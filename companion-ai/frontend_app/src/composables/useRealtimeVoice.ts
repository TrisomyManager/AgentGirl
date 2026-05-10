/**
 * Real-time voice call composable.
 *
 * Pipeline:
 *   mic → AudioWorklet (Int16 PCM 16kHz) ─┐
 *                                         ├─ WebSocket /voice/realtime
 *   Silero VAD (browser) ─ speech start/end ┘
 *
 *   Server PCM (Int16 sampleRate) ← WebSocket ← AudioBuffer queue ← speakers
 *
 * Supports both unified event protocol and legacy event protocol.
 *
 * Unified events (v2):
 *   ready, user_transcript_delta, user_transcript_final,
 *   assistant_text_delta, assistant_sentence_start,
 *   assistant_audio_chunk (binary), assistant_audio_done,
 *   interrupted, error, pong
 *
 * Legacy events (v1, for backward compat):
 *   ready, transcript, llm_token, llm_done, tts_start, tts_done,
 *   turn_done, interrupted, error, pong
 */

import { computed, onScopeDispose, ref } from 'vue';
import { COMPANION_DEFAULT_USER_ID, COMPANION_SESSION_STORAGE_KEY } from './useChat';

function buildRealtimeWsUrl(): string {
  const apiBase =
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
    'http://127.0.0.1:8000';
  const wsRoot = apiBase.replace(/^http/, 'ws');
  const baseForUrl = wsRoot.endsWith('/') ? wsRoot : `${wsRoot}/`;
  const u = new URL('voice/realtime', baseForUrl);
  try {
    u.searchParams.set('user_id', COMPANION_DEFAULT_USER_ID);
    const sid =
      typeof localStorage !== 'undefined' ? localStorage.getItem(COMPANION_SESSION_STORAGE_KEY) : null;
    if (sid) u.searchParams.set('session_id', sid);
  } catch {
    /* ignore storage / URL issues */
  }
  return u.toString();
}

const TARGET_PCM_RATE = 16000;
const PCM_CHUNK_SAMPLES = 2048;

/** Downsample mono float32 to 16 kHz (nearest-neighbour); server ASR expects 16 kHz PCM. */
function downsampleFloat32To16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === TARGET_PCM_RATE) return input;
  const ratio = inputRate / TARGET_PCM_RATE;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    out[i] = input[Math.min(Math.floor(i * ratio), input.length - 1)];
  }
  return out;
}

function float32ToInt16Pcm(samples: Float32Array): Int16Array {
  const int16 = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    int16[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return int16;
}

/** Module-level reactive state – reflects the most recent realtime voice session. */
export const currentAudioFormat = ref<string>('pcm');
export const currentRealtimeProvider = ref<string>('');
export const currentSampleRate = ref<number>(0);

export type CallState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'error';

export interface CallTranscriptItem {
  id: string;
  role: 'user' | 'assistant';
  text: string;
}

export function useRealtimeVoice() {
  const state = ref<CallState>('idle');
  const userSpeaking = ref(false);
  const errorMsg = ref<string | null>(null);
  const transcript = ref<CallTranscriptItem[]>([]);
  const partialAssistant = ref('');
  const partialUser = ref('');

  let ws: WebSocket | null = null;
  let micStream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let workletNode: AudioWorkletNode | null = null;
  /** Legacy PCM capture when AudioWorklet is unavailable (embedded browsers, etc.). */
  let pcmScriptProcessor: ScriptProcessorNode | null = null;
  let micVad: any = null;
  let playCtx: AudioContext | null = null;
  let playSampleRate = 22050;
  let nextPlayTime = 0;
  let activePlaybackSources: AudioBufferSourceNode[] = [];
  let thinkingTimer: ReturnType<typeof setTimeout> | null = null;
  const THINKING_TIMEOUT_MS = 20_000; // 20s — back to listening if no response
  let wsCloseIntentional = false;

  const isActive = computed(() => state.value !== 'idle' && state.value !== 'error');

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  async function startCall(): Promise<void> {
    if (state.value !== 'idle' && state.value !== 'error') return;
    errorMsg.value = null;
    transcript.value = [];
    partialAssistant.value = '';
    partialUser.value = '';
    state.value = 'connecting';
    try {
      await openWs();
      await openMic();
      state.value = 'listening';
    } catch (err) {
      errorMsg.value = (err as Error).message || String(err);
      state.value = 'error';
      await stopCall();
    }
  }

  async function stopCall(): Promise<void> {
    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        wsCloseIntentional = true;
        ws.close();
      }
    } catch {}
    ws = null;
    if (micVad) {
      try {
        micVad.pause();
        micVad.destroy();
      } catch {}
      micVad = null;
    }
    if (pcmScriptProcessor) {
      try {
        pcmScriptProcessor.disconnect();
      } catch {}
      pcmScriptProcessor = null;
    }
    if (workletNode) {
      try {
        workletNode.disconnect();
      } catch {}
      workletNode = null;
    }
    if (audioCtx) {
      try {
        await audioCtx.close();
      } catch {}
      audioCtx = null;
    }
    if (micStream) {
      micStream.getTracks().forEach((t) => t.stop());
      micStream = null;
    }
    abortPlayback();
    if (playCtx) {
      try {
        await playCtx.close();
      } catch {}
      playCtx = null;
    }
    clearThinkingTimer();
    state.value = 'idle';
    userSpeaking.value = false;
  }

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  async function openWs(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = buildRealtimeWsUrl();
      const sock = new WebSocket(wsUrl);
      sock.binaryType = 'arraybuffer';
      let opened = false;
      const timer = setTimeout(() => {
        sock.close();
        reject(new Error('WebSocket connect timeout（5s），请确认后端在运行）'));
      }, 5000);

      sock.onopen = () => {
        clearTimeout(timer);
        opened = true;
        let sessionId: string | undefined;
        try {
          sessionId =
            (typeof localStorage !== 'undefined' && localStorage.getItem(COMPANION_SESSION_STORAGE_KEY)) ||
            undefined;
        } catch {
          sessionId = undefined;
        }
        sock.send(
          JSON.stringify({
            type: 'start',
            user_id: COMPANION_DEFAULT_USER_ID,
            ...(sessionId ? { session_id: sessionId } : {}),
          }),
        );
        resolve();
      };
      sock.onerror = () => {
        clearTimeout(timer);
        if (!opened) {
          reject(
            new Error(
              `无法连接实时语音 WebSocket：${wsUrl}。请确认已启动后端（如 uvicorn）且 VITE_API_BASE_URL 与页面同源或可访问。`
            )
          );
        }
      };
      sock.onclose = (ev) => {
        clearTimeout(timer);
        if (wsCloseIntentional) {
          wsCloseIntentional = false;
          return;
        }
        if (!opened) {
          reject(
            new Error(
              (ev.reason && String(ev.reason)) ||
                `实时语音连接失败（code ${ev.code}）。请检查后端 /voice/realtime 是否正常。`
            )
          );
          return;
        }
        if (
          state.value === 'listening' ||
          state.value === 'thinking' ||
          state.value === 'speaking'
        ) {
          errorMsg.value =
            (ev.reason && String(ev.reason)) ||
            (ev.code !== 1000 ? `通话连接断开 (code ${ev.code})` : '通话连接已结束');
          state.value = 'error';
        }
      };
      sock.onmessage = (ev) => {
        if (typeof ev.data === 'string') {
          handleControl(ev.data);
        } else {
          handleAudioChunk(ev.data as ArrayBuffer);
        }
      };
      ws = sock;
    });
  }

  function clearThinkingTimer() {
    if (thinkingTimer !== null) {
      clearTimeout(thinkingTimer);
      thinkingTimer = null;
    }
  }

  function handleControl(raw: string) {
    let msg: any;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }

    switch (msg.type) {
      // ---- Unified events (v2) ----
      case 'ready':
        partialUser.value = '';
        break;

      case 'user_transcript_delta':
        partialUser.value += msg.text || '';
        break;

      case 'user_transcript_final': {
        const text = msg.text || partialUser.value;
        if (text) {
          transcript.value.push({
            id: `u-${Date.now()}`,
            role: 'user',
            text,
          });
        }
        partialUser.value = '';
        state.value = 'thinking';
        partialAssistant.value = '';
        // Start thinking timeout — revert to listening if no response
        clearThinkingTimer();
        thinkingTimer = setTimeout(() => {
          if (state.value === 'thinking') {
            state.value = 'listening';
          }
        }, THINKING_TIMEOUT_MS);
        break;
      }

      case 'assistant_text_delta':
        clearThinkingTimer();
        partialAssistant.value += msg.text || '';
        break;

      case 'assistant_sentence_start':
        clearThinkingTimer();
        playSampleRate = msg.sample_rate || 22050;
        currentSampleRate.value = playSampleRate;
        currentAudioFormat.value = msg.audio_format || 'pcm';
        currentRealtimeProvider.value = msg.provider || '';
        state.value = 'speaking';
        ensurePlayContext();
        break;

      case 'assistant_audio_done':
        break;

      // ---- Legacy events (v1) ----
      case 'transcript':
        if (msg.text) {
          transcript.value.push({
            id: `u-${Date.now()}`,
            role: 'user',
            text: msg.text,
          });
          state.value = 'thinking';
          partialAssistant.value = '';
          clearThinkingTimer();
          thinkingTimer = setTimeout(() => {
            if (state.value === 'thinking') {
              state.value = 'listening';
            }
          }, THINKING_TIMEOUT_MS);
        }
        break;

      case 'llm_token':
        clearThinkingTimer();
        partialAssistant.value += msg.text || '';
        break;

      case 'llm_done':
        if (partialAssistant.value) {
          transcript.value.push({
            id: `a-${Date.now()}`,
            role: 'assistant',
            text: partialAssistant.value,
          });
          partialAssistant.value = '';
        }
        break;

      case 'tts_start':
        clearThinkingTimer();
        playSampleRate = msg.sample_rate || 22050;
        currentSampleRate.value = playSampleRate;
        currentAudioFormat.value = msg.audio_format || 'pcm';
        currentRealtimeProvider.value = msg.provider || '';
        state.value = 'speaking';
        ensurePlayContext();
        break;

      case 'tts_done':
        break;

      case 'turn_done':
        clearThinkingTimer();
        state.value = userSpeaking.value ? 'listening' : 'listening';
        break;

      // ---- Shared events ----
      case 'interrupted':
        clearThinkingTimer();
        abortPlayback();
        state.value = 'listening';
        break;

      case 'error': {
        clearThinkingTimer();
        const m =
          (typeof msg.msg === 'string' && msg.msg.trim()) ||
          (typeof msg.message === 'string' && msg.message.trim()) ||
          (typeof msg.error === 'string' && msg.error.trim());
        errorMsg.value = m || JSON.stringify(msg);
        state.value = 'error';
        break;
      }

      case 'pong':
        break;
    }
  }

  function handleAudioChunk(buf: ArrayBuffer) {
    if (!playCtx) ensurePlayContext();
    if (!playCtx) return;

    const fmt = currentAudioFormat.value;
    if (fmt === 'pcm') {
      playPcmChunk(buf);
    } else {
      playCompressedChunk(buf);
    }
  }

  function playPcmChunk(buf: ArrayBuffer) {
    if (!playCtx) return;
    const int16 = new Int16Array(buf);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;
    const audioBuffer = playCtx.createBuffer(1, float32.length, playSampleRate);
    audioBuffer.getChannelData(0).set(float32);
    scheduleBuffer(audioBuffer);
  }

  function playCompressedChunk(buf: ArrayBuffer) {
    if (!playCtx) return;
    playCtx.decodeAudioData(buf.slice(0)).then(
      (audioBuffer) => {
        scheduleBuffer(audioBuffer);
      },
      (err) => {
        errorMsg.value = `音频解码失败 (${currentAudioFormat.value}): ${err?.message || err}`;
      }
    );
  }

  function scheduleBuffer(audioBuffer: AudioBuffer) {
    if (!playCtx) return;
    const src = playCtx.createBufferSource();
    src.buffer = audioBuffer;
    src.connect(playCtx.destination);
    const now = playCtx.currentTime;
    if (nextPlayTime < now) nextPlayTime = now + 0.02;
    src.start(nextPlayTime);
    src.onended = () => {
      activePlaybackSources = activePlaybackSources.filter((s) => s !== src);
    };
    activePlaybackSources.push(src);
    nextPlayTime += audioBuffer.duration;
  }

  function ensurePlayContext() {
    if (!playCtx) {
      const Ctx: typeof AudioContext =
        (window as any).AudioContext || (window as any).webkitAudioContext;
      playCtx = new Ctx({ sampleRate: playSampleRate });
      nextPlayTime = playCtx.currentTime;
      void playCtx.resume?.();
    }
  }

  function abortPlayback() {
    for (const src of activePlaybackSources) {
      try {
        src.stop();
      } catch {}
    }
    activePlaybackSources = [];
    nextPlayTime = playCtx ? playCtx.currentTime : 0;
  }

  // ------------------------------------------------------------------
  // Mic capture + VAD
  // ------------------------------------------------------------------

  async function openMic(): Promise<void> {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const Ctx: typeof AudioContext =
      (window as any).AudioContext || (window as any).webkitAudioContext;
    // Use device default rate; resample to 16 kHz before sending (server ASR expects 16 kHz).
    audioCtx = new Ctx();
    await audioCtx.resume();

    const inputRate = audioCtx.sampleRate;
    const micSrc = audioCtx.createMediaStreamSource(micStream);
    const silentOut = audioCtx.createGain();
    silentOut.gain.value = 0;
    silentOut.connect(audioCtx.destination);

    let pcm16kCarry = new Float32Array(0);

    function feedPcmAt16k(floatAt16k: Float32Array) {
      const merged = new Float32Array(pcm16kCarry.length + floatAt16k.length);
      merged.set(pcm16kCarry);
      merged.set(floatAt16k, pcm16kCarry.length);
      let pos = 0;
      while (pos + PCM_CHUNK_SAMPLES <= merged.length) {
        const slice = merged.subarray(pos, pos + PCM_CHUNK_SAMPLES);
        pos += PCM_CHUNK_SAMPLES;
        const i16 = float32ToInt16Pcm(slice);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(i16.buffer.slice(i16.byteOffset, i16.byteOffset + i16.byteLength));
        }
      }
      pcm16kCarry = merged.subarray(pos);
    }

    function sendNativeFloatAsPcm16k(nativeMono: Float32Array) {
      const at16k = downsampleFloat32To16k(nativeMono, inputRate);
      if (at16k.length) feedPcmAt16k(at16k);
    }

    // --- PCM tap: prefer AudioWorklet; fall back to ScriptProcessor (embedded / legacy browsers) ---
    const nativeSamplesPerChunk = Math.max(
      1,
      Math.round((PCM_CHUNK_SAMPLES * inputRate) / TARGET_PCM_RATE)
    );
    let nativeCarry = new Float32Array(0);

    try {
      if (!audioCtx.audioWorklet) throw new Error('AudioWorklet API missing');
      await audioCtx.audioWorklet.addModule('/pcm-recorder-worklet.js');
      workletNode = new AudioWorkletNode(audioCtx, 'pcm-recorder');
      workletNode.port.onmessage = (e: MessageEvent) => {
        if (!userSpeaking.value) return;
        const int16 = new Int16Array(e.data as ArrayBuffer);
        const chunk = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) chunk[i] = int16[i] / 0x8000;
        const merged = new Float32Array(nativeCarry.length + chunk.length);
        merged.set(nativeCarry);
        merged.set(chunk, nativeCarry.length);
        nativeCarry = merged;
        while (nativeCarry.length >= nativeSamplesPerChunk) {
          const block = nativeCarry.subarray(0, nativeSamplesPerChunk);
          nativeCarry = nativeCarry.subarray(nativeSamplesPerChunk);
          sendNativeFloatAsPcm16k(block);
        }
      };
      micSrc.connect(workletNode);
      workletNode.connect(silentOut);
    } catch (workletErr) {
      console.warn('[useRealtimeVoice] AudioWorklet failed, using ScriptProcessor', workletErr);
      const bufferSize = 4096;
      pcmScriptProcessor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      pcmScriptProcessor.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!userSpeaking.value) return;
        const input = e.inputBuffer.getChannelData(0);
        e.outputBuffer.getChannelData(0).fill(0);
        const merged = new Float32Array(nativeCarry.length + input.length);
        merged.set(nativeCarry);
        merged.set(input, nativeCarry.length);
        nativeCarry = merged;
        while (nativeCarry.length >= nativeSamplesPerChunk) {
          const block = nativeCarry.subarray(0, nativeSamplesPerChunk);
          nativeCarry = nativeCarry.subarray(nativeSamplesPerChunk);
          sendNativeFloatAsPcm16k(block);
        }
      };
      micSrc.connect(pcmScriptProcessor);
      pcmScriptProcessor.connect(silentOut);
    }

    // --- VAD: reuse mic stream + same AudioContext; force ScriptProcessor (more reliable than nested Worklets) ---
    const { MicVAD } = await import('@ricky0123/vad-web');
    const streamRef = micStream;
    micVad = await MicVAD.new({
      model: 'v5',
      baseAssetPath: '/',
      onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/',
      getStream: async () => streamRef as MediaStream,
      audioContext: audioCtx,
      processorType: 'ScriptProcessor',
      startOnLoad: false,
      onSpeechStart: () => {
        userSpeaking.value = true;
        nativeCarry = new Float32Array(0);
        pcm16kCarry = new Float32Array(0);
        if (state.value === 'speaking' || state.value === 'thinking') {
          abortPlayback();
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'interrupt' }));
          }
        }
        state.value = 'listening';
      },
      onSpeechEnd: () => {
        userSpeaking.value = false;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'speech_end' }));
        }
        state.value = 'thinking';
        clearThinkingTimer();
        thinkingTimer = setTimeout(() => {
          if (state.value === 'thinking') {
            state.value = 'listening';
          }
        }, THINKING_TIMEOUT_MS);
      },
      onVADMisfire: () => {
        userSpeaking.value = false;
      },
      positiveSpeechThreshold: 0.7,
      negativeSpeechThreshold: 0.55,
      minSpeechMs: 400,
    } as any);
    await micVad.start();
  }

  onScopeDispose(() => {
    void stopCall();
  });

  return {
    state,
    userSpeaking,
    errorMsg,
    transcript,
    partialAssistant,
    partialUser,
    isActive,
    startCall,
    stopCall,
    audioFormat: currentAudioFormat,
    realtimeProvider: currentRealtimeProvider,
    sampleRate: currentSampleRate,
  };
}

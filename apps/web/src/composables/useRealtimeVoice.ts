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

import { computed, getCurrentScope, onScopeDispose, ref } from 'vue';
import { COMPANION_SESSION_STORAGE_KEY } from './useChat';
import { currentUserId, sessionProtocols, userStorageKey } from './accessSession';
import { rms, type AvatarTimeline } from '../../../../packages/avatar-runtime/src';
import { avatarClock } from './useAvatarPresentation';
import { AUDIO_PROTOCOL, decodeAudioFrame, encodeAudioFrame } from '../../../../packages/audio-transport/src';

function buildRealtimeWsUrl(): string {
  const apiBase =
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
    'http://127.0.0.1:8000';
  const wsRoot = apiBase.replace(/^http/, 'ws');
  const baseForUrl = wsRoot.endsWith('/') ? wsRoot : `${wsRoot}/`;
  const u = new URL('voice/realtime', baseForUrl);
  u.searchParams.set('audio_protocol', AUDIO_PROTOCOL);
  try {
    u.searchParams.set('user_id', currentUserId());
    const sid =
      typeof localStorage !== 'undefined' ? localStorage.getItem(userStorageKey(COMPANION_SESSION_STORAGE_KEY)) : null;
    if (sid) u.searchParams.set('session_id', sid);
  } catch {
    /* ignore storage / URL issues */
  }
  return u.toString();
}

const TARGET_PCM_RATE = 16000;
const PCM_CHUNK_SAMPLES = 2048;
const MAX_AUDIO_FRAME_BYTES = 2 * 1024 * 1024;
const MAX_PENDING_DECODES = 16;
const MAX_PLAYBACK_SECONDS = 30;

function validSampleRate(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 8000 && value <= 192000
    ? value : 22050;
}

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
  let audioProtocol = 'raw', inputSequence = 0, outputSequence = 0, activeStream = 0, lastStream = 0;
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
  let presentationBuffers: { source: AudioBufferSourceNode; buffer: AudioBuffer; start: number; timeline?: AvatarTimeline }[] = [];
  let pendingTimeline: AvatarTimeline | undefined;
  let avatarToken: number | null = null, avatarRaf = 0, avatarKey = '', avatarStart = 0;
  let thinkingTimer: ReturnType<typeof setTimeout> | null = null;
  const THINKING_TIMEOUT_MS = 20_000; // 20s — back to listening if no response
  let wsCloseIntentional = false;
  let playbackEpoch = 0;
  let callGeneration = 0;
  let cleanupPromise: Promise<void> | null = null;
  let decodeQueue: Promise<void> = Promise.resolve();
  let pendingDecodes = 0;
  let pcmCarry: number | null = null;
  let acceptsAudio = false;
  let waitingInterruptAck = false;
  let audioFinished = false;
  let jitterDelay = 0.04;
  let lastArrival = 0;

  const isActive = computed(() => state.value !== 'idle' && state.value !== 'error');

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  async function startCall(): Promise<void> {
    if (cleanupPromise) await cleanupPromise;
    if (state.value !== 'idle' && state.value !== 'error') return;
    errorMsg.value = null;
    transcript.value = [];
    partialAssistant.value = '';
    partialUser.value = '';
    state.value = 'connecting';
    const generation = ++callGeneration;
    waitingInterruptAck = false;
    try {
      await openWs();
      if (generation !== callGeneration) return;
      if (!await openMic(generation) || generation !== callGeneration) return;
      state.value = 'listening';
    } catch (err) {
      if (generation !== callGeneration) return;
      await failCall((err as Error).message || String(err));
    }
  }

  async function stopCall(): Promise<void> {
    if (cleanupPromise) return cleanupPromise;
    cleanupPromise = closeCallResources();
    try { await cleanupPromise; }
    finally { cleanupPromise = null; }
  }

  async function failCall(message: string): Promise<void> {
    const closing = stopCall(), generation = callGeneration;
    errorMsg.value = message; state.value = 'error';
    await closing;
    if (generation === callGeneration) { errorMsg.value = message; state.value = 'error'; }
  }

  async function closeCallResources(): Promise<void> {
    callGeneration++;
    waitingInterruptAck = false;
    try {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
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
      audioProtocol = 'raw'; inputSequence = 0; outputSequence = 0; activeStream = 0; lastStream = 0;
      wsCloseIntentional = false;
      const wsUrl = buildRealtimeWsUrl();
      const protocols = sessionProtocols();
      const sock = protocols ? new WebSocket(wsUrl, protocols) : new WebSocket(wsUrl);
      sock.binaryType = 'arraybuffer';
      let opened = false;
      let negotiated = false;
      const timer = setTimeout(() => {
        sock.close();
        reject(new Error('WebSocket connect timeout（5s），请确认后端在运行）'));
      }, 5000);

      sock.onopen = () => {
        if (ws !== sock) { sock.close(); reject(new Error('通话已取消')); return; }
        opened = true;
        let sessionId: string | undefined;
        try {
          sessionId =
            (typeof localStorage !== 'undefined' && localStorage.getItem(userStorageKey(COMPANION_SESSION_STORAGE_KEY))) ||
            undefined;
        } catch {
          sessionId = undefined;
        }
        sock.send(
          JSON.stringify({
            type: 'start',
            user_id: currentUserId(),
            ...(sessionId ? { session_id: sessionId } : {}),
          }),
        );
      };
      sock.onerror = () => {
        clearTimeout(timer);
        if (!negotiated) {
          reject(
            new Error(
              `无法连接实时语音 WebSocket：${wsUrl}。请确认已启动后端（如 uvicorn）且 VITE_API_BASE_URL 与页面同源或可访问。`
            )
          );
        }
      };
      sock.onclose = (ev) => {
        clearTimeout(timer);
        if (ws !== sock) { if (!negotiated) reject(new Error('通话已取消')); return; }
        if (wsCloseIntentional) {
          wsCloseIntentional = false;
          return;
        }
        if (!negotiated) {
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
          const message =
            (ev.reason && String(ev.reason)) ||
            (ev.code !== 1000 ? `通话连接断开 (code ${ev.code})` : '通话连接已结束');
          void failCall(message);
        }
      };
      sock.onmessage = (ev) => {
        if (ws !== sock) return;
        if (typeof ev.data === 'string') {
          if (new TextEncoder().encode(ev.data).byteLength > 65536) { protocolFailure(); return; }
          try {
            const control = JSON.parse(ev.data);
            if (!negotiated && (control.type === 'transport_ready' || control.type === 'ready')) {
              const selected = control.type === 'ready' ? 'raw' : control.audio_protocol;
              if (selected !== 'raw' && selected !== AUDIO_PROTOCOL) throw new Error('Unsupported audio protocol');
              audioProtocol = selected; negotiated = true; clearTimeout(timer); resolve();
            } else if (!negotiated && control.type === 'error') {
              clearTimeout(timer); reject(new Error('语音服务暂时不可用，请检查配置后重试。'));
            }
          } catch { protocolFailure(); return; }
          handleControl(ev.data);
        } else {
          if (!negotiated) { protocolFailure(); return; }
          if (audioProtocol === AUDIO_PROTOCOL) {
            try {
              const frame = decodeAudioFrame(ev.data as ArrayBuffer);
              if (frame.sequence !== outputSequence++) throw new Error('Audio sequence mismatch');
              if (activeStream && frame.streamId === activeStream) handleAudioChunk(frame.payload);
            } catch { protocolFailure(); }
          } else handleAudioChunk(ev.data as ArrayBuffer);
        }
      };
      ws = sock;
    });
  }

  function protocolFailure() {
    ws?.close(1002);
    void failCall('语音传输格式或顺序不正确，请重新连接。');
  }

  function selectAudioStream(message: any): boolean {
    if (audioProtocol !== AUDIO_PROTOCOL) return true;
    const id = message.audio_stream_id;
    if (!Number.isInteger(id) || id <= lastStream || id > 0xffffffff) { protocolFailure(); return false; }
    activeStream = lastStream = id;
    return true;
  }

  function sendPcm(payload: ArrayBufferLike) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const data = payload instanceof ArrayBuffer ? payload : new Uint8Array(payload).slice().buffer;
    try { ws.send(audioProtocol === AUDIO_PROTOCOL ? encodeAudioFrame(data, 0, inputSequence++) : data); }
    catch { protocolFailure(); }
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
        if (waitingInterruptAck) break;
        if (!selectAudioStream(msg)) break;
        acceptsAudio = true;
        pendingTimeline = msg.avatar_timeline || undefined;
        audioFinished = false;
        clearThinkingTimer();
        playSampleRate = validSampleRate(msg.sample_rate);
        currentSampleRate.value = playSampleRate;
        currentAudioFormat.value = msg.audio_format || 'pcm';
        currentRealtimeProvider.value = msg.provider || '';
        state.value = 'speaking';
        ensurePlayContext();
        break;

      case 'assistant_audio_done':
        if (msg.final) { audioFinished = true; finishPlaybackIfDrained(); }
        break;
      case 'assistant_text_done':
        commitAssistantText();
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
        if (waitingInterruptAck) break;
        if (!selectAudioStream(msg)) break;
        acceptsAudio = true;
        audioFinished = false;
        clearThinkingTimer();
        playSampleRate = validSampleRate(msg.sample_rate);
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
        commitAssistantText();
        audioFinished = true;
        finishPlaybackIfDrained();
        break;

      // ---- Shared events ----
      case 'interrupted':
        clearThinkingTimer();
        abortPlayback();
        waitingInterruptAck = false;
        state.value = 'listening';
        break;

      case 'error': {
        clearThinkingTimer();
        const m =
          (typeof msg.msg === 'string' && msg.msg.trim()) ||
          (typeof msg.message === 'string' && msg.message.trim()) ||
          (typeof msg.error === 'string' && msg.error.trim());
        if (msg.recoverable) {
          errorMsg.value = m || '语音处理出现问题，请重试。'; abortPlayback(); state.value = 'listening';
        } else void failCall(m || '语音处理出现问题，请重试。');
        break;
      }

      case 'pong':
        break;
    }
  }

  function handleAudioChunk(buf: ArrayBuffer) {
    if (!acceptsAudio || waitingInterruptAck) return;
    if (buf.byteLength > MAX_AUDIO_FRAME_BYTES) {
      stopOverloadedPlayback();
      return;
    }
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
    const bytes = new Uint8Array(buf);
    const merged = new Uint8Array(bytes.length + (pcmCarry === null ? 0 : 1));
    if (pcmCarry !== null) merged[0] = pcmCarry;
    merged.set(bytes, pcmCarry === null ? 0 : 1);
    const even = merged.length - merged.length % 2;
    pcmCarry = even < merged.length ? merged[even] : null;
    if (!even) return;
    const int16 = new Int16Array(merged.buffer, 0, even / 2);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;
    const audioBuffer = playCtx.createBuffer(1, float32.length, playSampleRate);
    audioBuffer.getChannelData(0).set(float32);
    scheduleBuffer(audioBuffer);
  }

  function playCompressedChunk(buf: ArrayBuffer) {
    if (!playCtx) return;
    if (pendingDecodes >= MAX_PENDING_DECODES) {
      stopOverloadedPlayback();
      return;
    }
    const epoch = playbackEpoch;
    const timeline = pendingTimeline;
    const context = playCtx;
    pendingDecodes++;
    const decoded = context.decodeAudioData(buf.slice(0)).then(
      buffer => ({ buffer, error: null }), error => ({ buffer: null, error }),
    );
    decodeQueue = decodeQueue.then(async () => {
      const result = await decoded;
      if (epoch !== playbackEpoch || context !== playCtx) return;
      pendingDecodes--;
      if (result.buffer) scheduleBuffer(result.buffer, timeline);
      else errorMsg.value = '音频解码失败，请重试。';
      finishPlaybackIfDrained();
    });
  }

  function commitAssistantText() {
    if (!partialAssistant.value) return;
    transcript.value.push({ id: `a-${Date.now()}`, role: 'assistant', text: partialAssistant.value });
    partialAssistant.value = '';
  }

  function finishPlaybackIfDrained() {
    if (audioFinished && !activePlaybackSources.length && !pendingDecodes) {
      acceptsAudio = false;
      pcmCarry = null;
      stopAvatar();
      if (state.value !== 'idle' && state.value !== 'error') state.value = 'listening';
    }
  }

  function scheduleBuffer(audioBuffer: AudioBuffer, timeline = pendingTimeline) {
    if (!playCtx) return;
    if (Math.max(0, nextPlayTime - playCtx.currentTime) + audioBuffer.duration > MAX_PLAYBACK_SECONDS) {
      stopOverloadedPlayback();
      return;
    }
    const src = playCtx.createBufferSource();
    src.buffer = audioBuffer;
    src.connect(playCtx.destination);
    const now = playCtx.currentTime;
    const arrival = performance.now() / 1000;
    if (nextPlayTime < now) {
      const gap = lastArrival ? Math.max(0, arrival - lastArrival) : 0.04;
      jitterDelay = Math.min(0.25, Math.max(0.04, jitterDelay * .8 + gap * .2));
      nextPlayTime = now + jitterDelay;
    }
    lastArrival = arrival;
    src.start(nextPlayTime);
    presentationBuffers.push({ source: src, buffer: audioBuffer, start: nextPlayTime, timeline });
    if (!avatarRaf) avatarRaf = requestAnimationFrame(updateAvatar);
    src.onended = () => {
      activePlaybackSources = activePlaybackSources.filter((s) => s !== src);
      presentationBuffers = presentationBuffers.filter(item => item.source !== src);
      finishPlaybackIfDrained();
    };
    activePlaybackSources.push(src);
    nextPlayTime += audioBuffer.duration;
  }

  function updateAvatar() {
    avatarRaf = 0;
    if (!playCtx) return;
    const now = playCtx.currentTime;
    const item = presentationBuffers.find(item => item.start <= now && now < item.start + item.buffer.duration);
    if (item) {
      const key = item.timeline ? `${item.timeline.turn_id}:${item.timeline.segment_seq}` : 'native-audio';
      if (avatarToken === null || key !== avatarKey) {
        if (avatarToken !== null) avatarClock.stop(avatarToken);
        avatarToken = avatarClock.begin(item.timeline);
        avatarKey = key;
        avatarStart = item.start;
      }
      const data = item.buffer.getChannelData(0);
      const offset = Math.floor((now - item.start) * item.buffer.sampleRate);
      const samples = data.subarray(offset, Math.min(data.length, offset + 512));
      avatarClock.sample(avatarToken, (now - avatarStart) * 1000, rms(samples));
    } else if (avatarToken !== null) {
      avatarClock.sample(avatarToken, Math.max(0, (now - avatarStart) * 1000), 0, false);
    }
    if (activePlaybackSources.length || acceptsAudio) avatarRaf = requestAnimationFrame(updateAvatar);
  }

  function stopAvatar() {
    cancelAnimationFrame(avatarRaf);
    avatarRaf = 0;
    if (avatarToken !== null) avatarClock.stop(avatarToken);
    avatarToken = null;
    avatarKey = '';
    presentationBuffers = [];
  }

  function stopOverloadedPlayback() {
    abortPlayback();
    errorMsg.value = '语音积压过多，已停止播放；你可以继续说话。';
    state.value = 'listening';
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
    activeStream = 0;
    stopAvatar();
    pendingTimeline = undefined;
    playbackEpoch++;
    decodeQueue = Promise.resolve();
    pendingDecodes = 0;
    pcmCarry = null;
    acceptsAudio = false;
    audioFinished = false;
    lastArrival = 0;
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

  async function openMic(generation: number): Promise<boolean> {
    const acquiredStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    if (generation !== callGeneration) {
      acquiredStream.getTracks().forEach(track => track.stop());
      return false;
    }
    micStream = acquiredStream;
    const Ctx: typeof AudioContext =
      (window as any).AudioContext || (window as any).webkitAudioContext;
    // Use device default rate; resample to 16 kHz before sending (server ASR expects 16 kHz).
    const captureContext = new Ctx();
    audioCtx = captureContext;
    await captureContext.resume();
    if (generation !== callGeneration) { await captureContext.close(); return false; }

    const inputRate = captureContext.sampleRate;
    const micSrc = captureContext.createMediaStreamSource(micStream);
    const silentOut = captureContext.createGain();
    silentOut.gain.value = 0;
    silentOut.connect(captureContext.destination);

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
          sendPcm(i16.buffer.slice(i16.byteOffset, i16.byteOffset + i16.byteLength));
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
      if (!captureContext.audioWorklet) throw new Error('AudioWorklet API missing');
      await captureContext.audioWorklet.addModule('/pcm-recorder-worklet.js');
      if (generation !== callGeneration) return false;
      workletNode = new AudioWorkletNode(captureContext, 'pcm-recorder');
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
      pcmScriptProcessor = captureContext.createScriptProcessor(bufferSize, 1, 1);
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
    const detector = await MicVAD.new({
      model: 'v5',
      baseAssetPath: new URL(import.meta.env.BASE_URL, window.location.href).href,
      onnxWASMBasePath: new URL(`${import.meta.env.BASE_URL}ort/`, window.location.href).href,
      ortConfig: (ort: { env: { wasm: { numThreads?: number } } }) => { ort.env.wasm.numThreads = 1; },
      getStream: async () => streamRef as MediaStream,
      audioContext: captureContext,
      processorType: 'ScriptProcessor',
      startOnLoad: false,
      onSpeechStart: () => {
        errorMsg.value = null;
        userSpeaking.value = true;
        nativeCarry = new Float32Array(0);
        pcm16kCarry = new Float32Array(0);
        if (state.value === 'speaking' || state.value === 'thinking') {
          abortPlayback();
          waitingInterruptAck = true;
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
    if (generation !== callGeneration) { detector.pause(); detector.destroy(); return false; }
    micVad = detector;
    await detector.start();
    if (generation !== callGeneration) { detector.pause(); detector.destroy(); return false; }
    return true;
  }

  if (getCurrentScope()) onScopeDispose(() => {
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

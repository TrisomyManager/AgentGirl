/**
 * Real-time voice call composable.
 *
 * Pipeline:
 *   mic → AudioWorklet (Int16 PCM 16kHz) ─┐
 *                                         ├─ WebSocket /voice/realtime
 *   Silero VAD (browser) ─ speech start/end ┘
 *
 *   Server PCM (Int16 22050Hz) ← WebSocket ← AudioBuffer queue ← speakers
 */

import { computed, onScopeDispose, ref } from 'vue';

const WS_URL = (() => {
  const apiBase =
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
    'http://127.0.0.1:8000';
  return apiBase.replace(/^http/, 'ws') + '/voice/realtime';
})();

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

  let ws: WebSocket | null = null;
  let micStream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let workletNode: AudioWorkletNode | null = null;
  let micVad: any = null;
  let playCtx: AudioContext | null = null;
  let playSampleRate = 22050;
  let nextPlayTime = 0;
  let activePlaybackSources: AudioBufferSourceNode[] = [];

  const isActive = computed(() => state.value !== 'idle' && state.value !== 'error');

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  async function startCall(): Promise<void> {
    if (state.value !== 'idle' && state.value !== 'error') return;
    errorMsg.value = null;
    transcript.value = [];
    partialAssistant.value = '';
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
    state.value = 'idle';
    userSpeaking.value = false;
  }

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  async function openWs(): Promise<void> {
    return new Promise((resolve, reject) => {
      const sock = new WebSocket(WS_URL);
      sock.binaryType = 'arraybuffer';
      const timer = setTimeout(() => {
        sock.close();
        reject(new Error('WebSocket connect timeout'));
      }, 5000);

      sock.onopen = () => {
        clearTimeout(timer);
        sock.send(JSON.stringify({ type: 'start' }));
        resolve();
      };
      sock.onerror = () => {
        clearTimeout(timer);
        reject(new Error('WebSocket error'));
      };
      sock.onclose = () => {
        if (state.value !== 'idle') {
          state.value = 'idle';
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

  function handleControl(raw: string) {
    let msg: any;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    switch (msg.type) {
      case 'ready':
        // session ready
        break;
      case 'transcript':
        if (msg.text) {
          transcript.value.push({
            id: `u-${Date.now()}`,
            role: 'user',
            text: msg.text,
          });
          state.value = 'thinking';
          partialAssistant.value = '';
        }
        break;
      case 'llm_token':
        partialAssistant.value += msg.text;
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
        playSampleRate = msg.sample_rate || 22050;
        state.value = 'speaking';
        ensurePlayContext();
        break;
      case 'tts_done':
        // chunks for this sentence done; more may follow
        break;
      case 'turn_done':
        if (userSpeaking.value) {
          state.value = 'listening';
        } else {
          state.value = 'listening';
        }
        break;
      case 'interrupted':
        abortPlayback();
        state.value = 'listening';
        break;
      case 'error':
        errorMsg.value = msg.msg || 'unknown error';
        state.value = 'error';
        break;
    }
  }

  function handleAudioChunk(buf: ArrayBuffer) {
    if (!playCtx) ensurePlayContext();
    if (!playCtx) return;
    const int16 = new Int16Array(buf);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;
    const audioBuffer = playCtx.createBuffer(1, float32.length, playSampleRate);
    audioBuffer.getChannelData(0).set(float32);
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
    audioCtx = new Ctx({ sampleRate: 16000 });
    const src = audioCtx.createMediaStreamSource(micStream);
    await audioCtx.audioWorklet.addModule('/pcm-recorder-worklet.js');
    workletNode = new AudioWorkletNode(audioCtx, 'pcm-recorder');
    workletNode.port.onmessage = (e: MessageEvent) => {
      if (!userSpeaking.value) return;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(e.data as ArrayBuffer);
      }
    };
    src.connect(workletNode);
    workletNode.connect(audioCtx.destination); // safe: no audio actually playing back

    // Silero VAD opens its own mic stream — modern browsers share the device
    const { MicVAD } = await import('@ricky0123/vad-web');
    micVad = await MicVAD.new({
      model: 'v5',
      baseAssetPath: '/',
      onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/',
      onSpeechStart: () => {
        userSpeaking.value = true;
        if (state.value === 'speaking' || state.value === 'thinking') {
          // barge-in
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
      },
      onVADMisfire: () => {
        userSpeaking.value = false;
      },
      // Use slightly larger buffer for Chinese speech
      positiveSpeechThreshold: 0.55,
      negativeSpeechThreshold: 0.4,
      minSpeechMs: 250,
    } as any);
    micVad.start();
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
    isActive,
    startCall,
    stopCall,
  };
}

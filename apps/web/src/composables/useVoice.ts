import { getCurrentScope, onScopeDispose, ref } from 'vue';

import { absoluteApiUrl } from './useApi';
import { rms, type AvatarTimeline } from '../../../../packages/avatar-runtime/src';
import { avatarClock } from './useAvatarPresentation';
import { apiFetch as fetch, hasAccessSession } from './accessSession';

export interface PlaybackOptions { force?: boolean; avatarTimeline?: AvatarTimeline }

const AUTO_PLAY_KEY = 'companion_voice_auto_play';

function loadAutoPlayPreference(): boolean {
  try { return localStorage.getItem(AUTO_PLAY_KEY) !== 'false'; } catch { return true; }
}

export function useVoice() {
  const isRecording = ref(false);
  const isPlaying = ref(false);
  const autoPlayEnabled = ref(loadAutoPlayPreference());
  const recordingDuration = ref(0);

  let mediaRecorder: MediaRecorder | null = null;
  let recordingGeneration = 0;
  let recordingStream: MediaStream | null = null;
  let audioChunks: Blob[] = [];
  let audioElement: HTMLAudioElement | null = null;
  let playbackGeneration = 0;
  let sequenceGeneration = 0;
  let settlePlayback: (() => void) | null = null;
  let stopPresentation: (() => void) | null = null;
  let recordingTimer: ReturnType<typeof setInterval> | null = null;
  let recordingStartTime = 0;

  const onStopRecording = ref<((blob: Blob, durationMs: number) => void) | null>(null);

  async function startRecording(): Promise<void> {
    if (isRecording.value) return;
    stopAudio();
    const generation = ++recordingGeneration;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generation !== recordingGeneration) { stream.getTracks().forEach(track => track.stop()); return; }
      recordingStream = stream;
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (generation !== recordingGeneration) return;
        if (e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (generation !== recordingGeneration) return;
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        const durationMs = Math.max(0, Date.now() - recordingStartTime);
        isRecording.value = false;
        stopRecordingTimer();
        if (generation === recordingGeneration) onStopRecording.value?.(blob, durationMs);
      };

      mediaRecorder.onerror = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (generation !== recordingGeneration) return;
        isRecording.value = false;
        stopRecordingTimer();
      };

      mediaRecorder.start(100);
      isRecording.value = true;
      recordingStartTime = Date.now();
      recordingDuration.value = 0;
      startRecordingTimer();
    } catch (err) {
      console.error('Failed to start recording:', err);
      throw err;
    }
  }

  function stopRecording(): void {
    if (mediaRecorder && isRecording.value) {
      mediaRecorder.stop();
    }
  }

  function discardRecording(): void {
    recordingGeneration += 1;
    stopRecording();
    recordingStream?.getTracks().forEach(track => track.stop());
    recordingStream = null;
    audioChunks = [];
    isRecording.value = false;
    stopRecordingTimer();
  }

  function startRecordingTimer() {
    stopRecordingTimer();
    recordingTimer = setInterval(() => {
      recordingDuration.value = Math.floor((Date.now() - recordingStartTime) / 1000);
    }, 1000);
  }

  function stopRecordingTimer() {
    if (recordingTimer) {
      clearInterval(recordingTimer);
      recordingTimer = null;
    }
  }

  async function verifyVoiceAudioReachable(url: string): Promise<string> {
    const resolved = absoluteApiUrl(url);
    if (!resolved) {
      throw new Error('无效的语音播放地址。');
    }
    let r = await fetch(resolved, { method: 'HEAD', mode: 'cors' });
    if (r.status === 405 || r.status === 501) {
      r = await fetch(resolved, {
        method: 'GET',
        mode: 'cors',
        headers: { Range: 'bytes=0-0' },
      });
    }
    if (r.status === 404) {
      throw new Error(
        'TTS 音频不存在（404）：请确认后端已挂载 /static/voice，或重新请求带语音的回复。',
      );
    }
    if (r.status >= 500) {
      throw new Error(`音频地址返回服务器错误 ${r.status}，无法播放。`);
    }
    if (!r.ok && r.status !== 206) {
      throw new Error(`音频地址校验失败 HTTP ${r.status}。`);
    }
    return resolved;
  }

  async function playSingle(url: string, opts: PlaybackOptions = {}): Promise<void> {
    if (!opts.force && !autoPlayEnabled.value) return;
    cancelCurrent();
    const generation = playbackGeneration;
    let resolved: string;
    try { resolved = await verifyVoiceAudioReachable(url); }
    catch (error) { if (generation !== playbackGeneration) return; throw error; }
    if (generation !== playbackGeneration) return;
    let ownedBlobUrl: string | null = null;
    if (hasAccessSession()) {
      const response = await fetch(resolved);
      if (!response.ok) throw new Error('无法读取当前账号的音频，请重新登录或重新生成语音。');
      const blob = await response.blob();
      if (generation !== playbackGeneration) return;
      ownedBlobUrl = URL.createObjectURL(blob);
      resolved = ownedBlobUrl;
    }
    return new Promise((resolve, reject) => {
      const element = new Audio();
      element.crossOrigin = 'anonymous';
      element.src = resolved;
      audioElement = element;
      let context: AudioContext | null = null;
      let analyser: AnalyserNode | null = null;
      let source: MediaElementAudioSourceNode | null = null;
      let frameId = 0, token: number | null = null;
      const cleanup = () => {
        if (ownedBlobUrl) { URL.revokeObjectURL(ownedBlobUrl); ownedBlobUrl = null; }
        cancelAnimationFrame(frameId);
        if (token !== null) avatarClock.stop(token);
        source?.disconnect();
        analyser?.disconnect();
        if (context) void context.close().catch(() => {});
        context = null;
      };
      stopPresentation = cleanup;
      let settled = false;
      const finish = (error?: unknown) => {
        if (settled) return;
        settled = true;
        element.onended = null;
        element.onerror = null;
        if (audioElement === element) {
          cleanup();
          stopPresentation = null;
          audioElement = null;
          settlePlayback = null;
          isPlaying.value = false;
        }
        if (error) reject(error); else resolve();
      };
      settlePlayback = () => finish();
      element.onended = () => finish();
      element.onerror = () => finish(new Error('音频加载或解码失败，请重试。'));
      // Keep ordinary audio working when a browser lacks WebAudio analysis.
      try {
        const Ctx = window.AudioContext || (window as any).webkitAudioContext;
        if (Ctx && typeof Ctx.prototype.createMediaElementSource === 'function') {
          context = new Ctx();
          void context!.resume().catch(() => {});
          source = context!.createMediaElementSource(element);
          source.connect(context!.destination);
          analyser = context!.createAnalyser();
          analyser.fftSize = 256;
          source.connect(analyser);
        }
      } catch { /* Mouth stays closed if analysis is unavailable. */ }
      element.play().then(() => {
        if (generation !== playbackGeneration || audioElement !== element) return;
        isPlaying.value = true;
        token = avatarClock.begin(opts.avatarTimeline);
        const samples = new Float32Array(analyser?.fftSize || 256);
        const tick = () => {
          if (generation !== playbackGeneration || audioElement !== element || token === null) return;
          analyser?.getFloatTimeDomainData(samples);
          avatarClock.sample(token, element.currentTime * 1000, analyser ? rms(samples) : 0, !element.paused && !element.ended);
          frameId = requestAnimationFrame(tick);
        };
        frameId = requestAnimationFrame(tick);
      }).catch(error => {
        if (generation === playbackGeneration) finish(error);
      });
    });
  }

  function cancelCurrent(): void {
    playbackGeneration++;
    if (audioElement) {
      audioElement.pause();
      try { audioElement.currentTime = 0; } catch { /* not loaded yet */ }
    }
    settlePlayback?.();
    stopPresentation?.();
    stopPresentation = null;
    audioElement = null;
    settlePlayback = null;
    isPlaying.value = false;
  }

  async function playAudio(url: string, opts: PlaybackOptions = {}): Promise<void> {
    sequenceGeneration++;
    await playSingle(url, opts);
  }

  async function playAudioSequence(
    urls: string[], opts: PlaybackOptions & { avatarTimelines?: (AvatarTimeline | undefined)[] } = {},
  ): Promise<void> {
    stopAudio();
    const generation = sequenceGeneration;
    for (const [index, url] of urls.entries()) {
      if (generation !== sequenceGeneration || (!opts.force && !autoPlayEnabled.value)) return;
      await playSingle(url, { ...opts, avatarTimeline: opts.avatarTimelines?.[index] || opts.avatarTimeline });
    }
  }

  function stopAudio(): void {
    sequenceGeneration++;
    cancelCurrent();
  }

  function toggleAutoPlay(): void {
    autoPlayEnabled.value = !autoPlayEnabled.value;
    try { localStorage.setItem(AUTO_PLAY_KEY, String(autoPlayEnabled.value)); } catch { /* optional browser storage */ }
    if (!autoPlayEnabled.value) {
      stopAudio();
    }
  }

  if (getCurrentScope()) onScopeDispose(() => {
    onStopRecording.value = null;
    discardRecording();
    stopAudio();
    stopRecordingTimer();
  });

  return {
    isRecording,
    isPlaying,
    autoPlayEnabled,
    recordingDuration,
    startRecording,
    stopRecording,
    discardRecording,
    playAudio,
    playAudioSequence,
    verifyVoiceAudioReachable,
    stopAudio,
    toggleAutoPlay,
    onStopRecording,
  };
}

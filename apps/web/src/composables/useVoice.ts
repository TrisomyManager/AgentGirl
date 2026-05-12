import { ref } from 'vue';

import { absoluteApiUrl } from './useApi';

export function useVoice() {
  const isRecording = ref(false);
  const isPlaying = ref(false);
  const autoPlayEnabled = ref(true);
  const recordingDuration = ref(0);

  let mediaRecorder: MediaRecorder | null = null;
  let audioChunks: Blob[] = [];
  let audioElement: HTMLAudioElement | null = null;
  let recordingTimer: ReturnType<typeof setInterval> | null = null;
  let recordingStartTime = 0;

  const onStopRecording = ref<((blob: Blob, durationMs: number) => void) | null>(null);

  async function startRecording(): Promise<void> {
    if (isRecording.value) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        const durationMs = Math.max(0, Date.now() - recordingStartTime);
        isRecording.value = false;
        stopRecordingTimer();
        stream.getTracks().forEach((t) => t.stop());
        onStopRecording.value?.(blob, durationMs);
      };

      mediaRecorder.onerror = () => {
        isRecording.value = false;
        stopRecordingTimer();
        stream.getTracks().forEach((t) => t.stop());
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

  async function playAudio(url: string, opts: { force?: boolean } = {}): Promise<void> {
    if (!opts.force && !autoPlayEnabled.value) {
      return;
    }

    let resolved: string;
    try {
      resolved = await verifyVoiceAudioReachable(url);
    } catch (e) {
      if (e instanceof Error) {
        throw e;
      }
      throw new Error(String(e));
    }

    return new Promise((resolve, reject) => {
      stopAudio();
      audioElement = new Audio(resolved);
      audioElement.onended = () => {
        isPlaying.value = false;
        resolve();
      };
      audioElement.onerror = () => {
        isPlaying.value = false;
        reject(
          new Error(
            '浏览器无法解码或加载该音频：若为相对路径请确认 VITE_API_BASE_URL 指向后端；若接口返回 502 则为 TTS 上游错误。',
          ),
        );
      };
      audioElement
        .play()
        .then(() => {
          isPlaying.value = true;
        })
        .catch((err) => {
          isPlaying.value = false;
          reject(err);
        });
    });
  }

  function stopAudio(): void {
    if (audioElement) {
      audioElement.pause();
      audioElement.currentTime = 0;
      audioElement = null;
    }
    isPlaying.value = false;
  }

  function toggleAutoPlay(): void {
    autoPlayEnabled.value = !autoPlayEnabled.value;
    if (!autoPlayEnabled.value) {
      stopAudio();
    }
  }

  return {
    isRecording,
    isPlaying,
    autoPlayEnabled,
    recordingDuration,
    startRecording,
    stopRecording,
    playAudio,
    verifyVoiceAudioReachable,
    stopAudio,
    toggleAutoPlay,
    onStopRecording,
  };
}

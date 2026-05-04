import { ref } from 'vue';

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

  const onStopRecording = ref<((blob: Blob) => void) | null>(null);

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
        isRecording.value = false;
        stopRecordingTimer();
        stream.getTracks().forEach((t) => t.stop());
        onStopRecording.value?.(blob);
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

  function playAudio(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!autoPlayEnabled.value) {
        resolve();
        return;
      }
      stopAudio();
      audioElement = new Audio(url);
      audioElement.onended = () => {
        isPlaying.value = false;
        resolve();
      };
      audioElement.onerror = () => {
        isPlaying.value = false;
        reject(new Error('Audio playback error'));
      };
      audioElement.play().then(() => {
        isPlaying.value = true;
      }).catch((err) => {
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
    stopAudio,
    toggleAutoPlay,
    onStopRecording,
  };
}

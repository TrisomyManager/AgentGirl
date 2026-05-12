export class AudioRecorder {
  private mediaRecorder?: MediaRecorder;
  private chunks: Blob[] = [];
  private isRecording = false;

  onDataAvailable?: (blob: Blob) => void;
  onStop?: (blob: Blob) => void;
  onError?: (err: Error) => void;

  async start(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      this.chunks = [];
      this.isRecording = true;

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          this.chunks.push(e.data);
          this.onDataAvailable?.(e.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: 'audio/webm' });
        this.isRecording = false;
        this.onStop?.(blob);
        // Stop all tracks to release microphone
        stream.getTracks().forEach((t) => t.stop());
      };

      this.mediaRecorder.onerror = (e) => {
        this.onError?.(new Error(`MediaRecorder error: ${e}`));
      };

      this.mediaRecorder.start(100); // collect in 100ms chunks
    } catch (err) {
      this.onError?.(err as Error);
    }
  }

  stop(): void {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
    }
  }

  get isActive(): boolean {
    return this.isRecording;
  }
}

export class AudioPlayer {
  private audio?: HTMLAudioElement;

  onEnded?: () => void;
  onError?: (err: Error) => void;

  play(url: string): void {
    this.stop();
    this.audio = new Audio(url);
    this.audio.onended = () => this.onEnded?.();
    this.audio.onerror = () => this.onError?.(new Error('Audio playback error'));
    this.audio.play().catch((err) => this.onError?.(err));
  }

  stop(): void {
    if (this.audio) {
      this.audio.pause();
      this.audio.currentTime = 0;
      this.audio = undefined;
    }
  }

  get isPlaying(): boolean {
    return this.audio ? !this.audio.paused : false;
  }
}

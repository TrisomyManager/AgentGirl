import { type ActionFrame, type ActionSequence, EmotionTag, ActionType } from './types';

export interface RenderFrame {
  imageUrl: string;
  lipShape?: string;
  durationMs: number;
  emotion: EmotionTag;
}

export class ActionRenderer {
  private container: HTMLElement;
  private currentTimeout?: ReturnType<typeof setTimeout>;
  private isPlaying = false;
  private frameQueue: RenderFrame[] = [];
  private currentIndex = 0;

  // Default placeholder URLs if no real frames provided
  private placeholderBase = '/assets/avatar';

  constructor(container: HTMLElement) {
    this.container = container;
  }

  setPlaceholderBase(url: string): void {
    this.placeholderBase = url;
  }

  playSequence(seq: ActionSequence): void {
    this.stop();
    this.frameQueue = seq.frames.map((f) => this.resolveFrame(f));
    this.currentIndex = 0;
    this.isPlaying = true;
    this.renderNext();
  }

  playIdle(): void {
    this.stop();
    const idleFrame: RenderFrame = {
      imageUrl: `${this.placeholderBase}/idle.png`,
      durationMs: 1000,
      emotion: EmotionTag.NEUTRAL,
    };
    this.frameQueue = [idleFrame];
    this.currentIndex = 0;
    this.isPlaying = true;
    this.renderNext();
  }

  playTalking(audioDurationMs: number, lipSyncFrames?: { shape: string; timeMs: number }[]): void {
    this.stop();
    // Generate talking frames for the duration of audio
    const frameDuration = 80; // ms per frame
    const totalFrames = Math.ceil(audioDurationMs / frameDuration);

    this.frameQueue = Array.from({ length: totalFrames }, (_, i) => {
      const timeMs = i * frameDuration;
      const lip = lipSyncFrames?.find((l) => l.timeMs >= timeMs && l.timeMs < timeMs + frameDuration);
      return {
        imageUrl: `${this.placeholderBase}/talk_${lip?.shape || 'rest'}.png`,
        lipShape: lip?.shape || 'rest',
        durationMs: frameDuration,
        emotion: EmotionTag.NEUTRAL,
      };
    });

    this.currentIndex = 0;
    this.isPlaying = true;
    this.renderNext();
  }

  stop(): void {
    this.isPlaying = false;
    if (this.currentTimeout) {
      clearTimeout(this.currentTimeout);
      this.currentTimeout = undefined;
    }
    this.frameQueue = [];
    this.currentIndex = 0;
  }

  private renderNext(): void {
    if (!this.isPlaying || this.currentIndex >= this.frameQueue.length) {
      if (this.isPlaying) {
        // Loop idle after sequence ends
        this.playIdle();
      }
      return;
    }

    const frame = this.frameQueue[this.currentIndex];
    this.renderFrame(frame);
    this.currentIndex++;

    this.currentTimeout = setTimeout(() => {
      this.renderNext();
    }, frame.durationMs);
  }

  private renderFrame(frame: RenderFrame): void {
    const img = this.container.querySelector('img');
    if (img) {
      img.src = frame.imageUrl;
      img.alt = `Companion ${frame.emotion}`;
    } else {
      const newImg = document.createElement('img');
      newImg.src = frame.imageUrl;
      newImg.alt = `Companion ${frame.emotion}`;
      newImg.style.width = '100%';
      newImg.style.height = '100%';
      newImg.style.objectFit = 'contain';
      this.container.innerHTML = '';
      this.container.appendChild(newImg);
    }
  }

  private resolveFrame(frame: ActionFrame): RenderFrame {
    // If the server provides a real image URL, use it
    if (frame.image_url) {
      return {
        imageUrl: frame.image_url,
        lipShape: frame.lip_shape,
        durationMs: frame.duration_ms,
        emotion: frame.emotion,
      };
    }

    // Otherwise use placeholder
    const emotionMap: Record<EmotionTag, string> = {
      [EmotionTag.NEUTRAL]: 'neutral',
      [EmotionTag.HAPPY]: 'happy',
      [EmotionTag.SAD]: 'sad',
      [EmotionTag.ANGRY]: 'angry',
      [EmotionTag.SURPRISED]: 'surprised',
      [EmotionTag.FEARFUL]: 'fearful',
      [EmotionTag.DISGUSTED]: 'disgusted',
      [EmotionTag.AFFECTIONATE]: 'affectionate',
      [EmotionTag.CONCERNED]: 'concerned',
      [EmotionTag.EXCITED]: 'excited',
      [EmotionTag.CALM]: 'calm',
    };

    const actionMap: Record<ActionType, string> = {
      [ActionType.IDLE]: 'idle',
      [ActionType.TALK]: 'talk',
      [ActionType.LISTEN]: 'listen',
      [ActionType.REACT_HAPPY]: 'react_happy',
      [ActionType.REACT_SAD]: 'react_sad',
      [ActionType.REACT_SURPRISED]: 'react_surprised',
      [ActionType.REACT_THINKING]: 'react_thinking',
      [ActionType.GESTURE_WAVE]: 'gesture_wave',
      [ActionType.GESTURE_NOD]: 'gesture_nod',
      [ActionType.GESTURE_HEAD_TILT]: 'gesture_head_tilt',
    };

    const emotionName = emotionMap[frame.emotion] || 'neutral';
    const actionName = actionMap[frame.action_type] || 'idle';

    return {
      imageUrl: `${this.placeholderBase}/${actionName}_${emotionName}.png`,
      lipShape: frame.lip_shape,
      durationMs: frame.duration_ms,
      emotion: frame.emotion,
    };
  }
}

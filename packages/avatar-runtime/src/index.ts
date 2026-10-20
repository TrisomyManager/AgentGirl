/** Pure playback/presentation runtime. No Vue, Live2D, networking or host state. */
export interface AvatarCue {
  offset_ms: number;
  emotion: string;
  intensity: number;
  gesture: 'idle' | 'nod' | 'tilt' | 'brighten';
}
export interface AvatarTimeline {
  version: 1;
  turn_id: string;
  segment_seq: number;
  duration_ms: number | null;
  clock: 'audio_playback';
  mouth_source: 'audio_rms';
  cues: AvatarCue[];
}
export interface AvatarFrame {
  active: boolean;
  emotion: string;
  intensity: number;
  gesture: AvatarCue['gesture'];
  mouthOpen: number;
  positionMs: number;
}
export const IDLE_FRAME: AvatarFrame = { active: false, emotion: 'neutral', intensity: .5, gesture: 'idle', mouthOpen: 0, positionMs: 0 };
const emotions = new Set(['neutral', 'calm', 'happy', 'excited', 'sad', 'angry', 'surprised', 'fearful', 'disgusted', 'affectionate', 'concerned']);
const gestures = new Set(['idle', 'nod', 'tilt', 'brighten']);
const clamp = (value: number) => Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));

/** Validate even saved/untrusted timeline data; malformed cues never touch a model. */
export function normalizeTimeline(input?: AvatarTimeline): AvatarCue[] {
  if (!input || input.version !== 1 || input.clock !== 'audio_playback' || !Array.isArray(input.cues)) return [];
  return input.cues.slice(0, 32).filter(cue => cue && Number.isInteger(cue.offset_ms) && cue.offset_ms >= 0 && cue.offset_ms <= 120000)
    .map(cue => ({ offset_ms: cue.offset_ms, emotion: emotions.has(cue.emotion) ? cue.emotion : 'neutral',
      intensity: clamp(cue.intensity), gesture: gestures.has(cue.gesture) ? cue.gesture : 'idle' as const }))
    .sort((a, b) => a.offset_ms - b.offset_ms);
}

export function rms(samples: Float32Array): number {
  let sum = 0;
  for (const sample of samples) sum += Number.isFinite(sample) ? sample * sample : 0;
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}

export function createAvatarClock(emit: (frame: AvatarFrame) => void) {
  let generation = 0, previousMs = 0, mouth = 0;
  let cues: AvatarCue[] = [];
  function begin(timeline?: AvatarTimeline) {
    generation++;
    previousMs = mouth = 0;
    cues = normalizeTimeline(timeline);
    // Receiving metadata never starts expression/mouth movement. Only sample() does.
    emit({ ...IDLE_FRAME });
    return generation;
  }
  function sample(token: number, positionMs: number, energy: number, playing = true) {
    if (token !== generation || !Number.isFinite(positionMs) || positionMs < 0) return;
    const cue = cues.filter(cue => cue.offset_ms <= positionMs).slice(-1)[0];
    const target = playing ? clamp((energy - .01) * 4) : 0;
    const dt = Math.min(100, Math.max(0, positionMs - previousMs));
    mouth += (target - mouth) * (1 - Math.exp(-dt / (target > mouth ? 35 : 85)));
    previousMs = positionMs;
    emit({ active: playing, emotion: cue?.emotion || 'neutral', intensity: cue?.intensity ?? .5,
      gesture: cue?.gesture || 'idle', mouthOpen: playing ? clamp(mouth) : 0, positionMs });
  }
  function stop(token: number) {
    if (token !== generation) return;
    generation++;
    mouth = 0;
    emit({ ...IDLE_FRAME });
  }
  return { begin, sample, stop };
}

/** Stable semantic mappings; only use expressions/motions that the loaded asset exposes. */
export function emotionPresentation(emotion: string) {
  const map: Record<string, { expression: string; motion: string; mouthForm: number }> = {
    happy: { expression: 'f04', motion: 'tap_body', mouthForm: .45 },
    excited: { expression: 'f04', motion: 'shake', mouthForm: .65 },
    affectionate: { expression: 'f04', motion: 'tap_body', mouthForm: .3 },
    sad: { expression: 'f02', motion: 'idle', mouthForm: -.45 },
    concerned: { expression: 'f02', motion: 'idle', mouthForm: -.2 },
    fearful: { expression: 'f02', motion: 'idle', mouthForm: -.3 },
    angry: { expression: 'f03', motion: 'pinch_in', mouthForm: -.4 },
    disgusted: { expression: 'f03', motion: 'pinch_in', mouthForm: -.3 },
    surprised: { expression: 'f04', motion: 'pinch_out', mouthForm: .1 },
  };
  return map[emotion] || { expression: 'f01', motion: 'idle', mouthForm: 0 };
}

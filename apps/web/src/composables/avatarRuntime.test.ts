import { describe, expect, it } from 'vitest';
import { createAvatarClock, IDLE_FRAME, normalizeTimeline, rms, type AvatarFrame, type AvatarTimeline } from '../../../../packages/avatar-runtime/src';

const timeline: AvatarTimeline = { version: 1, turn_id: 't', segment_seq: 0, duration_ms: 1200,
  clock: 'audio_playback', mouth_source: 'audio_rms', cues: [
    { offset_ms: 0, emotion: 'happy', intensity: .8, gesture: 'brighten' },
    { offset_ms: 700, emotion: 'concerned', intensity: .5, gesture: 'tilt' },
  ] };

describe('standalone presentation clock', () => {
  it('uses actual playback position and silence, never metadata arrival or a duration estimate', () => {
    const frames: AvatarFrame[] = [];
    const clock = createAvatarClock(frame => frames.push(frame));
    const token = clock.begin(timeline);
    expect(frames.slice(-1)[0]).toEqual(IDLE_FRAME);
    clock.sample(token, 200, .25);
    expect(frames.slice(-1)[0]?.emotion).toBe('happy');
    expect(frames.slice(-1)[0]?.mouthOpen).toBeGreaterThan(.5);
    clock.sample(token, 800, 0);
    expect(frames.slice(-1)[0]?.emotion).toBe('concerned');
    clock.sample(token, 1500, 0, false);
    expect(frames.slice(-1)[0]?.mouthOpen).toBe(0);
    expect(frames.slice(-1)[0]?.active).toBe(false);
  });
  it('discards late frames and stops from an old playback after a new segment begins', () => {
    let frame = { ...IDLE_FRAME };
    const clock = createAvatarClock(value => { frame = value; });
    const old = clock.begin(timeline), current = clock.begin(timeline);
    clock.sample(current, 200, .2);
    const expected = frame;
    clock.sample(old, 900, .8); clock.stop(old);
    expect(frame).toBe(expected);
    clock.stop(current);
    expect(frame).toEqual(IDLE_FRAME);
    clock.sample(current, 400, .2);
    expect(frame).toEqual(IDLE_FRAME);
  });
  it('sanitizes corrupted saved cues and computes energy from real samples', () => {
    const cues = normalizeTimeline({ ...timeline, cues: [
      { offset_ms: -1, emotion: 'happy', intensity: 1, gesture: 'nod' },
      { offset_ms: 0, emotion: '<script>', intensity: Infinity, gesture: 'run-shell' as any },
    ] });
    expect(cues).toEqual([{ offset_ms: 0, emotion: 'neutral', intensity: 0, gesture: 'idle' }]);
    expect(rms(new Float32Array([.5, -.5]))).toBe(.5);
    expect(rms(new Float32Array(0))).toBe(0);
  });
});

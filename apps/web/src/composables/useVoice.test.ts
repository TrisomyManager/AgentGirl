import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useVoice } from './useVoice';
import { avatarFrame } from './useAvatarPresentation';

describe('voice playback cancellation', () => {
  beforeEach(() => { vi.restoreAllMocks(); });
  afterEach(() => { vi.unstubAllGlobals(); });
  it('discards a pending microphone request after privacy cleanup and stops its tracks without transcribing', async () => {
    let permit!: (stream: unknown) => void;
    const track = { stop: vi.fn() };
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn(() => new Promise(resolve => { permit = resolve; })) } });
    const createRecorder = vi.fn(); vi.stubGlobal('MediaRecorder', createRecorder);
    const voice = useVoice(); voice.onStopRecording.value = vi.fn();
    const pending = voice.startRecording();
    voice.discardRecording(); permit({ getTracks: () => [track] }); await pending;
    expect(track.stop).toHaveBeenCalledOnce();
    expect(createRecorder).not.toHaveBeenCalled();
    expect(voice.onStopRecording.value).not.toHaveBeenCalled();
    expect(voice.isRecording.value).toBe(false);
  });
  it('drives mouth movement from playing audio and closes it on interruption, ignoring late animation frames', async () => {
    let tick!: FrameRequestCallback;
    vi.stubGlobal('requestAnimationFrame', vi.fn(callback => { tick = callback; return 1; }));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200 })));
    const close = vi.fn(async () => {});
    vi.stubGlobal('AudioContext', class {
      destination = {};
      resume = vi.fn(async () => {});
      close = close;
      createMediaElementSource() { return { connect() {}, disconnect() {} }; }
      createAnalyser() { return { fftSize: 256, disconnect() {}, getFloatTimeDomainData(samples: Float32Array) { samples.fill(.25); } }; }
    });
    const element = { currentTime: .2, paused: false, ended: false, pause: vi.fn(), play: vi.fn(async () => {}), onended: null, onerror: null };
    vi.stubGlobal('Audio', vi.fn(function () { return element; }));
    const voice = useVoice();
    const playing = voice.playAudio('/actual.mp3', { force: true });
    await flushPromises();
    expect(avatarFrame.value.active).toBe(false);
    tick(200);
    expect(avatarFrame.value.active).toBe(true);
    expect(avatarFrame.value.mouthOpen).toBeGreaterThan(.5);
    voice.stopAudio(); await playing;
    expect(avatarFrame.value.mouthOpen).toBe(0);
    tick(300);
    expect(avatarFrame.value.active).toBe(false);
    expect(close).toHaveBeenCalledOnce();
  });
  it('does not start an old sound when a delayed URL check finishes after stop', async () => {
    let finish!: (value: unknown) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve; })));
    const audio = vi.fn(); vi.stubGlobal('Audio', audio);
    const voice = useVoice();
    const pending = voice.playAudio('/late.mp3', { force: true });
    voice.stopAudio(); finish({ ok: true, status: 200 });
    await pending;
    expect(audio).not.toHaveBeenCalled();
  });

  it('settles playback when stopped so the caller never waits for an absent ended event', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200 })));
    const element = { pause: vi.fn(), play: vi.fn(async () => {}), currentTime: 0, onended: null, onerror: null };
    vi.stubGlobal('Audio', vi.fn(function () { return element; }));
    const voice = useVoice();
    const pending = voice.playAudio('/one.mp3', { force: true });
    await flushPromises(); voice.stopAudio(); await pending;
    expect(element.pause).toHaveBeenCalled(); expect(voice.isPlaying.value).toBe(false);
  });
});

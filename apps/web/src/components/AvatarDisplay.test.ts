import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref, nextTick } from 'vue';
import AvatarDisplay from './AvatarDisplay.vue';
import { avatarClock } from '../composables/useAvatarPresentation';

const renderer = vi.hoisted(() => ({ setExpression: vi.fn(), playMotion: vi.fn(), setPresentation: vi.fn() }));
vi.mock('../composables/useLive2D', () => ({ useLive2D: () => ({ ...renderer, isLoading: ref(false), error: ref(null),
  getMotionGroups: () => ['idle', 'tap_body', 'shake', 'pinch_in', 'pinch_out'],
}) }));
afterEach(() => { vi.clearAllMocks(); });

describe('Live2D emotion adapter', () => {
  it('sets real named asset expressions and returns to the base mood when audio is stopped', async () => {
    const wrapper = mount(AvatarDisplay, { props: { emotion: 'sad', emotionLabel: '难过', actionLabel: '', isTyping: false } });
    expect(renderer.setExpression).toHaveBeenLastCalledWith('f02');
    const token = avatarClock.begin({ version: 1, turn_id: 't', segment_seq: 0, duration_ms: null,
      clock: 'audio_playback', mouth_source: 'audio_rms', cues: [{ offset_ms: 0, emotion: 'happy', intensity: .8, gesture: 'brighten' }] });
    avatarClock.sample(token, 200, .25);
    await nextTick();
    expect(renderer.setExpression).toHaveBeenLastCalledWith('f04');
    expect(renderer.setPresentation.mock.calls.slice(-1)[0]?.[0].mouthOpen).toBeGreaterThan(.5);
    avatarClock.stop(token); await nextTick();
    expect(renderer.setExpression).toHaveBeenLastCalledWith('f02');
    expect(renderer.setPresentation.mock.calls.slice(-1)[0]?.[0].mouthOpen).toBe(0);
    wrapper.unmount();
  });
});

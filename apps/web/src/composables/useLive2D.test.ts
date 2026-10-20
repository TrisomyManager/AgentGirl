import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, h, ref } from 'vue';
import { useLive2D } from './useLive2D';

const renderer = vi.hoisted(() => ({ load: vi.fn(), add: vi.fn(), destroy: vi.fn() }));
vi.mock('pixi.js', () => ({ Application: class {
  view = document.createElement('canvas');
  renderer = { resize: vi.fn() };
  stage = { addChild: renderer.add };
  destroy = renderer.destroy;
} }));
vi.mock('pixi-live2d-display/cubism2', () => ({ Live2DModel: { from: renderer.load }, config: { sound: true } }));
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); delete (window as any).Live2D; });

describe('Live2D parameter adapter lifecycle', () => {
  it('applies smoothed speech parameters at the model update point and detaches on disposal', async () => {
    (window as any).Live2D = {};
    let update!: () => void;
    const core = { setParamFloat: vi.fn(), addToParamFloat: vi.fn() };
    const off = vi.fn();
    const model = { scale: { x: 1, set: vi.fn() }, getBounds: () => ({ x: 0, y: 0, width: 200, height: 300 }),
      x: 0, y: 0, on: vi.fn(), destroy: vi.fn(), internalModel: { coreModel: core,
        on: (_event: string, handler: () => void) => { update = handler; }, off },
    };
    renderer.load.mockResolvedValue(model);
    let api!: ReturnType<typeof useLive2D>;
    const wrapper = mount(defineComponent({ setup() {
      const el = ref<HTMLElement | null>(null);
      api = useLive2D(el, { modelPath: '/sample', width: 200, height: 300 });
      return () => h('div', { ref: el });
    } }));
    await flushPromises();
    api.setPresentation({ mouthOpen: 1, mouthForm: .6, angleZ: 20 });
    const now = performance.now();
    vi.spyOn(performance, 'now').mockReturnValue(now + 100);
    update();
    const mouth = core.setParamFloat.mock.calls.find(call => call[0] === 'PARAM_MOUTH_OPEN_Y')?.[1];
    expect(mouth).toBeGreaterThan(0);
    expect(mouth).toBeLessThan(1);
    expect(core.setParamFloat).toHaveBeenCalledWith('PARAM_MOUTH_FORM', expect.any(Number));
    const angle = core.addToParamFloat.mock.calls.find(call => call[0] === 'PARAM_ANGLE_Z')?.[1];
    expect(angle).toBeLessThanOrEqual(8);
    wrapper.unmount();
    expect(off).toHaveBeenCalledWith('beforeModelUpdate', update);
    expect(renderer.destroy).toHaveBeenCalledOnce();
  });
});

import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import ChatInput from './ChatInput.vue';

function input() {
  return mount(ChatInput, { props: { isLoading: false, voice: {
    isRecording: ref(false), recordingDuration: ref(0), startRecording: vi.fn(), stopRecording: vi.fn(),
  } as any } });
}
async function choose(wrapper: ReturnType<typeof input>, files: File[]) {
  const element = wrapper.find('input[type=file]').element;
  Object.defineProperty(element, 'files', { value: files, configurable: true });
  await wrapper.find('input[type=file]').trigger('change');
  await vi.waitFor(() => expect(wrapper.find('.send-btn').attributes('disabled')).toBeUndefined());
  await flushPromises();
}

describe('image messages', () => {
  it('previews/removes images and sends an image with no typed text', async () => {
    const wrapper = input();
    expect(wrapper.find('.send-btn').attributes('disabled')).toBeDefined();
    await choose(wrapper, [new File(['pixels'], 'red.png', { type: 'image/png' })]);
    expect(wrapper.find('.image-preview img').attributes('src')).toMatch(/^data:image\/png;base64,/);
    await wrapper.find('[aria-label="移除图片 1"]').trigger('click');
    expect(wrapper.find('.send-btn').attributes('disabled')).toBeDefined();
    await choose(wrapper, [new File(['pixels'], 'red.png', { type: 'image/png' })]);
    await wrapper.find('.send-btn').trigger('click');
    expect(wrapper.emitted('send')?.[0]).toEqual(['', { imageUrls: [expect.stringMatching(/^data:image\/png;base64,/)] }]);
    expect(wrapper.find('.image-preview').exists()).toBe(false);
    wrapper.unmount();
  });

  it('rejects unsupported types and excessive counts before reading', async () => {
    const wrapper = input();
    const element = wrapper.find('input[type=file]').element;
    Object.defineProperty(element, 'files', { value: [new File(['svg'], 'x.svg', { type: 'image/svg+xml' })], configurable: true });
    await wrapper.find('input[type=file]').trigger('change');
    expect(wrapper.find('[role=alert]').text()).toContain('JPEG');
    Object.defineProperty(element, 'files', { value: Array.from({ length: 4 }, () => new File(['p'], 'x.png', { type: 'image/png' })), configurable: true });
    await wrapper.find('input[type=file]').trigger('change');
    expect(wrapper.find('[role=alert]').text()).toContain('3');
    expect(wrapper.find('.image-preview').exists()).toBe(false);
    wrapper.unmount();
  });

  it('aborts readers on unmount and discards late file events', async () => {
    let reader: any;
    const abort = vi.fn();
    vi.stubGlobal('FileReader', class {
      constructor() { reader = this; }
      readAsDataURL() {}
      abort = abort;
      result = 'data:image/png;base64,cGl4ZWxz';
    });
    try {
      const wrapper = input();
      const element = wrapper.find('input[type=file]').element;
      Object.defineProperty(element, 'files', { value: [new File(['p'], 'x.png', { type: 'image/png' })] });
      await wrapper.find('input[type=file]').trigger('change');
      wrapper.unmount();
      expect(abort).toHaveBeenCalledOnce();
      reader.onload();
      await flushPromises();
      expect(wrapper.emitted('send')).toBeUndefined();
    } finally { vi.unstubAllGlobals(); }
  });
});

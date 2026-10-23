import { defineComponent } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { useProactivePush } from './useProactivePush';

beforeEach(() => { localStorage.clear(); });
afterEach(() => { vi.unstubAllGlobals(); });

test('SSE and polling deliver one proactive message per event id, also across reloads', async () => {
  localStorage.setItem('companion_push_since_alice', '0');
  const payload = { id: 'event-1', user_id: 'alice', message: '记得休息一下', trigger_type: 'desktop_context' };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    if (input.includes('/poll?')) return new Response(JSON.stringify({ latest_seq: 1,
      events: [{ kind: 'proactive_message', payload }] }));
    const stream = new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode(`event: proactive_message\ndata: ${JSON.stringify(payload)}\n\n`));
      options?.signal?.addEventListener('abort', () => controller.close());
    } });
    return new Response(stream);
  }));
  const received = vi.fn();
  const component = defineComponent({ setup() { useProactivePush('alice', { onProactiveMessage: received });
    return () => null; } });
  let view = mount(component);
  await flushPromises();
  expect(received).toHaveBeenCalledTimes(1);
  view.unmount();
  view = mount(component);
  await flushPromises();
  expect(received).toHaveBeenCalledTimes(1);
  view.unmount();
});

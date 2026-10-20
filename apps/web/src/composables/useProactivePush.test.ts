import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { pushEventIdentity, useProactivePush } from './useProactivePush';

beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    clear: () => storage.clear(),
  });
});

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); Reflect.deleteProperty(window, 'electronAPI'); });

describe('reliable proactive delivery', () => {
  it('lets the native host decide background visibility and sends each event once', async () => {
    const background = vi.fn(), legacy = vi.fn();
    Object.defineProperty(window, 'electronAPI', { configurable: true, value: { showBackgroundNotification: background, showNotification: legacy } });
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    const event = { kind: 'reminder_fired', payload: { id: 'r', event_id: 'one', user_id: 'u', text: '休息一下' } };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('/push?')
      ? new Response(`event: reminder_fired\ndata: ${JSON.stringify(event.payload)}\n\n`)
      : Response.json({ durable: true, latest_seq: 1, events: [event] })));
    const wrapper = mount(defineComponent({ setup: () => useProactivePush('u'), template: '<div />' }));
    await flushPromises();
    expect(background).toHaveBeenCalledTimes(1);
    expect(background).toHaveBeenCalledWith('小暖提醒你', '休息一下');
    expect(legacy).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it('recovers offline events on first load and deduplicates SSE plus polling', async () => {
    const message = { id: 'care-1', event_id: 'event-1', user_id: 'u', message: '休息一下', trigger_type: 'idle_checkin', timestamp: '' };
    const onMessage = vi.fn();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/push?')) {
        return new Response(`event: proactive_message\ndata: ${JSON.stringify(message)}\n\n`, { status: 200 });
      }
      return Response.json({ durable: true, latest_seq: 1, events: [{ kind: 'proactive_message', payload: message }] });
    }));
    const component = defineComponent({
      setup() { return useProactivePush('u', { onProactiveMessage: onMessage }); },
      template: '<div />',
    });
    const wrapper = mount(component);
    await flushPromises();
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('companion_push_since_v2_u')).toBe('1');
    wrapper.unmount();
  });

  it('delivers each repeating occurrence and drains every history page', async () => {
    let page = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/push?')) return new Response('event: hello\ndata: {}\n\n');
      page++;
      return Response.json({
        durable: true, latest_seq: page, has_more: page === 1,
        events: [{ kind: 'reminder_fired', payload: { id: 'same-reminder', event_id: `occurrence-${page}`, user_id: 'u', text: '喝水', fire_at: `time-${page}` } }],
      });
    }));
    const component = defineComponent({ setup() { return useProactivePush('u'); }, template: '<div />' });
    const wrapper = mount(component);
    await flushPromises();
    expect(page).toBe(2);
    expect(wrapper.vm.events).toHaveLength(2);
    expect(wrapper.vm.lastReminder?.event_id).toBe('occurrence-2');
    wrapper.unmount();
  });

  it('identifies legacy repeating reminders by their occurrence time', () => {
    expect(pushEventIdentity('reminder_fired', { id: 'r', fire_at: 'a' }))
      .not.toBe(pushEventIdentity('reminder_fired', { id: 'r', fire_at: 'b' }));
  });
});

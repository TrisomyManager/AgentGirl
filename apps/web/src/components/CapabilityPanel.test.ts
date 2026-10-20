import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import CapabilityPanel from './CapabilityPanel.vue';

const api = vi.hoisted(() => ({
  getCapabilities: vi.fn(async () => [{ id: 'remind', title: '提醒', group: '生活助手', status: 'ready', description: '', examples: [] }]),
  getUserState: vi.fn(async () => ({ reminders: { upcoming: [], recent: [] }, proactive: { rules: [
    { id: 'morning_greeting', title: '早晨问候', enabled: true, schedule: '每天' },
  ] } })),
  getCarePreferences: vi.fn(async () => ({
    enabled: true, idle_checkin: true, morning_greeting: true, evening_greeting: true, memory_followup: true,
    timezone: 'Asia/Shanghai', dnd_start_hour: 22, dnd_end_hour: 7, max_per_day: 3, cooldown_minutes: 60,
  })),
  saveCarePreferences: vi.fn(async (_userId: string, preferences: any) => preferences),
  cancelReminder: vi.fn(),
  getTasks: vi.fn(async () => []),
  cancelTask: vi.fn(),
  resumeTask: vi.fn(),
}));

vi.mock('../composables/useApi', () => ({ useApi: () => api }));

describe('care settings', () => {
  it('loads capabilities when the previously hidden panel opens', async () => {
    const wrapper = mount(CapabilityPanel, { props: { visible: false, userId: 'u' } });
    await wrapper.setProps({ visible: true });
    await flushPromises();
    expect(wrapper.text()).toContain('提醒');
    wrapper.unmount();
  });

  it('saves rule changes and frequency preferences for the current user', async () => {
    const wrapper = mount(CapabilityPanel, { props: { visible: true, userId: 'u' } });
    await wrapper.findAll('button').find(button => button.text() === '我的事项')!.trigger('click');
    await flushPromises();
    await wrapper.findAll('input[type="checkbox"]')[1].setValue(false);
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(api.saveCarePreferences).toHaveBeenLastCalledWith('u', expect.objectContaining({ morning_greeting: false }));
    expect(wrapper.text()).toContain('已保存');
    wrapper.unmount();
  });
});

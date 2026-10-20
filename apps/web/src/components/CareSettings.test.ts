import { beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import CareSettings from './CareSettings.vue';
const api = vi.hoisted(() => ({ getCarePreferences: vi.fn(), saveCarePreferences: vi.fn() }));
vi.mock('../composables/useApi', () => ({ useApi: () => api }));
const preferences = (limit: number) => ({ enabled: true, idle_checkin: true, morning_greeting: true,
  evening_greeting: true, memory_followup: true, timezone: 'Asia/Shanghai', dnd_start_hour: 22,
  dnd_end_hour: 7, cooldown_minutes: 60, max_per_day: limit });
beforeEach(() => vi.resetAllMocks());

it('discards late preferences from a previous account', async () => {
  let resolve!: (value: unknown) => void;
  api.getCarePreferences.mockImplementationOnce(() => new Promise(r => { resolve = r; }))
    .mockResolvedValueOnce(preferences(2));
  const wrapper = mount(CareSettings, { props: { userId: 'alice' } });
  await wrapper.setProps({ userId: 'bob' });
  await flushPromises();
  resolve(preferences(19));
  await flushPromises();
  const limit = wrapper.findAll('input[type=number]')[2].element as HTMLInputElement;
  expect(limit.value).toBe('2');
  wrapper.unmount();
});

it('retains edits after a failed save and does not emit success', async () => {
  api.getCarePreferences.mockResolvedValue(preferences(4));
  api.saveCarePreferences.mockRejectedValue(new Error('unavailable'));
  const wrapper = mount(CareSettings, { props: { userId: 'alice' } });
  await flushPromises();
  await wrapper.findAll('input[type=number]')[2].setValue(3);
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(wrapper.find('[role="alert"]').text()).toContain('保存陪伴设置失败');
  expect((wrapper.findAll('input[type=number]')[2].element as HTMLInputElement).value).toBe('3');
  expect(wrapper.emitted('saved')).toBeUndefined();
  wrapper.unmount();
});

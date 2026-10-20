import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import SettingsDrawer from './SettingsDrawer.vue';
import { accessState } from '../composables/accessSession';

const api = vi.hoisted(() => ({ getLlmConfig: vi.fn(), getVoiceConfig: vi.fn(), saveLlmConfig: vi.fn(),
  saveVoiceConfig: vi.fn(), testLlmConfig: vi.fn(), testVoiceConfig: vi.fn() }));
vi.mock('../composables/useApi', () => ({ useApi: () => api }));
vi.mock('../composables/useRealtimeVoice', async () => { const { ref } = await import('vue'); return {
  currentAudioFormat: ref('pcm'), currentRealtimeProvider: ref('volc_realtime'), currentSampleRate: ref(24000),
}; });
const config = { provider: 'volcengine', base_url: 'https://ark.cn-beijing.volces.com/api/v3', model: 'test-model', api_key_set: true };
const options = { props: { visible: true, userName: '用户', userId: 'operator', sessionId: 's', serverAvailable: true },
  global: { stubs: { teleport: true, transition: true, ConversationSettings: true, PrivacyControls: true, AdminPanel: true, CareSettings: true } } };
beforeEach(() => { vi.resetAllMocks(); api.getLlmConfig.mockResolvedValue(config); Object.assign(accessState, { role: 'admin', userId: 'operator' }); });
afterEach(() => vi.restoreAllMocks());

it('keeps personal controls separate and wipes unsaved secrets when the drawer closes', async () => {
  const wrapper = mount(SettingsDrawer, options);
  expect(wrapper.text()).toContain('用户昵称');
  expect(wrapper.find('input[type=password]').exists()).toBe(false);
  await wrapper.findAll('nav button').find(b => b.text() === '模型服务')!.trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('LLM 配置');
  await wrapper.find('input[type=password]').setValue('synthetic-only-secret');
  await wrapper.setProps({ visible: false });
  await wrapper.setProps({ visible: true });
  await flushPromises();
  expect((wrapper.find('input[type=password]').element as HTMLInputElement).value).toBe('');
  expect(wrapper.html()).not.toContain('synthetic-only-secret');
  wrapper.unmount();
});

it('ignores a delayed save after losing management permission', async () => {
  let resolve!: (value: unknown) => void;
  api.saveLlmConfig.mockImplementation(() => new Promise(r => { resolve = r; }));
  const wrapper = mount(SettingsDrawer, options);
  await wrapper.findAll('nav button').find(b => b.text() === '模型服务')!.trigger('click');
  await flushPromises();
  await wrapper.findAll('button').find(b => b.text() === '保存并生效')!.trigger('click');
  accessState.role = 'user';
  await flushPromises();
  resolve({ ok: true, config: { ...config, model: 'previous-account-model' } });
  await flushPromises();
  expect(wrapper.text()).toContain('用户昵称');
  expect(wrapper.text()).not.toContain('previous-account-model');
  expect(wrapper.text()).not.toContain('模型服务');
  expect(wrapper.text()).not.toContain('已保存，下一条');
  wrapper.unmount();
});

it('blocks editing an unavailable configuration and allows a successful retry', async () => {
  api.getLlmConfig.mockResolvedValueOnce(null).mockResolvedValue(config);
  const wrapper = mount(SettingsDrawer, options);
  await wrapper.findAll('nav button').find(b => b.text() === '模型服务')!.trigger('click');
  await flushPromises();
  expect(wrapper.find('[role="alert"]').text()).toContain('暂时不能保存');
  expect(wrapper.find('fieldset').attributes('disabled')).toBeDefined();
  await wrapper.findAll('button').find(b => b.text() === '重新加载配置')!.trigger('click');
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  expect(wrapper.find('fieldset').attributes('disabled')).toBeUndefined();
  wrapper.unmount();
});

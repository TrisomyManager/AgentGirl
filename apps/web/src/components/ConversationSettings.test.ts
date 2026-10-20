import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import ConversationSettings from './ConversationSettings.vue';

const api = vi.hoisted(() => ({ getConversationPreferences: vi.fn(), saveConversationPreferences: vi.fn() }));
vi.mock('../composables/useApi', () => ({ useApi: () => api }));

beforeEach(() => {
  vi.resetAllMocks();
  api.getConversationPreferences.mockResolvedValue({ natural_reply_enabled: false, acknowledgement_reply_probability: .35 });
  api.saveConversationPreferences.mockImplementation(async (_user, preferences) => preferences);
});

describe('conversation pacing controls', () => {
  it('loads saved preferences and saves the user choice to the same account', async () => {
    const wrapper = mount(ConversationSettings, { props: { userId: 'user-a' } });
    await flushPromises();
    expect(wrapper.find('input[type=range]').attributes('disabled')).toBeDefined();
    await wrapper.find('input[type=checkbox]').setValue(true);
    await wrapper.find('input[type=range]').setValue('0.2');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(api.saveConversationPreferences).toHaveBeenCalledWith('user-a', {
      natural_reply_enabled: true, acknowledgement_reply_probability: .2,
    });
    expect(wrapper.text()).toContain('已保存');
    wrapper.unmount();
  });

  it('does not overwrite a different account with a late settings response', async () => {
    let resolveOld!: (value: unknown) => void;
    api.getConversationPreferences.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    const wrapper = mount(ConversationSettings, { props: { userId: 'user-a' } });
    await wrapper.setProps({ userId: 'user-b' });
    await flushPromises();
    resolveOld({ natural_reply_enabled: true, acknowledgement_reply_probability: 0 });
    await flushPromises();
    expect((wrapper.find('input[type=checkbox]').element as HTMLInputElement).checked).toBe(false);
    expect(wrapper.text()).toContain('35%');
    wrapper.unmount();
  });

  it('keeps controls unavailable until settings load and offers a retry after failure', async () => {
    api.getConversationPreferences.mockRejectedValueOnce(new Error('暂时无法连接'));
    const wrapper = mount(ConversationSettings, { props: { userId: 'user-a' } });
    await flushPromises();
    expect(wrapper.find('form').exists()).toBe(false);
    expect(wrapper.get('[role=alert]').text()).toContain('暂时无法连接');
    await wrapper.find('button').trigger('click');
    await flushPromises();
    expect(wrapper.find('form').exists()).toBe(true);
    wrapper.unmount();
  });
});

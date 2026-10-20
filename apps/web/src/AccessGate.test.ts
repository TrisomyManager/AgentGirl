import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import AccessGate from './AccessGate.vue';
import { accessState } from './composables/accessSession';

const api = vi.hoisted(() => ({ check: vi.fn(), login: vi.fn() }));
vi.mock('./App.vue', () => ({ default: { template: '<div data-private-app>private workspace</div>' } }));
vi.mock('./composables/accessSession', async () => {
  const { reactive } = await import('vue');
  return { accessState: reactive({ mode: 'key', authenticated: false, error: '' }), checkAccess: api.check, loginAccess: api.login };
});
beforeEach(() => { vi.resetAllMocks(); Object.assign(accessState, { mode: 'key', authenticated: false, error: '' }); });

it('does not mount protected content while authentication is still loading', async () => {
  let finish!: () => void;
  api.check.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
  const wrapper = mount(AccessGate);
  expect(wrapper.find('[data-private-app]').exists()).toBe(false);
  accessState.authenticated = true; finish(); await flushPromises();
  expect(wrapper.find('[data-private-app]').exists()).toBe(true); wrapper.unmount();
});

it('erases a submitted access key after failed login and never displays private content', async () => {
  api.check.mockResolvedValueOnce(undefined); api.login.mockRejectedValueOnce(new Error('无效密钥'));
  const wrapper = mount(AccessGate); await flushPromises();
  await wrapper.get('input').setValue('temporary-host-key');
  await wrapper.get('form').trigger('submit'); await flushPromises();
  expect(api.login).toHaveBeenCalledWith('temporary-host-key');
  expect((wrapper.get('input').element as HTMLInputElement).value).toBe('');
  expect(wrapper.get('[role=alert]').text()).toBe('无效密钥');
  expect(wrapper.find('[data-private-app]').exists()).toBe(false); wrapper.unmount();
});

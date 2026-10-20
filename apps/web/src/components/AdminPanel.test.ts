import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import AdminPanel from './AdminPanel.vue';
import { accessState } from '../composables/accessSession';

const entry = { id: 'text_tools', name: '文本小工具', version: '1.0.0', sha256: 'a'.repeat(64),
  description: '统计文章篇幅', permissions: '纯本地计算', installed: false, runtime_status: 'not_installed' };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => { Object.assign(accessState, { role: 'admin', userId: 'operator', authenticated: true }); });
afterEach(() => { vi.unstubAllGlobals(); });

it('requires explicit review before installing and refreshes actual disabled status', async () => {
  let installed = false;
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === 'POST') { installed = true; return json({ status: 'installed' }, 201); }
    if (url.endsWith('/catalog')) return json({ installation_enabled: true, entries: [{ ...entry, installed, runtime_status: installed ? 'disabled' : 'not_installed' }] });
    return json({ plugins: installed ? [{ id: entry.id, name: entry.name, status: 'disabled' }] : [] });
  });
  vi.stubGlobal('fetch', fetch);
  const wrapper = mount(AdminPanel, { props: { section: 'extensions' } });
  await flushPromises();
  await wrapper.findAll('button').find(b => b.text() === '查看并安装')!.trigger('click');
  expect(fetch.mock.calls.some(call => call[1]?.method === 'POST')).toBe(false);
  expect(wrapper.find('[role="dialog"]').text()).toContain('不更改宿主授权');
  await wrapper.findAll('button').find(b => b.text() === '确认安装')!.trigger('click');
  await flushPromises();
  const call = fetch.mock.calls.find(call => call[1]?.method === 'POST')!;
  expect(JSON.parse(call[1]?.body as string)).toEqual({ sha256: entry.sha256 });
  expect(wrapper.text()).toContain('已安装，未启用');
  expect(wrapper.text()).toContain('已安装；执行权限仍由宿主授权。');
  wrapper.unmount();
});

it('does not request admin data as a user and rejects stale responses after role changes', async () => {
  let resolve!: (value: Response) => void;
  const fetch = vi.fn(() => new Promise<Response>(r => { resolve = r; }));
  vi.stubGlobal('fetch', fetch);
  const wrapper = mount(AdminPanel, { props: { section: 'overview' } });
  accessState.role = 'user';
  await flushPromises();
  resolve(json({ ready: true, modules: { secret_module: 'ready' }, storage_mode: 'sqlite', access_mode: 'key' }));
  await flushPromises();
  expect(wrapper.text()).not.toContain('secret_module');
  expect(wrapper.text()).not.toContain('运行中');
  const calls = fetch.mock.calls.length;
  await wrapper.find('button').trigger('click');
  expect(fetch.mock.calls.length).toBe(calls);
  wrapper.unmount();
});

it('shows a failed request without retaining old installation controls', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({}, 503)));
  const wrapper = mount(AdminPanel, { props: { section: 'extensions' } });
  await flushPromises();
  expect(wrapper.find('[role="alert"]').text()).toContain('请求失败');
  expect(wrapper.text()).not.toContain('查看并安装');
  wrapper.unmount();
});

it('shows actual platform connection states without offering to grant a destination', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ ready: true, modules: {}, storage_mode: 'sqlite', access_mode: 'key',
    platforms: { state: 'enabled', accounts: [
      { id: 'test-telegram', platform: 'telegram', receive_state: 'connected', reply: true },
      { id: 'test-qq', platform: 'qq', receive_state: 'waiting_callback', reply: false },
    ] } })));
  const wrapper = mount(AdminPanel, { props: { section: 'overview' } });
  await flushPromises();
  expect(wrapper.text()).toContain('test-telegram');
  expect(wrapper.text()).toContain('已连接 · 可回复');
  expect(wrapper.text()).toContain('等待平台回调 · 回复关闭');
  expect(wrapper.findAll('input')).toHaveLength(0);
  wrapper.unmount();
});

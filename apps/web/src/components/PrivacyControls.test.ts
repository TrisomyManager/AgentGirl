import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import PrivacyControls from './PrivacyControls.vue';

const api = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../composables/accessSession', () => ({ ACCESS_API_BASE: 'http://test', apiFetch: api.fetch }));
beforeEach(() => { vi.resetAllMocks(); api.fetch.mockResolvedValueOnce(Response.json({ status: 'none' })); });

it('requires the exact confirmation, stops work first, and retains pending cleanup until a successful retry', async () => {
  const wrapper = mount(PrivacyControls, { props: { userId: 'alice' } });
  await flushPromises();
  const submit = () => wrapper.find('form').trigger('submit');
  await wrapper.find('input').setValue('yes'); await submit();
  expect(api.fetch).toHaveBeenCalledTimes(1);
  await wrapper.find('input').setValue('删除我的全部数据');
  api.fetch.mockImplementationOnce(async (_url, options) => {
    expect(wrapper.emitted('clearing')?.[0]).toEqual([true]);
    expect(JSON.parse(options.body).confirmation).toBe('删除我的全部数据');
    return Response.json({ status: 'pending', pending: ['voice_files'] }, { status: 202 });
  });
  await submit(); await flushPromises();
  expect(wrapper.text()).toContain('部分清理尚未完成');
  expect(wrapper.text()).not.toContain('服务端数据已清理');
  expect(wrapper.emitted('cleared')).toHaveLength(1);
  await wrapper.find('input').setValue('删除我的全部数据');
  api.fetch.mockResolvedValueOnce(Response.json({ status: 'completed', pending: [] }));
  await submit(); await flushPromises();
  expect(api.fetch.mock.calls[2][0]).toBe('http://test/privacy/user/alice/erase');
  expect(wrapper.text()).toContain('服务端数据已清理'); wrapper.unmount();
});

it('does not claim completion or clear cached history when the response is lost', async () => {
  const wrapper = mount(PrivacyControls, { props: { userId: 'alice' } });
  await flushPromises();
  await wrapper.find('input').setValue('删除我的全部数据');
  api.fetch.mockRejectedValueOnce(new Error('连接中断'));
  await wrapper.find('form').trigger('submit'); await flushPromises();
  expect(wrapper.get('[role=alert]').text()).toContain('连接中断');
  expect(wrapper.emitted('cleared')).toBeUndefined();
  expect(wrapper.emitted('clearing')).toEqual([[true]]); wrapper.unmount();
});

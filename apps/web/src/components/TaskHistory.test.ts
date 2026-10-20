import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TaskHistory from './TaskHistory.vue';

const api = vi.hoisted(() => ({ getTasks: vi.fn(), cancelTask: vi.fn(), resumeTask: vi.fn() }));
vi.mock('../composables/useApi', () => ({ useApi: () => api }));
function run(status = 'awaiting_input') {
  return { id: 'task-1', request: '先看时间，再提醒我', status, message: '提醒什么？', steps: [
    { position: 0, tool_name: 'get_time', status: 'success', result: { message: '现在是 12:00' } },
  ] };
}

describe('task history', () => {
  beforeEach(() => { vi.resetAllMocks(); api.getTasks.mockResolvedValue([run()]); });

  it('shows actual completed steps and resumes with clarification for the current user', async () => {
    api.resumeTask.mockResolvedValue(undefined);
    const wrapper = mount(TaskHistory, { props: { userId: 'owner' } });
    await flushPromises();
    expect(wrapper.text()).toContain('现在是 12:00');
    expect(wrapper.text()).toContain('等待补充');
    await wrapper.find('input').setValue('十分钟后喝水');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(api.resumeTask).toHaveBeenCalledWith('task-1', 'owner', '十分钟后喝水');
    expect(wrapper.emitted('changed')).toHaveLength(1);
    wrapper.unmount();
  });

  it('cancels only the selected task and reloads receipts', async () => {
    api.cancelTask.mockResolvedValue(undefined);
    const wrapper = mount(TaskHistory, { props: { userId: 'owner' } });
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === '停止任务')!.trigger('click');
    await flushPromises();
    expect(api.cancelTask).toHaveBeenCalledWith('task-1', 'owner');
    expect(api.getTasks).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it('clears previous user tasks and ignores late results after an owner change', async () => {
    let finish!: (value: unknown[]) => void;
    api.getTasks.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue([]);
    const wrapper = mount(TaskHistory, { props: { userId: 'first' } });
    await wrapper.setProps({ userId: 'second' });
    await flushPromises();
    finish([run()]);
    await flushPromises();
    expect(wrapper.text()).not.toContain('现在是 12:00');
    expect(api.getTasks).toHaveBeenLastCalledWith('second');
    wrapper.unmount();
  });
});

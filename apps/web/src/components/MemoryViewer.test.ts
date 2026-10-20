import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import MemoryViewer from './MemoryViewer.vue';

const api = vi.hoisted(() => ({
  listMemories: vi.fn(async () => [{ entry_id: 'old', category: 'fact', content: '一条旧记忆', importance: .3, effective_importance: .05, memory_status: 'dormant' }]),
  getMemorySummary: vi.fn(async () => ({ total_memories: 1, avg_importance: .3, by_category: { fact: 1 } })),
  recallMemory: vi.fn(async () => ({ entries: [] })),
  deleteMemory: vi.fn(), deleteAllMemories: vi.fn(),
  restoreMemory: vi.fn(async () => true),
  consolidateMemories: vi.fn(async () => ({ status: 'updated' })),
  listDailySummaries: vi.fn(async (): Promise<any[]> => []),
}));

vi.mock('../composables/useApi', () => ({ useApi: () => api }));
afterEach(() => vi.unstubAllGlobals());

function mountViewer() {
  return mount(MemoryViewer, { props: { visible: true, userId: 'u' }, global: { stubs: { teleport: true } } });
}

describe('memory review controls', () => {
  it('shows faded memories and lets the user restore them', async () => {
    const wrapper = mountViewer();
    await flushPromises();
    expect(wrapper.text()).toContain('已淡化');
    await wrapper.findAll('button').find(button => button.text() === '重新记住')!.trigger('click');
    await flushPromises();
    expect(api.restoreMemory).toHaveBeenLastCalledWith('u', 'old');
    expect(wrapper.text()).toContain('已重新记住');
    wrapper.unmount();
  });

  it('shows an empty search result instead of showing unrelated original memories', async () => {
    const wrapper = mountViewer();
    await flushPromises();
    await wrapper.find('.search-row input').setValue('不存在的话题');
    await wrapper.find('.search-btn').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('未找到相关记忆');
    expect(wrapper.text()).not.toContain('一条旧记忆');
    wrapper.unmount();
  });

  it('shows the saved daily recap after manual consolidation', async () => {
    const wrapper = mountViewer();
    await flushPromises();
    api.listDailySummaries.mockResolvedValueOnce([{ day: '2026-10-19', summary: '今天在准备面试', method: 'extractive' }]);
    await wrapper.findAll('button').find(button => button.text() === '整理今天的记忆')!.trigger('click');
    await flushPromises();
    expect(api.consolidateMemories).toHaveBeenCalledWith('u');
    expect(wrapper.text()).toContain('今天在准备面试');
    expect(wrapper.text()).toContain('对话摘录');
    wrapper.unmount();
  });

  it('does not restore stale search results after the user clears the memory library', async () => {
    let resolveSearch!: (result: any) => void;
    api.recallMemory.mockImplementationOnce(() => new Promise(resolve => { resolveSearch = resolve; }));
    api.deleteAllMemories.mockResolvedValueOnce(true);
    vi.stubGlobal('confirm', () => true);
    const wrapper = mountViewer();
    await flushPromises();
    await wrapper.find('.search-row input').setValue('旧记忆');
    await wrapper.find('.search-btn').trigger('click');
    await wrapper.find('.danger-btn').trigger('click');
    await flushPromises();
    resolveSearch({ entries: [{ entry_id: 'old', content: '不应重新出现的旧信息', category: 'fact', importance: .5 }] });
    await flushPromises();
    expect(wrapper.text()).not.toContain('不应重新出现的旧信息');
    expect(wrapper.text()).toContain('记忆库和对话回顾已清空');
    wrapper.unmount();
  });

  it('keeps external cleanup pending visible after a refresh', async () => {
    api.deleteAllMemories.mockResolvedValueOnce('pending');
    vi.stubGlobal('confirm', () => true);
    const wrapper = mountViewer();
    await flushPromises();
    await wrapper.find('.danger-btn').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('外部关联信息仍待清理');
    api.getMemorySummary.mockResolvedValueOnce({ total_memories: 0, external_graph_cleanup_pending: true } as any);
    await wrapper.findAll('button').find(button => button.text().includes('刷新'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('外部关联信息仍待清理');
    wrapper.unmount();
  });

  it('discards a clear response after switching users', async () => {
    let finish!: (result: any) => void;
    api.deleteAllMemories.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    vi.stubGlobal('confirm', () => true);
    const wrapper = mountViewer();
    await flushPromises();
    await wrapper.find('.danger-btn').trigger('click');
    await wrapper.setProps({ userId: 'another-user' });
    await flushPromises();
    finish('completed');
    await flushPromises();
    expect(wrapper.text()).toContain('一条旧记忆');
    expect(wrapper.text()).not.toContain('记忆库和对话回顾已清空');
    wrapper.unmount();
  });

  it('shows pending single-delete cleanup and resolves it on refresh', async () => {
    vi.stubGlobal('confirm', () => true);
    api.deleteMemory.mockResolvedValueOnce(true);
    const wrapper = mountViewer();
    await flushPromises();
    api.getMemorySummary.mockResolvedValueOnce({ total_memories: 0, external_graph_cleanup_pending: true } as any);
    await wrapper.find('.del-btn').trigger('click');
    await flushPromises();
    expect(wrapper.text()).not.toContain('一条旧记忆');
    expect(wrapper.text()).toContain('记忆已删除，外部关联信息仍待清理');
    api.listMemories.mockResolvedValueOnce([]);
    api.getMemorySummary.mockResolvedValueOnce({ total_memories: 0, external_graph_cleanup_pending: false } as any);
    await wrapper.findAll('button').find(button => button.text().includes('刷新'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('外部关联信息已清理');
    expect(wrapper.text()).not.toContain('仍待清理');
    wrapper.unmount();
  });

  it('discards a single-delete response after switching users', async () => {
    let finish!: (result: boolean) => void;
    api.deleteMemory.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    vi.stubGlobal('confirm', () => true);
    const wrapper = mountViewer();
    await flushPromises();
    await wrapper.find('.del-btn').trigger('click');
    await wrapper.setProps({ userId: 'another-user' });
    await flushPromises();
    finish(true);
    await flushPromises();
    expect(wrapper.text()).toContain('一条旧记忆');
    wrapper.unmount();
  });
});

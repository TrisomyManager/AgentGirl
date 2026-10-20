import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MemoryGraph from './MemoryGraph.vue';
import type { MemoryGraphData } from '../composables/useApi';

const api = vi.hoisted(() => ({ getMemoryGraph: vi.fn() }));
vi.mock('../composables/useApi', () => ({ useApi: () => api }));
const graph: MemoryGraphData = {
  nodes: [{ id: 'm:one', kind: 'memory', label: '我的旅行约定', content: '打算去杭州旅行', memory_id: 'one', status: 'active' },
    { id: 'e:city', kind: 'entity', label: '杭州' }, { id: 'e:key', kind: 'keyword', label: '旅行' }],
  edges: [{ source: 'm:one', target: 'e:city', kind: 'mentions', label: '提及', memory_ids: ['one'] },
    { source: 'm:one', target: 'e:key', kind: 'mentions', label: '提及', memory_ids: ['one'] }],
  memory_count: 1, truncated: false, source: 'sql_index',
};
afterEach(() => vi.resetAllMocks());

describe('memory network', () => {
  it('shows actual evidence on a keyboard-selectable entity and distinguishes keyword links', async () => {
    api.getMemoryGraph.mockResolvedValue(graph);
    const wrapper = mount(MemoryGraph, { props: { userId: 'alice' } });
    await flushPromises();
    expect(wrapper.findAll('svg .network-node')).toHaveLength(3);
    expect(wrapper.findAll('.network-edge.keyword')).toHaveLength(1);
    await wrapper.find('[aria-label="实体：杭州"]').trigger('keydown', { key: 'Enter' });
    expect(wrapper.find('.evidence-button').text()).toBe('打算去杭州旅行');
    await wrapper.find('.evidence-button').trigger('click');
    expect(wrapper.find('.evidence-text').text()).toBe('打算去杭州旅行');
    wrapper.unmount();
  });

  it('filters on the server and renders no unrelated graph when the result is empty', async () => {
    api.getMemoryGraph.mockResolvedValueOnce(graph).mockResolvedValueOnce({ ...graph, nodes: [], edges: [], memory_count: 0 });
    const wrapper = mount(MemoryGraph, { props: { userId: 'alice' } });
    await flushPromises();
    await wrapper.find('[aria-label="筛选记忆网络"]').setValue('不存在');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(api.getMemoryGraph).toHaveBeenLastCalledWith('alice', '不存在', false, false, expect.any(AbortSignal));
    expect(wrapper.text()).toContain('没有符合条件的记忆');
    expect(wrapper.find('svg').exists()).toBe(false);
    wrapper.unmount();
  });

  it('clears private content on account switch and discards the old late response', async () => {
    let finish!: (data: MemoryGraphData) => void;
    api.getMemoryGraph.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
      .mockResolvedValueOnce({ ...graph, nodes: [], edges: [], memory_count: 0 });
    const wrapper = mount(MemoryGraph, { props: { userId: 'alice' } });
    await wrapper.setProps({ userId: 'bob' });
    await flushPromises();
    finish(graph); await flushPromises();
    expect(wrapper.text()).not.toContain('我的旅行约定');
    expect(wrapper.find('svg').exists()).toBe(false);
    wrapper.unmount();
  });
});

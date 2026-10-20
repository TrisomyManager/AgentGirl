<template>
  <section class="memory-network" aria-label="我的记忆网络">
    <div class="network-toolbar">
      <form @submit.prevent="load">
        <input v-model="query" aria-label="筛选记忆网络" placeholder="查找人物、地点或话题" maxlength="120" />
        <button :disabled="loading">查找</button>
        <button type="button" @click="resetSearch">重置</button>
      </form>
      <div class="network-options">
        <label><input v-model="dormant" type="checkbox" @change="load" /> 包含淡化记忆</label>
        <label><input v-model="keywords" type="checkbox" @change="load" /> 显示关键词</label>
        <button @click="load" :disabled="loading">刷新</button>
      </div>
    </div>
    <p class="network-explanation">圆点是提取的实体，方块是记忆，虚线连接自动关键词。点选查看原文依据；关联可能需要核对。</p>
    <p v-if="loading" role="status">正在加载记忆网络…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!graph?.nodes.length" class="network-empty">没有符合条件的记忆。可以调整筛选，或先聊聊最近的生活。</p>
    <template v-else>
      <div class="network-count" role="status">
        {{ graph!.memory_count }} 条记忆 · {{ graph!.nodes.length - graph!.memory_count }} 个关联
        <span v-if="graph!.truncated"> · 当前仅显示部分，输入话题可缩小范围</span>
      </div>
      <div class="network-body">
        <div class="network-canvas">
          <div class="zoom-controls" aria-label="图谱缩放">
            <button aria-label="放大图谱" @click="zoom = Math.min(3, zoom + .25)">＋</button>
            <button aria-label="缩小图谱" @click="zoom = Math.max(.5, zoom - .25)">−</button>
            <button @click="fit">适应</button>
          </div>
          <svg viewBox="0 0 900 520" aria-label="可点选的记忆关联图" @pointerdown="startPan"
               @pointermove="movePan" @pointerup="endPan" @pointercancel="endPan">
            <g :transform="`translate(${pan.x + 450} ${pan.y + 260}) scale(${zoom}) translate(-450 -260)`">
              <line v-for="(edge, i) in layout.edges" :key="i" :x1="edge.a.x" :y1="edge.a.y" :x2="edge.b.x" :y2="edge.b.y"
                    :class="['network-edge', { relation: edge.kind === 'relation', keyword: edge.b.kind === 'keyword', dim: selected && !connectedEdge(edge) }]" />
              <g v-for="node in layout.nodes" :key="node.id" :transform="`translate(${node.x} ${node.y})`"
                 :class="['network-node', node.kind, { selected: selected === node.id, dim: selected && !connected.has(node.id), faded: node.status === 'dormant' }]"
                 role="button" tabindex="0" :aria-label="`${node.kind === 'memory' ? '记忆' : node.kind === 'keyword' ? '关键词' : '实体'}：${node.label}`"
                 :aria-pressed="selected === node.id" @pointerdown.stop @click="select(node.id)" @keydown.enter="select(node.id)" @keydown.space.prevent="select(node.id)">
                <title>{{ node.content || node.label }}</title>
                <rect class="node-hit" x="-22" y="-22" width="44" height="44" />
                <rect v-if="node.kind === 'memory'" x="-9" y="-9" width="18" height="18" rx="4" />
                <circle v-else :r="node.kind === 'keyword' ? 5 : 9" />
                <text y="25" text-anchor="middle">{{ node.label.slice(0, node.kind === 'memory' ? 6 : 10) }}{{ node.label.length > (node.kind === 'memory' ? 6 : 10) ? '…' : '' }}</text>
              </g>
            </g>
          </svg>
        </div>
        <aside class="network-detail" aria-live="polite">
          <template v-if="selectedNode">
            <div class="detail-heading"><small>{{ kindLabel(selectedNode.kind) }}</small><button @click="selected = ''">取消选择</button></div>
            <h3>{{ selectedNode.kind === 'memory' ? '记忆原文' : selectedNode.label }}</h3>
            <template v-if="selectedNode.kind === 'memory'">
              <p class="evidence-text">{{ selectedNode.content }}</p>
              <small v-if="selectedNode.content_truncated">原文较长，这里显示前 2,000 字；可返回列表查看完整内容。</small>
              <p class="detail-meta">{{ selectedNode.status === 'dormant' ? '已淡化' : '活跃' }} · 清晰度 {{ Math.round((selectedNode.importance || 0) * 100) }}%</p>
              <small v-if="selectedNode.created_at">{{ new Date(selectedNode.created_at).toLocaleString('zh-CN') }}</small>
            </template>
            <template v-else>
              <p>{{ selectedNode.kind === 'keyword' ? '由文字自动建立的检索关联，不代表明确的人物或事实关系。' : '根据记忆内容提取，以下原文可用于核对。' }}</p>
              <div v-for="edge in relations" :key="`${edge.source}:${edge.target}:${edge.label}`" class="relation-fact">
                {{ labelFor(edge.source) }} → {{ relationLabel(edge.label) }} → {{ labelFor(edge.target) }}
              </div>
              <button v-for="memory in evidence" :key="memory.id" class="evidence-button" @click="select(memory.id)">{{ memory.content }}</button>
              <p v-if="!evidence.length">当前视图中没有可显示的原文，缩小话题范围后重试。</p>
            </template>
          </template>
          <template v-else>
            <h3>记忆之间的联系</h3><p>选择一个节点，查看关联与原文。拖动空白区域移动，使用上方按钮缩放。</p>
            <label class="node-list-label">也可从列表选择<select aria-label="选择记忆节点" @change="select(($event.target as HTMLSelectElement).value)"><option value="">请选择</option><option v-for="node in graph!.nodes" :key="node.id" :value="node.id">{{ kindLabel(node.kind) }} · {{ node.label }}</option></select></label>
          </template>
        </aside>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useApi, type MemoryGraphData } from '../composables/useApi';
import { memoryGraphLayout } from '../composables/memoryGraphLayout';

const props = defineProps<{ userId: string; revision?: number }>();
const { getMemoryGraph } = useApi();
const query = ref(''), selected = ref(''), error = ref('');
const dormant = ref(false), keywords = ref(false), loading = ref(false);
const graph = ref<MemoryGraphData | null>(null);
const zoom = ref(1), pan = ref({ x: 0, y: 0 });
let request = 0, controller: AbortController | undefined;
let drag: { x: number; y: number; scale: number } | undefined;
const layout = computed(() => memoryGraphLayout(graph.value || { nodes: [], edges: [], truncated: false, memory_count: 0, source: 'sql_index' }));
const selectedNode = computed(() => graph.value?.nodes.find(node => node.id === selected.value));
const connected = computed(() => new Set([selected.value, ...(graph.value?.edges.filter(connectedEdge).flatMap(edge => [edge.source, edge.target]) || [])]));
const relations = computed(() => graph.value?.edges.filter(edge => edge.kind === 'relation' && connectedEdge(edge)) || []);
const evidence = computed(() => {
  const ids = new Set(graph.value?.edges.filter(connectedEdge).flatMap(edge => edge.memory_ids) || []);
  return graph.value?.nodes.filter(node => node.kind === 'memory' && node.memory_id && ids.has(node.memory_id)) || [];
});
function connectedEdge(edge: { source: string; target: string }) { return edge.source === selected.value || edge.target === selected.value; }
function labelFor(id: string) { return graph.value?.nodes.find(node => node.id === id)?.label || ''; }
function kindLabel(kind: string) { return kind === 'memory' ? '记忆' : kind === 'keyword' ? '关键词' : '实体'; }
function relationLabel(label: string) { return ({ LOCATED_IN: '位于', LIKES: '喜欢', DISLIKES: '不喜欢', RELATED_TO: '相关', KNOWS: '认识', WORKS_AT: '工作于', LIVES_IN: '居住于' } as Record<string, string>)[label] || label.replace(/_/g, ' '); }
function select(id: string) { selected.value = id; }
function fit() { zoom.value = 1; pan.value = { x: 0, y: 0 }; }
function startPan(event: PointerEvent) {
  const svg = event.currentTarget as SVGSVGElement;
  if (event.button !== 0) return;
  drag = { x: event.clientX, y: event.clientY, scale: 900 / Math.max(1, svg.getBoundingClientRect().width) };
  svg.setPointerCapture?.(event.pointerId);
}
function movePan(event: PointerEvent) {
  if (!drag) return;
  pan.value = { x: pan.value.x + (event.clientX - drag.x) * drag.scale, y: pan.value.y + (event.clientY - drag.y) * drag.scale };
  drag.x = event.clientX; drag.y = event.clientY;
}
function endPan() { drag = undefined; }
async function load() {
  const current = ++request;
  controller?.abort(); controller = new AbortController();
  graph.value = null; selected.value = ''; loading.value = true; error.value = ''; fit();
  const result = props.userId ? await getMemoryGraph(props.userId, query.value.trim(), dormant.value, keywords.value, controller.signal) : null;
  if (request !== current) return;
  loading.value = false; graph.value = result;
  if (!result) error.value = '记忆网络加载失败，请稍后刷新。';
}
function resetSearch() { query.value = ''; void load(); }
watch(() => [props.userId, props.revision], () => { query.value = ''; void load(); }, { immediate: true });
onBeforeUnmount(() => { request++; controller?.abort(); graph.value = null; });
</script>

<style scoped>
.memory-network { padding: 0 20px 18px; overflow: auto; min-height: 0; color: #eee9fa; }
.network-toolbar form, .network-options { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.network-toolbar input:not([type]), .network-toolbar input[type="text"] { flex: 1; min-width: 140px; }
input:not([type="checkbox"]), select { background: #17192c; color: #eee9fa; border: 1px solid #61617b; border-radius: 8px; padding: 9px; }
button { color: #f2edf9; background: #37314f; border: 1px solid #76658e; border-radius: 7px; padding: 7px 11px; cursor: pointer; }
button:disabled { opacity: .5; cursor: wait; }
button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid #e4c2ff; outline-offset: 2px; }
.network-options label, .network-explanation, .network-count, .detail-meta { font-size: 12px; color: #c8c2d8; line-height: 1.6; }
.network-count { margin: 8px 0; }
.network-body { display: grid; grid-template-columns: minmax(0, 1fr) 240px; gap: 12px; }
.network-canvas { position: relative; min-width: 0; background: #11172b; border: 1px solid #4c4663; border-radius: 12px; overflow: hidden; }
svg { display: block; width: 100%; min-height: 340px; touch-action: none; cursor: grab; }
.zoom-controls { position: absolute; z-index: 1; display: flex; gap: 5px; top: 8px; left: 8px; }
.network-edge { stroke: #736681; stroke-width: 1.2; opacity: .55; }
.network-edge.relation { stroke: #89c5e9; stroke-width: 2.2; }
.network-edge.keyword { stroke-dasharray: 4 4; }
.network-node { cursor: pointer; }
.network-node rect { fill: #b8a1ec; stroke: #e1d0ff; }
.network-node circle { fill: #7ed4ce; stroke: #cdf7f4; }
.network-node.keyword circle { fill: #8395b3; }
.network-node text { fill: #eee9fa; font-size: 18px; paint-order: stroke; stroke: #11172b; stroke-width: 3px; }
.network-node .node-hit { fill: transparent; stroke: none; }
.network-node.selected rect, .network-node.selected circle, .network-node:focus rect, .network-node:focus circle { stroke: #ffe0a3; stroke-width: 4px; }
.network-node.selected .node-hit, .network-node:focus .node-hit { stroke: none; }
.network-node.faded { opacity: .5; }
.network-node.dim, .network-edge.dim { opacity: .3; }
.network-detail { border: 1px solid #554766; background: #201c34; border-radius: 12px; padding: 14px; overflow-wrap: anywhere; max-height: 520px; overflow: auto; }
.network-detail h3 { font-size: 15px; margin: 10px 0; }
.network-detail p, .network-detail small { font-size: 12px; line-height: 1.7; }
.detail-heading { display: flex; justify-content: space-between; align-items: center; }
.detail-heading button { font-size: 11px; padding: 4px 7px; }
.evidence-text { white-space: pre-wrap; }
.evidence-button { display: block; text-align: left; width: 100%; margin-top: 8px; font-size: 12px; line-height: 1.6; max-height: 110px; overflow: auto; }
.relation-fact { font-size: 12px; border-left: 2px solid #89c5e9; padding: 8px; margin: 8px 0; }
.node-list-label { font-size: 12px; display: grid; gap: 8px; }
select { width: 100%; }
.network-empty { padding: 35px 0; text-align: center; font-size: 13px; }
@media (max-width: 650px) {
  .memory-network { padding: 0 12px 12px; }
  .network-body { grid-template-columns: minmax(0, 1fr); }
  .network-detail { max-height: 250px; }
  svg { min-height: 300px; }
  .network-node text { font-size: 30px; }
  .network-node:not(.keyword) circle { r: 13px; }
}
</style>

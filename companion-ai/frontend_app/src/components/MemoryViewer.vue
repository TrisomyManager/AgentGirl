<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="visible" class="overlay" @click="closePanel">
        <div class="panel" @click.stop>
          <div class="header">
            <h2>🧠 记忆库</h2>
            <button class="close-btn" @click="closePanel">✕</button>
          </div>

          <!-- Summary stats -->
          <div class="stats-row">
            <div class="stat">
              <div class="stat-num">{{ summary?.total_memories ?? 0 }}</div>
              <div class="stat-label">总条数</div>
            </div>
            <div class="stat">
              <div class="stat-num">{{ avgImpStr }}</div>
              <div class="stat-label">平均重要性</div>
            </div>
            <div class="stat">
              <div class="stat-num">{{ Object.keys(summary?.by_category || {}).length }}</div>
              <div class="stat-label">类别数</div>
            </div>
            <div class="stat">
              <div class="stat-num small">{{ lastMemoryStr }}</div>
              <div class="stat-label">最近一条</div>
            </div>
          </div>

          <!-- Category filter -->
          <div class="filter-row">
            <button
              class="cat-chip"
              :class="{ active: activeCategory === '' }"
              @click="setCategory('')"
            >全部</button>
            <button
              v-for="cat in availableCategories"
              :key="cat"
              class="cat-chip"
              :class="{ active: activeCategory === cat }"
              @click="setCategory(cat)"
            >{{ catLabel(cat) }} ({{ summary?.by_category[cat] || 0 }})</button>
          </div>

          <!-- Search -->
          <div class="search-row">
            <input
              v-model="searchQuery"
              placeholder="🔍 语义搜索记忆..."
              @keydown.enter="runSearch"
            />
            <button class="search-btn" @click="runSearch" :disabled="searching">
              {{ searching ? '搜索中...' : '搜索' }}
            </button>
            <button v-if="searchResults.length" class="clear-btn" @click="clearSearch">清除</button>
          </div>

          <!-- Memory list -->
          <div class="list">
            <div v-if="loading" class="empty">⏳ 加载中...</div>
            <div v-else-if="!displayList.length" class="empty">
              {{ searchResults.length ? '未找到相关记忆' : '尚未生成任何记忆 — 多聊一些就有了' }}
            </div>
            <div
              v-for="mem in displayList"
              :key="mem.entry_id || mem.id"
              class="card"
              :class="`cat-${mem.category}`"
            >
              <div class="card-header">
                <span class="cat-tag" :class="`cat-${mem.category}`">{{ catLabel(mem.category) }}</span>
                <div class="imp-bar">
                  <div class="imp-fill" :style="{ width: (mem.importance * 100) + '%' }"></div>
                </div>
                <span class="imp-text">{{ Math.round(mem.importance * 100) }}%</span>
                <button class="del-btn" @click="onDelete(mem)" title="删除">🗑️</button>
              </div>
              <div class="card-body">{{ mem.content }}</div>
              <div class="card-footer">
                <span v-if="mem.emotion_tags?.length" class="emo-tags">
                  <span v-for="t in mem.emotion_tags" :key="t" class="emo-tag">{{ t }}</span>
                </span>
                <span class="date">{{ fmtDate(mem.created_at) }}</span>
              </div>
            </div>
          </div>

          <!-- Footer actions -->
          <div class="footer">
            <button class="refresh-btn" @click="refresh">🔄 刷新</button>
            <button class="danger-btn" @click="onClearAll">🗑️ 清空全部</button>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useApi } from '../composables/useApi';

const props = defineProps<{ visible: boolean; userId: string }>();
const emit = defineEmits<{ (e: 'close'): void }>();

const { listMemories, getMemorySummary, recallMemory, deleteMemory, deleteAllMemories } = useApi();

const memories = ref<any[]>([]);
const summary = ref<any | null>(null);
const loading = ref(false);
const searching = ref(false);
const searchQuery = ref('');
const searchResults = ref<any[]>([]);
const activeCategory = ref('');

const CATEGORY_LABELS: Record<string, string> = {
  fact: '事实',
  emotion: '情感',
  event: '事件',
  preference: '偏好',
  relationship_milestone: '关系里程碑',
  routine: '日常',
};

function catLabel(c: string): string {
  return CATEGORY_LABELS[c] || c;
}

const availableCategories = computed(() => {
  return Object.keys(summary.value?.by_category || {});
});

const displayList = computed(() => {
  if (searchResults.value.length) return searchResults.value;
  if (activeCategory.value) {
    return memories.value.filter((m) => m.category === activeCategory.value);
  }
  return memories.value;
});

const avgImpStr = computed(() => {
  const v = summary.value?.avg_importance;
  return v != null ? (v * 100).toFixed(0) + '%' : '—';
});

const lastMemoryStr = computed(() => {
  const v = summary.value?.last_memory;
  if (!v) return '—';
  try {
    const d = new Date(v);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}分前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
    return `${Math.floor(diff / 86400)}天前`;
  } catch {
    return v;
  }
});

function fmtDate(s: string | null): string {
  if (!s) return '';
  try {
    const d = new Date(s);
    return d.toLocaleString('zh-CN', { hour12: false });
  } catch {
    return s;
  }
}

async function refresh() {
  if (!props.userId) return;
  loading.value = true;
  searchResults.value = [];
  searchQuery.value = '';
  const [list, sum] = await Promise.all([
    listMemories(props.userId, 100, 0, activeCategory.value || undefined),
    getMemorySummary(props.userId),
  ]);
  memories.value = list || [];
  summary.value = sum;
  loading.value = false;
}

async function setCategory(cat: string) {
  activeCategory.value = cat;
  await refresh();
}

async function runSearch() {
  if (!searchQuery.value.trim()) {
    searchResults.value = [];
    return;
  }
  searching.value = true;
  const result = await recallMemory(props.userId, searchQuery.value, 10);
  searching.value = false;
  searchResults.value = result?.entries || [];
}

function clearSearch() {
  searchQuery.value = '';
  searchResults.value = [];
}

async function onDelete(mem: any) {
  const id = mem.entry_id || mem.id;
  if (!id) return;
  if (!confirm('确定删除这条记忆？')) return;
  const ok = await deleteMemory(id);
  if (ok) {
    memories.value = memories.value.filter((m) => (m.entry_id || m.id) !== id);
    searchResults.value = searchResults.value.filter((m) => (m.entry_id || m.id) !== id);
    summary.value = await getMemorySummary(props.userId);
  }
}

async function onClearAll() {
  if (!confirm('确定清空所有记忆？此操作不可恢复！')) return;
  const ok = await deleteAllMemories(props.userId);
  if (ok) {
    memories.value = [];
    searchResults.value = [];
    summary.value = await getMemorySummary(props.userId);
  }
}

function closePanel() {
  emit('close');
}

watch(
  () => props.visible,
  (v) => {
    if (v) refresh();
  }
);
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  z-index: 150;
  display: flex;
  align-items: center;
  justify-content: center;
}
.panel {
  width: 92%;
  max-width: 900px;
  max-height: 88vh;
  background: linear-gradient(135deg, #1a1530 0%, #16213e 100%);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.header h2 { margin: 0; font-size: 20px; color: #fff; }
.close-btn {
  width: 34px; height: 34px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.06);
  color: #cbd5e1;
  cursor: pointer;
  font-size: 14px;
}
.close-btn:hover { background: rgba(233, 69, 96, 0.25); color: #fff; }

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 14px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.stat {
  text-align: center;
  padding: 12px 8px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  border: 1px solid rgba(167, 139, 250, 0.18);
}
.stat-num { font-size: 22px; font-weight: 700; color: #a78bfa; line-height: 1; }
.stat-num.small { font-size: 14px; color: #cbd5e1; }
.stat-label { font-size: 11px; color: #94a3b8; margin-top: 4px; }

.filter-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 12px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.cat-chip {
  padding: 5px 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: #94a3b8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.cat-chip:hover { color: #fff; border-color: rgba(167, 139, 250, 0.4); }
.cat-chip.active {
  color: #fff;
  background: rgba(167, 139, 250, 0.25);
  border-color: rgba(167, 139, 250, 0.6);
}

.search-row {
  display: flex;
  gap: 8px;
  padding: 12px 24px;
}
.search-row input {
  flex: 1;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 15, 30, 0.7);
  color: #e2e8f0;
  font-size: 14px;
  outline: none;
}
.search-row input:focus { border-color: rgba(167, 139, 250, 0.5); }
.search-btn, .clear-btn {
  padding: 10px 16px;
  border-radius: 10px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.search-btn {
  background: linear-gradient(135deg, #a78bfa, #8b5cf6);
  color: #fff;
}
.search-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.clear-btn {
  background: rgba(255, 255, 255, 0.06);
  color: #cbd5e1;
}

.list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 24px 16px;
}
.list::-webkit-scrollbar { width: 5px; }
.list::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 4px; }

.empty {
  text-align: center;
  padding: 40px 20px;
  color: #64748b;
  font-size: 14px;
}

.card {
  margin-bottom: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border-left: 3px solid #94a3b8;
  transition: background 0.15s;
}
.card:hover { background: rgba(255, 255, 255, 0.05); }
.card.cat-fact { border-left-color: #60a5fa; }
.card.cat-emotion { border-left-color: #f472b6; }
.card.cat-event { border-left-color: #fbbf24; }
.card.cat-preference { border-left-color: #4ade80; }
.card.cat-relationship_milestone { border-left-color: #a78bfa; }
.card.cat-routine { border-left-color: #94a3b8; }

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.cat-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
  font-weight: 600;
}
.cat-tag.cat-fact { background: rgba(96, 165, 250, 0.18); color: #60a5fa; }
.cat-tag.cat-emotion { background: rgba(244, 114, 182, 0.18); color: #f472b6; }
.cat-tag.cat-event { background: rgba(251, 191, 36, 0.18); color: #fbbf24; }
.cat-tag.cat-preference { background: rgba(74, 222, 128, 0.18); color: #4ade80; }
.cat-tag.cat-relationship_milestone { background: rgba(167, 139, 250, 0.18); color: #a78bfa; }
.cat-tag.cat-routine { background: rgba(148, 163, 184, 0.18); color: #94a3b8; }

.imp-bar {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
  max-width: 180px;
}
.imp-fill {
  height: 100%;
  background: linear-gradient(90deg, #fbbf24, #ef4444);
  transition: width 0.3s;
}
.imp-text { font-size: 11px; color: #94a3b8; min-width: 32px; text-align: right; }

.del-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.5;
  transition: opacity 0.15s;
}
.del-btn:hover { opacity: 1; }

.card-body {
  font-size: 13px;
  color: #e2e8f0;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 11px;
  color: #64748b;
}
.emo-tags { display: flex; gap: 4px; }
.emo-tag {
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(167, 139, 250, 0.1);
  color: #a78bfa;
  font-size: 10px;
}
.date { color: #64748b; }

.footer {
  display: flex;
  justify-content: space-between;
  padding: 12px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}
.refresh-btn, .danger-btn {
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
  font-size: 13px;
  cursor: pointer;
}
.refresh-btn {
  background: rgba(255, 255, 255, 0.06);
  color: #cbd5e1;
}
.refresh-btn:hover { background: rgba(255, 255, 255, 0.1); }
.danger-btn {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}
.danger-btn:hover { background: rgba(239, 68, 68, 0.2); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>

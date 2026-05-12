<template>
  <Transition name="panel-fade">
    <div v-if="visible" class="capability-overlay" @click.self="$emit('close')">
      <div class="capability-panel">
        <div class="panel-header">
          <h2>{{ activeTab === 'capabilities' ? '小暖可以帮你' : '我的小暖事项' }}</h2>
          <button class="close-btn" @click="$emit('close')" aria-label="关闭">✕</button>
        </div>

        <!-- Tab bar -->
        <div class="tab-bar">
          <button
            :class="['tab-btn', { active: activeTab === 'capabilities' }]"
            @click="activeTab = 'capabilities'"
          >
            小暖能力
          </button>
          <button
            :class="['tab-btn', { active: activeTab === 'mytasks' }]"
            @click="activeTab = 'mytasks'"
          >
            我的事项
          </button>
          <button
            :class="['tab-btn', { active: activeTab === 'mydevices' }]"
            @click="activeTab = 'mydevices'"
          >
            我的设备
          </button>
        </div>

        <!-- Tab: Capabilities -->
        <template v-if="activeTab === 'capabilities'">
          <div v-if="capLoading" class="status-box"><span class="spinner"></span><span>加载中…</span></div>
          <div v-else-if="capError" class="status-box error"><span>{{ capError }}</span></div>
          <div v-else-if="!groups.length" class="status-box"><span>暂无能力数据</span></div>
          <div v-else class="panel-body">
            <div v-for="group in groups" :key="group.name" class="cap-group">
              <div class="group-title">{{ group.name }}</div>
              <div v-for="cap in group.items" :key="cap.id" class="cap-card">
                <div class="cap-head">
                  <span class="cap-title">{{ cap.title }}</span>
                  <span :class="['cap-status', cap.status]">{{ statusLabel(cap.status) }}</span>
                </div>
                <div class="cap-desc">{{ cap.description }}</div>
                <div v-if="cap.examples.length" class="cap-examples">
                  <button
                    v-for="(ex, idx) in cap.examples" :key="idx"
                    class="example-btn"
                    :disabled="cap.status === 'disabled' || cap.status === 'experimental'"
                    @click="fillExample(ex)"
                  >{{ ex }}</button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- Tab: My Tasks -->
        <template v-if="activeTab === 'mytasks'">
          <div v-if="taskLoading" class="status-box"><span class="spinner"></span><span>加载中…</span></div>
          <div v-else-if="taskError" class="status-box error"><span>{{ taskError }}</span></div>
          <div v-else-if="taskEmpty" class="status-box">
            <div class="empty-state">
              <p>现在还没有安排给小暖的事项。</p>
              <p class="empty-hint">你可以对小暖说：<br><em>明天上午 10 点提醒我交材料</em></p>
            </div>
          </div>
          <div v-else class="panel-body">
            <!-- Upcoming -->
            <div v-if="upcoming.length" class="task-section">
              <div class="task-section-title">待提醒</div>
              <div v-for="item in upcoming" :key="item.id" class="task-card">
                <div class="task-info">
                  <span class="task-title">{{ formatTime(item.scheduled_at) }} 提醒你：{{ item.title }}</span>
                </div>
                <button class="cancel-task-btn" @click="cancelReminder(item.id)">取消</button>
              </div>
            </div>

            <!-- Proactive (placeholder) -->
            <div v-if="rules.length" class="task-section">
              <div class="task-section-title">主动陪伴</div>
              <div v-for="rule in rules" :key="rule.id" class="task-card proactive-card">
                <span class="task-title">{{ rule.title }}</span>
                <span :class="['status-tag', rule.enabled ? 'on' : 'off']">{{ rule.enabled ? '开启' : '关闭' }}</span>
              </div>
            </div>

            <!-- Recent -->
            <div v-if="recent.length" class="task-section">
              <div class="task-section-title">最近记录</div>
              <div v-for="item in recent" :key="item.id" class="task-card recent-card">
                <span class="task-title">
                  <template v-if="item.status === 'fired'">{{ formatTime(item.completed_at || item.scheduled_at) }} 已提醒你：{{ item.title }}</template>
                  <template v-else>已取消：{{ item.title }}</template>
                </span>
              </div>
            </div>
          </div>
        </template>

        <!-- Tab: My Devices -->
        <template v-if="activeTab === 'mydevices'">
          <div class="panel-body">
            <DevicePanel :user-id="userId" />
          </div>
        </template>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useApi, type CapabilityItem, type UserStateItem, type UserStateResponse } from '../composables/useApi';
import DevicePanel from './DevicePanel.vue';

const props = defineProps<{ visible: boolean; userId: string }>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'fill', text: string): void;
}>();

const { getCapabilities, getUserState, cancelReminder: apiCancelReminder } = useApi();

const activeTab = ref<'capabilities' | 'mytasks' | 'mydevices'>('capabilities');

// --- Capabilities ---
const capLoading = ref(false);
const capError = ref('');
const capabilities = ref<CapabilityItem[]>([]);

const groupOrder = ['生活助手', '查询能力', '记忆与关系', '主动陪伴', '设备与动作'];

const groups = computed(() => {
  const map = new Map<string, CapabilityItem[]>();
  for (const c of capabilities.value) {
    const g = c.group || '其他';
    if (!map.has(g)) map.set(g, []);
    map.get(g)!.push(c);
  }
  const ordered: { name: string; items: CapabilityItem[] }[] = [];
  for (const g of groupOrder) {
    if (map.has(g)) ordered.push({ name: g, items: map.get(g)! });
  }
  for (const [g, items] of map) {
    if (!groupOrder.includes(g)) ordered.push({ name: g, items });
  }
  return ordered;
});

const statusLabels: Record<string, string> = {
  ready: '可用',
  needs_config: '需配置',
  degraded: '部分可用',
  disabled: '未启用',
  experimental: '实验中',
};

function statusLabel(s: string) { return statusLabels[s] || s; }

async function loadCapabilities() {
  if (capabilities.value.length || capLoading.value) return;
  capLoading.value = true;
  capError.value = '';
  try {
    const data = await getCapabilities();
    if (data === null) throw new Error('接口请求失败');
    capabilities.value = data;
  } catch (e) {
    capError.value = e instanceof Error ? e.message : '加载能力失败';
  } finally {
    capLoading.value = false;
  }
}

function fillExample(text: string) {
  emit('fill', text);
  emit('close');
}

// --- My Tasks ---
const taskLoading = ref(false);
const taskError = ref('');
const state = ref<UserStateResponse | null>(null);

const upcoming = computed(() => state.value?.reminders?.upcoming || []);
const recent = computed(() => state.value?.reminders?.recent || []);
const rules = computed(() => state.value?.proactive?.rules || []);

const taskEmpty = computed(() => {
  if (!state.value) return false;
  return upcoming.value.length === 0 && recent.value.length === 0 && rules.value.length === 0;
});

async function loadTasks() {
  if (taskLoading.value) return;
  taskLoading.value = true;
  taskError.value = '';
  try {
    const data = await getUserState(props.userId || 'user_001');
    if (data === null) throw new Error('接口请求失败');
    state.value = data;
  } catch (e) {
    taskError.value = e instanceof Error ? e.message : '加载事项失败';
  } finally {
    taskLoading.value = false;
  }
}

// Reload tasks every time the tab is activated so newly created reminders
// show up without closing and re-opening the panel.
watch(activeTab, (t) => {
  if (t === 'mytasks') loadTasks();
  if (t === 'capabilities') loadCapabilities();
});

async function cancelReminder(id: string) {
  const ok = await apiCancelReminder(id);
  if (ok) {
    // Remove from local state immediately so UI feels responsive.
    if (state.value) {
      const item = upcoming.value.find(u => u.id === id) || recent.value.find(r => r.id === id);
      state.value.reminders.upcoming = upcoming.value.filter(u => u.id !== id);
      state.value.reminders.recent = recent.value.filter(r => r.id !== id);
      if (item) {
        (item as UserStateItem).status = 'cancelled';
        state.value.reminders.recent.unshift(item);
      }
    }
  }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

onMounted(() => {
  if (props.visible) loadCapabilities();
});
</script>

<style scoped>
.capability-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.52);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(6px);
}

.capability-panel {
  width: min(600px, 92vw);
  max-height: 80vh;
  background: linear-gradient(180deg, rgba(20, 26, 42, 0.98), rgba(10, 14, 24, 0.99));
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  box-shadow: 0 32px 80px rgba(0, 0, 0, 0.55);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.panel-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #f0f4ff;
  letter-spacing: 0.02em;
}

.close-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #94a3b8;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover { background: rgba(255, 255, 255, 0.1); color: #e2e8f0; }

/* Tabs */
.tab-bar {
  display: flex;
  gap: 0;
  padding: 0 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.tab-btn {
  flex: 1;
  padding: 12px 0;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn.active {
  color: #e2e8f0;
  border-bottom-color: #e94560;
}

.tab-btn:hover:not(.active) { color: #94a3b8; }

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px 20px;
  scroll-behavior: smooth;
}

.panel-body::-webkit-scrollbar { width: 4px; }
.panel-body::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 999px; }

.status-box {
  padding: 32px;
  text-align: center;
  color: #94a3b8;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.status-box.error { color: #fca5a5; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(233, 69, 96, 0.2);
  border-top-color: #e94560;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.cap-group { margin-bottom: 18px; }

.group-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #64748b;
  margin-bottom: 10px;
  padding-left: 4px;
  text-transform: none;
}

.cap-card {
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 8px;
  transition: border-color 0.2s;
}

.cap-card:hover { border-color: rgba(233, 69, 96, 0.2); }

.cap-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.cap-title { font-size: 15px; font-weight: 600; color: #e2e8f0; }

.cap-status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 999px;
}

.cap-status.ready { color: #4ade80; background: rgba(74, 222, 128, 0.1); }
.cap-status.needs_config { color: #facc15; background: rgba(250, 204, 21, 0.1); }
.cap-status.degraded { color: #f97316; background: rgba(249, 115, 22, 0.1); }
.cap-status.disabled { color: #64748b; background: rgba(100, 116, 139, 0.1); }
.cap-status.experimental { color: #818cf8; background: rgba(129, 140, 248, 0.1); }

.cap-desc { font-size: 13px; color: #94a3b8; line-height: 1.55; margin-bottom: 8px; }

.cap-examples { display: flex; flex-wrap: wrap; gap: 6px; }

.example-btn {
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid rgba(233, 69, 96, 0.18);
  background: rgba(233, 69, 96, 0.06);
  color: #e2e8f0;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.example-btn:hover { background: rgba(233, 69, 96, 0.16); border-color: rgba(233, 69, 96, 0.3); }
.example-btn:disabled { opacity: 0.35; cursor: not-allowed; }

/* --- My Tasks --- */
.task-section { margin-bottom: 20px; }

.task-section-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #64748b;
  margin-bottom: 10px;
  padding-left: 4px;
  text-transform: none;
}

.task-card {
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  padding: 12px 16px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  transition: border-color 0.2s;
}

.task-card:hover { border-color: rgba(233, 69, 96, 0.15); }

.task-info { flex: 1; min-width: 0; }

.task-title { font-size: 13px; color: #e2e8f0; line-height: 1.5; }

.cancel-task-btn {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid rgba(248, 113, 113, 0.2);
  background: rgba(248, 113, 113, 0.08);
  color: #fca5a5;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  white-space: nowrap;
}

.cancel-task-btn:hover { background: rgba(248, 113, 113, 0.18); border-color: rgba(248, 113, 113, 0.35); }

.recent-card { opacity: 0.75; }

.recent-card .task-title { color: #94a3b8; }

.proactive-card { opacity: 0.85; }

.status-tag {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 999px;
  flex-shrink: 0;
}

.status-tag.on { color: #4ade80; background: rgba(74, 222, 128, 0.1); }
.status-tag.off { color: #64748b; background: rgba(100, 116, 139, 0.1); }

.empty-state { text-align: center; }

.empty-state p {
  color: #94a3b8;
  font-size: 14px;
  margin: 4px 0;
}

.empty-hint {
  margin-top: 10px !important;
  color: #64748b !important;
  font-size: 13px !important;
}

.empty-hint em { color: #e94560; font-style: normal; }

/* Transition */
.panel-fade-enter-active,
.panel-fade-leave-active {
  transition: opacity 0.2s ease;
}

.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
}

@media (max-width: 640px) {
  .capability-panel {
    width: 100vw;
    max-height: 100dvh;
    border-radius: 0;
    border: none;
  }

  .example-btn { max-width: 200px; }
}
</style>

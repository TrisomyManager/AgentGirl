<template>
  <Transition name="status-fade">
    <div v-if="visible" class="cap-status-overlay" @click.self="$emit('close')">
      <div class="cap-status-panel">
        <div class="panel-header">
          <h3>小暖能力状态</h3>
          <button class="close-btn" @click="$emit('close')">✕</button>
        </div>
        <div class="panel-body">
          <div v-if="loading" class="hint">加载中…</div>
          <div v-else-if="!caps.length" class="hint">暂无数据</div>
          <table v-else>
            <thead>
              <tr>
                <th>能力</th>
                <th>状态</th>
                <th>缺配置</th>
                <th>Lite</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in caps" :key="c.id">
                <td>
                  <span class="cap-name">{{ c.title }}</span>
                  <span class="cap-group-label">{{ c.group }}</span>
                </td>
                <td>
                  <span :class="['tag', c.status]">{{ labels[c.status] }}</span>
                </td>
                <td class="missing-cell">
                  <template v-if="c.missing_config.length">
                    <code v-for="m in c.missing_config" :key="m">{{ m }}</code>
                  </template>
                  <span v-else class="none">—</span>
                </td>
                <td>{{ c.lite_mode_supported ? '✅' : '⚠️' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useApi, type CapabilityItem } from '../composables/useApi';

const props = defineProps<{ visible: boolean }>();
defineEmits<{ (e: 'close'): void }>();

const { getCapabilities } = useApi();
const loading = ref(false);
const caps = ref<CapabilityItem[]>([]);

const labels: Record<string, string> = {
  ready: '可用',
  needs_config: '需配置',
  degraded: '部分可用',
  disabled: '未启用',
  experimental: '实验中',
};

async function load() {
  if (caps.value.length) return;
  loading.value = true;
  try {
    const data = await getCapabilities();
    if (data) caps.value = data;
  } finally {
    loading.value = false;
  }
}

watch(() => props.visible, (v) => {
  if (v) load();
});
</script>

<style scoped>
.cap-status-overlay {
  position: fixed;
  inset: 0;
  z-index: 210;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.cap-status-panel {
  width: min(720px, 94vw);
  max-height: 80vh;
  background: linear-gradient(180deg, rgba(20, 26, 42, 0.98), rgba(10, 14, 24, 0.99));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  color: #f0f4ff;
}

.close-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: none;
  color: #94a3b8;
  cursor: pointer;
  font-size: 14px;
}

.close-btn:hover { color: #e2e8f0; }

.panel-body { overflow-y: auto; padding: 12px; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th {
  text-align: left;
  padding: 8px 10px;
  color: #64748b;
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.04em;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

td {
  padding: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  vertical-align: middle;
}

.cap-name { font-weight: 600; color: #e2e8f0; }
.cap-group-label { display: block; font-size: 11px; color: #64748b; margin-top: 2px; }

.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 500;
}

.tag.ready { color: #4ade80; background: rgba(74, 222, 128, 0.1); }
.tag.needs_config { color: #facc15; background: rgba(250, 204, 21, 0.1); }
.tag.degraded { color: #f97316; background: rgba(249, 115, 22, 0.1); }
.tag.disabled { color: #64748b; background: rgba(100, 116, 139, 0.1); }
.tag.experimental { color: #818cf8; background: rgba(129, 140, 248, 0.1); }

.missing-cell code {
  display: inline-block;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(250, 204, 21, 0.12);
  color: #facc15;
  margin: 1px 2px;
}

.none { color: #475569; }
.hint { padding: 32px; text-align: center; color: #64748b; font-size: 14px; }

.status-fade-enter-active, .status-fade-leave-active { transition: opacity 0.2s; }
.status-fade-enter-from, .status-fade-leave-to { opacity: 0; }
</style>

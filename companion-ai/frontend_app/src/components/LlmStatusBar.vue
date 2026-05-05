<template>
  <div class="llm-status-bar">
    <div v-if="loading" class="status-content loading-state">
      <span class="status-icon">⚙️</span>
      <span class="status-text">正在获取 LLM 配置...</span>
    </div>

    <div v-else-if="config" class="status-content" :class="{ 'config-warning': !config.api_key_set }">
      <span class="status-icon">🤖</span>
      <div class="status-details">
        <span class="status-provider">{{ providerLabel }}</span>
        <span class="status-divider">|</span>
        <span class="status-model">{{ config.model || '未配置' }}</span>
        <span v-if="config.base_url" class="status-divider">|</span>
        <span v-if="config.base_url" class="status-url">{{ shortenUrl(config.base_url) }}</span>
      </div>
      <span v-if="!config.api_key_set" class="status-warning-badge" title="API Key 未设置">⚠️</span>
      <button class="status-refresh" @click="refresh" title="刷新配置">
        <span class="refresh-icon">🔄</span>
      </button>
    </div>

    <div v-else class="status-content error-state">
      <span class="status-icon">⚠️</span>
      <span class="status-text">无法获取 LLM 配置</span>
      <button class="status-refresh" @click="refresh" title="重试">
        <span class="refresh-icon">🔄</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useApi } from '../composables/useApi';

const { getLlmConfig } = useApi();

const loading = ref(true);
const config = ref<{
  provider: string;
  api_key_set: boolean;
  base_url: string;
  model: string;
} | null>(null);

const providerLabel = computed(() => {
  const map: Record<string, string> = {
    openai: 'OpenAI',
    claude: 'Claude',
    kimi: 'Kimi',
    dashscope: 'DashScope',
    ollama: 'Ollama',
    custom: '自定义',
  };
  return map[config.value?.provider || ''] || config.value?.provider || '未知';
});

function shortenUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname;
  } catch {
    return url.length > 30 ? url.slice(0, 27) + '...' : url;
  }
}

async function refresh() {
  loading.value = true;
  const cfg = await getLlmConfig();
  config.value = cfg;
  loading.value = false;
}

onMounted(() => {
  refresh();
});
</script>

<style scoped>
.llm-status-bar {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(11, 15, 27, 0.58);
  backdrop-filter: blur(8px);
}

.status-content {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 12px;
  color: #94a3b8;
  transition: background 0.2s ease;
}

.status-content.loading-state {
  color: #64748b;
}

.status-content.error-state {
  color: #f87171;
}

.status-content.config-warning {
  background: rgba(245, 158, 11, 0.05);
  border-top-color: rgba(245, 158, 11, 0.15);
}

.status-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.status-text {
  flex: 1;
}

.status-details {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  flex-wrap: wrap;
}

.status-provider {
  font-weight: 600;
  color: #e94560;
}

.status-model {
  color: #8b5cf6;
  font-family: 'JetBrains Mono', monospace;
}

.status-url {
  color: #64748b;
  font-size: 11px;
}

.status-divider {
  color: rgba(255, 255, 255, 0.1);
}

.status-warning-badge {
  font-size: 13px;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-refresh {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.status-refresh:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #94a3b8;
}

.status-refresh:active .refresh-icon {
  animation: spin 0.5s ease;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.refresh-icon {
  display: inline-block;
  font-size: 12px;
}

@media (max-width: 640px) {
  .status-content {
    padding: 8px 12px;
  }
}
</style>

<template>
  <div v-if="visible" class="status-overlay" @click="closePanel">
    <div class="status-panel" @click.stop>
      <!-- Header -->
      <div class="panel-header">
        <h2>📊 {{ statusData?.project_name || '项目开发状态' }}</h2>
        <p class="version">{{ statusData?.version || 'v0.0.0' }}</p>
        <button class="close-btn" @click="closePanel">✕</button>
      </div>

      <!-- Overall Progress -->
      <div class="overall-progress">
        <div class="progress-label">
          <span>整体完成度</span>
          <span class="progress-value">{{ statusData?.overall_progress || 0 }}%</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: (statusData?.overall_progress || 0) + '%' }"
          ></div>
        </div>
        <div class="progress-meta">
          <span class="meta-item">
            <span class="meta-num">{{ stats.totalFeatures }}</span>
            <span class="meta-label">总功能数</span>
          </span>
          <span class="meta-item">
            <span class="meta-num new">{{ stats.newFeatures }}</span>
            <span class="meta-label">🆕 本次新增</span>
          </span>
          <span class="meta-item">
            <span class="meta-num">{{ statusData?.modules.length || 0 }}</span>
            <span class="meta-label">模块总数</span>
          </span>
        </div>
      </div>

      <!-- Stats summary -->
      <div class="stats-grid">
        <div class="stat-card completed">
          <div class="stat-icon">✅</div>
          <div class="stat-num">{{ stats.completed }}</div>
          <div class="stat-label">已完成</div>
        </div>
        <div class="stat-card in_progress">
          <div class="stat-icon">🔄</div>
          <div class="stat-num">{{ stats.inProgress }}</div>
          <div class="stat-label">开发中</div>
        </div>
        <div class="stat-card planned">
          <div class="stat-icon">📋</div>
          <div class="stat-num">{{ stats.planned }}</div>
          <div class="stat-label">规划中</div>
        </div>
        <div class="stat-card blocked">
          <div class="stat-icon">🚫</div>
          <div class="stat-num">{{ stats.blocked }}</div>
          <div class="stat-label">阻塞</div>
        </div>
      </div>

      <!-- Architecture Layers -->
      <div class="architecture-layers">
        <h3>🏗️ 架构分层</h3>
        <div
          v-for="(modules, layer) in statusData?.architecture_layers"
          :key="layer"
          class="layer-row"
        >
          <div class="layer-name">{{ layer }}</div>
          <div class="layer-modules">
            <span
              v-for="moduleId in modules"
              :key="moduleId"
              class="module-chip"
              :class="getModuleStatus(moduleId)"
              @click="scrollToModule(moduleId)"
            >
              {{ getModuleName(moduleId) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Module Details -->
      <div class="modules-container">
        <h3>📦 模块详情</h3>
        <div
          v-for="module in statusData?.modules"
          :key="module.id"
          :id="'module-' + module.id"
          class="module-card"
          :class="module.status"
        >
          <!-- Module Header -->
          <div class="module-header">
            <div class="module-title">
              <span class="status-icon">{{ getStatusIcon(module.status) }}</span>
              <h4>{{ module.name_zh }} <span class="en-name">{{ module.name }}</span></h4>
            </div>
            <div class="module-progress">
              <span class="progress-text">{{ module.progress }}%</span>
              <div class="mini-progress-bar">
                <div
                  class="mini-progress-fill"
                  :style="{ width: module.progress + '%' }"
                ></div>
              </div>
            </div>
          </div>

          <!-- Description -->
          <p class="module-description">{{ module.description }}</p>

          <!-- Tech Stack -->
          <div class="tech-stack">
            <div v-if="module.tech_stack.languages.length" class="tech-group">
              <span class="tech-label">语言:</span>
              <span
                v-for="lang in module.tech_stack.languages"
                :key="lang"
                class="tech-tag lang"
              >{{ lang }}</span>
            </div>
            <div v-if="module.tech_stack.frameworks.length" class="tech-group">
              <span class="tech-label">框架:</span>
              <span
                v-for="fw in module.tech_stack.frameworks"
                :key="fw"
                class="tech-tag framework"
              >{{ fw }}</span>
            </div>
            <div v-if="module.tech_stack.databases.length" class="tech-group">
              <span class="tech-label">数据库:</span>
              <span
                v-for="db in module.tech_stack.databases"
                :key="db"
                class="tech-tag database"
              >{{ db }}</span>
            </div>
            <div v-if="module.tech_stack.apis.length" class="tech-group">
              <span class="tech-label">API:</span>
              <span
                v-for="api in module.tech_stack.apis"
                :key="api"
                class="tech-tag api"
              >{{ api }}</span>
            </div>
          </div>

          <!-- Key Features -->
          <div v-if="module.key_features.length" class="key-features">
            <h5>核心功能</h5>
            <ul>
              <li
                v-for="(feature, idx) in module.key_features"
                :key="idx"
                :class="{ 'new-feature': feature.startsWith('🆕') }"
              >{{ feature }}</li>
            </ul>
          </div>

          <!-- Dependencies -->
          <div v-if="module.dependencies.length" class="dependencies">
            <span class="dep-label">依赖:</span>
            <span
              v-for="dep in module.dependencies"
              :key="dep"
              class="dep-tag"
            >{{ getModuleName(dep) }}</span>
          </div>

          <!-- Blockers -->
          <div v-if="module.blockers.length" class="blockers">
            <h5>⚠️ 阻塞项</h5>
            <ul>
              <li v-for="(blocker, idx) in module.blockers" :key="idx">{{ blocker }}</li>
            </ul>
          </div>

          <!-- Last Updated -->
          <div class="last-updated">
            最后更新: {{ module.last_updated || 'N/A' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue';

interface TechStack {
  languages: string[];
  frameworks: string[];
  databases: string[];
  apis: string[];
}

interface ModuleInfo {
  id: string;
  name: string;
  name_zh: string;
  description: string;
  status: 'completed' | 'in_progress' | 'planned' | 'blocked';
  progress: number;
  tech_stack: TechStack;
  key_features: string[];
  dependencies: string[];
  blockers: string[];
  last_updated: string;
}

interface ProjectStatusData {
  project_name: string;
  version: string;
  overall_progress: number;
  modules: ModuleInfo[];
  architecture_layers: Record<string, string[]>;
}

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const statusData = ref<ProjectStatusData | null>(null);
const loading = ref(false);
const error = ref('');

const stats = computed(() => {
  const mods = statusData.value?.modules ?? [];
  let total = 0;
  let neu = 0;
  for (const m of mods) {
    total += m.key_features.length;
    neu += m.key_features.filter((f) => f.startsWith('🆕')).length;
  }
  return {
    totalFeatures: total,
    newFeatures: neu,
    completed: mods.filter((m) => m.status === 'completed').length,
    inProgress: mods.filter((m) => m.status === 'in_progress').length,
    planned: mods.filter((m) => m.status === 'planned').length,
    blocked: mods.filter((m) => m.status === 'blocked').length,
  };
});

async function fetchStatus() {
  loading.value = true;
  error.value = '';
  try {
    const resp = await fetch('http://localhost:8000/orchestrator/project_status');
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    statusData.value = await resp.json();
  } catch (err: any) {
    error.value = err.message || '加载失败';
    console.error('Failed to fetch project status:', err);
  } finally {
    loading.value = false;
  }
}

function closePanel() {
  emit('close');
}

function getStatusIcon(status: string): string {
  const icons: Record<string, string> = {
    completed: '✅',
    in_progress: '🔄',
    planned: '📋',
    blocked: '🚫',
  };
  return icons[status] || '❓';
}

function getModuleStatus(moduleId: string): string {
  const module = statusData.value?.modules.find(m => m.id === moduleId);
  return module?.status || 'planned';
}

function getModuleName(moduleId: string): string {
  const module = statusData.value?.modules.find(m => m.id === moduleId);
  return module?.name_zh || moduleId;
}

function scrollToModule(moduleId: string) {
  const el = document.getElementById('module-' + moduleId);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal && !statusData.value) {
    fetchStatus();
  }
});

onMounted(() => {
  if (props.visible) {
    fetchStatus();
  }
});
</script>

<style scoped>
.status-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

.status-panel {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-radius: 16px;
  width: 90%;
  max-width: 1200px;
  height: 90vh;
  overflow-y: auto;
  padding: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  animation: slideUp 0.3s ease;
}

.panel-header {
  position: relative;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid rgba(255, 255, 255, 0.1);
}

.panel-header h2 {
  color: #fff;
  font-size: 28px;
  margin: 0 0 8px 0;
}

.version {
  color: #a0a0a0;
  font-size: 14px;
  margin: 0;
}

.close-btn {
  position: absolute;
  top: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  color: #fff;
  font-size: 24px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: rotate(90deg);
}

.overall-progress {
  margin-bottom: 32px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
}

.progress-label {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  color: #fff;
  font-size: 18px;
  font-weight: 500;
}

.progress-value {
  color: #4ade80;
  font-weight: 700;
}

.progress-bar {
  height: 12px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4ade80 0%, #22c55e 100%);
  transition: width 0.5s ease;
}

.progress-meta {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-num {
  font-size: 22px;
  font-weight: 700;
  color: #e2e8f0;
  line-height: 1;
}
.meta-num.new {
  color: #fbbf24;
  text-shadow: 0 0 12px rgba(251, 191, 36, 0.4);
}
.meta-label {
  font-size: 11px;
  color: #94a3b8;
  letter-spacing: 0.5px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 32px;
}
.stat-card {
  padding: 16px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  text-align: center;
  border: 1px solid rgba(255, 255, 255, 0.06);
  transition: transform 0.2s ease;
}
.stat-card:hover { transform: translateY(-2px); }
.stat-card.completed { border-color: rgba(74, 222, 128, 0.35); }
.stat-card.in_progress { border-color: rgba(96, 165, 250, 0.35); }
.stat-card.planned { border-color: rgba(163, 163, 163, 0.35); }
.stat-card.blocked { border-color: rgba(248, 113, 113, 0.35); }
.stat-icon { font-size: 22px; margin-bottom: 6px; }
.stat-num {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
}
.stat-card.completed .stat-num { color: #4ade80; }
.stat-card.in_progress .stat-num { color: #60a5fa; }
.stat-card.planned .stat-num { color: #a3a3a3; }
.stat-card.blocked .stat-num { color: #f87171; }
.stat-label { font-size: 12px; color: #94a3b8; margin-top: 4px; }

.new-feature {
  background: rgba(251, 191, 36, 0.08);
  border-left: 2px solid #fbbf24;
  padding-left: 8px;
  border-radius: 4px;
  color: #fde68a !important;
  font-weight: 500;
}

.architecture-layers {
  margin-bottom: 32px;
}

.architecture-layers h3 {
  color: #fff;
  font-size: 20px;
  margin-bottom: 16px;
}

.layer-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
}

.layer-name {
  min-width: 100px;
  color: #a0a0a0;
  font-weight: 500;
}

.layer-modules {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.module-chip {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.module-chip.completed {
  background: rgba(74, 222, 128, 0.2);
  color: #4ade80;
  border: 1px solid rgba(74, 222, 128, 0.4);
}

.module-chip.in_progress {
  background: rgba(96, 165, 250, 0.2);
  color: #60a5fa;
  border: 1px solid rgba(96, 165, 250, 0.4);
}

.module-chip.planned {
  background: rgba(163, 163, 163, 0.2);
  color: #a3a3a3;
  border: 1px solid rgba(163, 163, 163, 0.4);
}

.module-chip.blocked {
  background: rgba(248, 113, 113, 0.2);
  color: #f87171;
  border: 1px solid rgba(248, 113, 113, 0.4);
}

.module-chip:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.modules-container h3 {
  color: #fff;
  font-size: 20px;
  margin-bottom: 16px;
}

.module-card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  border-left: 4px solid transparent;
  transition: all 0.3s;
}

.module-card.completed {
  border-left-color: #4ade80;
}

.module-card.in_progress {
  border-left-color: #60a5fa;
}

.module-card.planned {
  border-left-color: #a3a3a3;
}

.module-card.blocked {
  border-left-color: #f87171;
}

.module-card:hover {
  background: rgba(255, 255, 255, 0.08);
  transform: translateX(4px);
}

.module-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.module-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-icon {
  font-size: 20px;
}

.module-title h4 {
  color: #fff;
  margin: 0;
  font-size: 18px;
}

.en-name {
  color: #a0a0a0;
  font-size: 14px;
  font-weight: 400;
}

.module-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-text {
  color: #4ade80;
  font-weight: 600;
  min-width: 45px;
  text-align: right;
}

.mini-progress-bar {
  width: 100px;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4ade80 0%, #22c55e 100%);
  transition: width 0.3s ease;
}

.module-description {
  color: #d0d0d0;
  margin: 0 0 16px 0;
  font-size: 14px;
}

.tech-stack {
  margin-bottom: 16px;
}

.tech-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.tech-label {
  color: #a0a0a0;
  font-size: 13px;
  min-width: 60px;
}

.tech-tag {
  padding: 3px 10px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
}

.tech-tag.lang {
  background: rgba(147, 51, 234, 0.2);
  color: #a78bfa;
  border: 1px solid rgba(147, 51, 234, 0.4);
}

.tech-tag.framework {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
  border: 1px solid rgba(59, 130, 246, 0.4);
}

.tech-tag.database {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.tech-tag.api {
  background: rgba(234, 179, 8, 0.2);
  color: #fbbf24;
  border: 1px solid rgba(234, 179, 8, 0.4);
}

.key-features, .blockers {
  margin-bottom: 16px;
}

.key-features h5, .blockers h5 {
  color: #fff;
  font-size: 14px;
  margin: 0 0 8px 0;
}

.key-features ul, .blockers ul {
  margin: 0;
  padding-left: 20px;
  color: #d0d0d0;
  font-size: 13px;
}

.key-features li {
  margin-bottom: 4px;
}

.blockers li {
  color: #f87171;
  margin-bottom: 4px;
}

.dependencies {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.dep-label {
  color: #a0a0a0;
  font-size: 13px;
}

.dep-tag {
  padding: 3px 10px;
  border-radius: 8px;
  font-size: 12px;
  background: rgba(163, 163, 163, 0.2);
  color: #d0d0d0;
  border: 1px solid rgba(163, 163, 163, 0.3);
}

.last-updated {
  color: #808080;
  font-size: 12px;
  text-align: right;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    transform: translateY(50px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

/* Scrollbar styling */
.status-panel::-webkit-scrollbar {
  width: 8px;
}

.status-panel::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.status-panel::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.status-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>

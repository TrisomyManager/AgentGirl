<template>
  <div v-if="visible" class="status-overlay" @click="closePanel">
    <div class="status-panel" @click.stop>
      <div class="panel-shell">
        <header class="hero-card">
          <div class="hero-copy">
            <p class="eyebrow">工程交接视图</p>
            <div class="hero-headline">
              <h2>{{ statusData?.project_name || 'Companion AI' }}</h2>
              <span class="version-pill">{{ statusData?.version || 'unknown' }}</span>
            </div>
            <p class="hero-summary">
              {{ statusData?.summary || '正在加载项目状态…' }}
            </p>
            <div class="hero-meta">
              <span class="phase-pill">{{ statusData?.current_phase || '等待状态数据' }}</span>
              <span class="muted">最近更新 {{ statusData?.last_updated || 'N/A' }}</span>
            </div>
          </div>

          <div class="hero-actions">
            <button class="ghost-btn" :disabled="loading" @click="loadStatus">
              {{ loading ? '刷新中…' : '刷新状态' }}
            </button>
            <button class="close-btn" @click="closePanel" aria-label="关闭面板">×</button>
          </div>
        </header>

        <div v-if="error" class="callout error">
          <strong>状态加载失败</strong>
          <span>{{ error }}</span>
        </div>

        <section class="overview-grid">
          <article class="glass-card progress-card">
            <div class="section-head">
              <span class="section-label">整体进度</span>
              <span class="progress-value">{{ statusData?.overall_progress || 0 }}%</span>
            </div>
            <div class="progress-track">
              <div
                class="progress-fill"
                :style="{ width: `${statusData?.overall_progress || 0}%` }"
              ></div>
            </div>
            <div class="metric-grid">
              <div class="metric-item">
                <span class="metric-value">{{ stats.completed }}</span>
                <span class="metric-label">已完成模块</span>
              </div>
              <div class="metric-item">
                <span class="metric-value">{{ stats.inProgress }}</span>
                <span class="metric-label">推进中</span>
              </div>
              <div class="metric-item">
                <span class="metric-value accent">{{ stats.newFeatures }}</span>
                <span class="metric-label">本轮新增亮点</span>
              </div>
              <div class="metric-item">
                <span class="metric-value warning">{{ stats.blockers }}</span>
                <span class="metric-label">待处理阻塞</span>
              </div>
            </div>
          </article>

          <article class="glass-card">
            <div class="section-head">
              <span class="section-label">测试快照</span>
              <span class="chip neutral">{{ testSnapshot.command }}</span>
            </div>
            <div class="test-summary">
              <div class="test-stat success">
                <strong>{{ testSnapshot.passed }}</strong>
                <span>通过</span>
              </div>
              <div class="test-stat danger">
                <strong>{{ testSnapshot.failed }}</strong>
                <span>失败</span>
              </div>
              <div v-if="(testSnapshot.skipped ?? 0) > 0" class="test-stat neutral">
                <strong>{{ testSnapshot.skipped }}</strong>
                <span>跳过</span>
              </div>
            </div>
            <ul class="bullet-list compact">
              <li
                v-for="(note, index) in testSnapshot.notes"
                :key="`test-note-${index}`"
              >
                {{ note }}
              </li>
            </ul>
          </article>
        </section>

        <section class="content-grid">
          <article class="glass-card">
            <div class="section-head">
              <span class="section-label">本版本亮点</span>
            </div>
            <ul class="bullet-list">
              <li
                v-for="(highlight, index) in statusData?.recent_highlights || []"
                :key="`highlight-${index}`"
              >
                {{ highlight }}
              </li>
            </ul>
          </article>

          <article class="glass-card">
            <div class="section-head">
              <span class="section-label">下一步聚焦</span>
            </div>
            <div class="focus-stack">
              <div
                v-for="item in statusData?.next_focus || []"
                :key="item.title"
                class="focus-card"
              >
                <strong>{{ item.title }}</strong>
                <p>{{ item.detail }}</p>
              </div>
            </div>
          </article>

          <article class="glass-card">
            <div class="section-head">
              <span class="section-label">当前风险</span>
            </div>
            <div class="focus-stack">
              <div
                v-for="item in statusData?.risks || []"
                :key="item.title"
                class="focus-card risk"
              >
                <strong>{{ item.title }}</strong>
                <p>{{ item.detail }}</p>
              </div>
            </div>
          </article>
        </section>

        <section class="glass-card prompt-debug-card">
          <div class="section-head prompt-debug-head">
            <div>
              <span class="section-label">Prompt 调试</span>
              <p class="muted small">
                「最近一轮」来自主聊天写入的快照；「假设用户句」调用
                <code>POST /orchestrator/debug/prompt_preview</code>，走意图 + 记忆召回后拼装
                system prompt（不调 LLM）。
              </p>
            </div>
            <div class="prompt-debug-actions">
              <button
                class="ghost-btn"
                type="button"
                :disabled="promptLoading"
                @click="loadDebugPrompt"
              >
                {{ promptLoading ? '加载中…' : '加载最近 system prompt' }}
              </button>
              <button
                class="ghost-btn"
                type="button"
                :disabled="!promptText || promptCopying"
                @click="copyPromptToClipboard"
              >
                {{ promptCopying ? '已复制' : '复制全文' }}
              </button>
              <button
                class="ghost-btn"
                type="button"
                :disabled="!promptText"
                @click="downloadPromptTxt"
              >
                下载 .txt
              </button>
            </div>
          </div>
          <div class="prompt-preview-controls">
            <label class="prompt-field">
              <span class="prompt-field-label">session_id</span>
              <input v-model="promptPreviewSessionId" type="text" autocomplete="off" />
            </label>
            <label class="prompt-field">
              <span class="prompt-field-label">user_id</span>
              <input v-model="promptPreviewUserId" type="text" autocomplete="off" />
            </label>
            <button class="ghost-btn prompt-fill-btn" type="button" @click="fillExamplePreview">
              填入示例句
            </button>
          </div>
          <label class="prompt-field prompt-field-block">
            <span class="prompt-field-label">假设用户消息</span>
            <textarea
              v-model="promptPreviewMessage"
              rows="3"
              class="prompt-preview-textarea"
              spellcheck="false"
            ></textarea>
          </label>
          <div class="prompt-preview-row">
            <button
              class="ghost-btn primary-ghost"
              type="button"
              :disabled="previewLoading"
              @click="loadPromptPreview"
            >
              {{ previewLoading ? '拼装中…' : '预览拼装 prompt' }}
            </button>
            <span v-if="promptSource" class="muted small prompt-source-hint">{{ promptSourceLabel }}</span>
          </div>
          <p v-if="promptError" class="callout error compact-callout">
            <strong>加载失败</strong>
            <span>{{ promptError }}</span>
          </p>
          <p v-else-if="promptHint" class="muted">{{ promptHint }}</p>
          <p v-if="promptMeta" class="prompt-meta muted">{{ promptMeta }}</p>
          <pre v-if="promptText" class="prompt-debug-pre">{{ promptText }}</pre>
        </section>

        <section class="glass-card">
          <div class="section-head">
            <span class="section-label">里程碑节奏</span>
          </div>
          <div class="milestone-grid">
            <article
              v-for="milestone in statusData?.milestones || []"
              :key="milestone.title"
              class="milestone-card"
              :class="milestone.status"
            >
              <div class="milestone-top">
                <span class="chip" :class="milestone.status">
                  {{ getMilestoneLabel(milestone.status) }}
                </span>
                <span class="milestone-owner">{{ milestone.owner }}</span>
              </div>
              <h3>{{ milestone.title }}</h3>
              <p>{{ milestone.detail }}</p>
            </article>
          </div>
        </section>

        <section
          v-if="statusData?.release_notes && statusData.release_notes.items.length"
          class="glass-card release-card"
        >
          <div class="section-head release-head">
            <div>
              <span class="section-label">本轮交付</span>
              <h3 class="release-title">{{ statusData.release_notes.title }}</h3>
            </div>
            <span v-if="statusData.release_notes.pr_branch" class="chip neutral release-branch">
              {{ statusData.release_notes.pr_branch }}
            </span>
          </div>
          <p v-if="statusData.release_notes.summary" class="release-summary">
            {{ statusData.release_notes.summary }}
          </p>
          <div class="release-meta-row">
            <span
              v-for="(count, cat) in releaseCategoryCounts"
              :key="cat"
              class="chip"
              :class="getReleaseCategoryClass(cat)"
            >
              {{ getReleaseCategoryLabel(cat) }} · {{ count }}
            </span>
          </div>
          <div class="release-grid">
            <article
              v-for="(item, index) in statusData.release_notes.items"
              :key="`release-${index}`"
              class="release-item"
              :class="getReleaseCategoryClass(item.category)"
            >
              <div class="release-item-top">
                <span class="chip" :class="getReleaseCategoryClass(item.category)">
                  {{ getReleaseCategoryLabel(item.category) }}
                </span>
                <strong>{{ item.title }}</strong>
              </div>
              <p class="release-detail">{{ item.detail }}</p>
              <p v-if="item.impact" class="release-impact">
                <span class="impact-label">影响：</span>{{ item.impact }}
              </p>
              <div v-if="item.refs.length" class="release-refs">
                <code v-for="ref in item.refs" :key="ref" class="release-ref">{{ ref }}</code>
              </div>
            </article>
          </div>
        </section>

        <section class="glass-card">
          <div class="section-head">
            <span class="section-label">架构分层</span>
          </div>
          <div class="layer-stack">
            <div
              v-for="(modules, layer) in statusData?.architecture_layers"
              :key="layer"
              class="layer-row"
            >
              <div class="layer-name">{{ layer }}</div>
              <div class="layer-modules">
                <button
                  v-for="moduleId in modules"
                  :key="moduleId"
                  class="module-chip"
                  :class="getModuleStatus(moduleId)"
                  @click="scrollToModule(moduleId)"
                >
                  {{ getModuleName(moduleId) }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section class="module-section">
          <div class="section-head">
            <span class="section-label">模块详情</span>
            <span class="muted">按成熟度与风险查看当前实现面</span>
          </div>

          <div class="modules-grid">
            <article
              v-for="module in statusData?.modules"
              :key="module.id"
              :id="`module-${module.id}`"
              class="module-card"
              :class="module.status"
            >
              <div class="module-card-top">
                <div>
                  <div class="module-name-row">
                    <span class="status-dot" :class="module.status"></span>
                    <h3>{{ module.name_zh }}</h3>
                  </div>
                  <p class="module-subtitle">{{ module.name }}</p>
                </div>
                <span class="chip" :class="module.status">
                  {{ getStatusLabel(module.status) }}
                </span>
              </div>

              <p class="module-description">{{ module.description }}</p>

              <div class="module-progress">
                <div class="progress-track mini">
                  <div
                    class="progress-fill"
                    :style="{ width: `${module.progress}%` }"
                  ></div>
                </div>
                <span class="progress-mini-label">{{ module.progress }}%</span>
              </div>

              <div class="tag-groups">
                <div v-if="module.tech_stack.languages.length" class="tag-group">
                  <span class="tag-title">语言</span>
                  <span
                    v-for="lang in module.tech_stack.languages"
                    :key="lang"
                    class="pill lang"
                  >
                    {{ lang }}
                  </span>
                </div>
                <div v-if="module.tech_stack.frameworks.length" class="tag-group">
                  <span class="tag-title">框架</span>
                  <span
                    v-for="framework in module.tech_stack.frameworks"
                    :key="framework"
                    class="pill framework"
                  >
                    {{ framework }}
                  </span>
                </div>
                <div v-if="module.tech_stack.databases.length" class="tag-group">
                  <span class="tag-title">数据层</span>
                  <span
                    v-for="database in module.tech_stack.databases"
                    :key="database"
                    class="pill database"
                  >
                    {{ database }}
                  </span>
                </div>
                <div v-if="module.tech_stack.apis.length" class="tag-group">
                  <span class="tag-title">接口</span>
                  <span
                    v-for="api in module.tech_stack.apis"
                    :key="api"
                    class="pill api"
                  >
                    {{ api }}
                  </span>
                </div>
              </div>

              <div v-if="module.key_features.length" class="detail-block">
                <h4>核心能力</h4>
                <ul class="bullet-list compact">
                  <li
                    v-for="(feature, index) in module.key_features"
                    :key="`${module.id}-feature-${index}`"
                    :class="{ featured: feature.startsWith('🆕') }"
                  >
                    {{ feature }}
                  </li>
                </ul>
              </div>

              <div v-if="module.dependencies.length" class="detail-block">
                <h4>依赖边界</h4>
                <div class="dependency-row">
                  <span
                    v-for="dependency in module.dependencies"
                    :key="dependency"
                    class="dependency-pill"
                  >
                    {{ getModuleName(dependency) }}
                  </span>
                </div>
              </div>

              <div v-if="module.blockers.length" class="detail-block">
                <h4>风险 / 阻塞</h4>
                <ul class="bullet-list compact danger-list">
                  <li
                    v-for="(blocker, index) in module.blockers"
                    :key="`${module.id}-blocker-${index}`"
                  >
                    {{ blocker }}
                  </li>
                </ul>
              </div>

              <div class="module-footer">
                <span>最近更新 {{ module.last_updated || 'N/A' }}</span>
              </div>
            </article>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

interface TechStack {
  languages: string[];
  frameworks: string[];
  databases: string[];
  apis: string[];
}

interface FocusItem {
  title: string;
  detail: string;
}

interface MilestoneInfo {
  title: string;
  owner: string;
  status: 'done' | 'active' | 'queued' | string;
  detail: string;
}

interface TestSnapshot {
  command: string;
  passed: number;
  failed: number;
  skipped?: number;
  notes: string[];
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

interface ReleaseNoteItem {
  category: string;
  title: string;
  detail: string;
  impact: string;
  refs: string[];
}

interface ReleaseSection {
  title: string;
  pr_branch: string;
  summary: string;
  items: ReleaseNoteItem[];
}

interface ProjectStatusData {
  project_name: string;
  version: string;
  current_phase: string;
  summary: string;
  last_updated: string;
  overall_progress: number;
  recent_highlights: string[];
  next_focus: FocusItem[];
  risks: FocusItem[];
  milestones: MilestoneInfo[];
  test_snapshot: TestSnapshot;
  modules: ModuleInfo[];
  architecture_layers: Record<string, string[]>;
  release_notes?: ReleaseSection;
}

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
  'http://127.0.0.1:8000';

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const statusData = ref<ProjectStatusData | null>(null);
const loading = ref(false);
const error = ref('');

const promptText = ref('');
const promptMeta = ref('');
const promptLoading = ref(false);
const previewLoading = ref(false);
const promptCopying = ref(false);
const promptError = ref('');
const promptHint = ref(
  '打开本面板后点击按钮；若尚未聊天，接口会返回提示。发送一条主聊天消息后再加载可看到完整 prompt。',
);
const promptSource = ref<'snapshot' | 'preview' | null>(null);
const promptPreviewSessionId = ref('status-panel-preview');
const promptPreviewUserId = ref('status-panel-user');
const promptPreviewMessage = ref('');

const promptSourceLabel = computed(() => {
  if (promptSource.value === 'preview') return '来源：prompt_preview（假设用户句）';
  if (promptSource.value === 'snapshot') return '来源：最近一轮主聊天快照';
  return '';
});

const testSnapshot = computed<TestSnapshot>(() => {
  return (
    statusData.value?.test_snapshot ?? {
      command: 'N/A',
      passed: 0,
      failed: 0,
      skipped: 0,
      notes: [],
    }
  );
});

const stats = computed(() => {
  const modules = statusData.value?.modules ?? [];
  return {
    completed: modules.filter((module) => module.status === 'completed').length,
    inProgress: modules.filter((module) => module.status === 'in_progress').length,
    blockers: modules.reduce((count, module) => count + module.blockers.length, 0),
    newFeatures: modules.reduce(
      (count, module) =>
        count + module.key_features.filter((feature) => feature.startsWith('🆕')).length,
      0,
    ),
  };
});

const releaseCategoryCounts = computed<Record<string, number>>(() => {
  const items = statusData.value?.release_notes?.items ?? [];
  const counts: Record<string, number> = {};
  for (const item of items) {
    counts[item.category] = (counts[item.category] ?? 0) + 1;
  }
  return counts;
});

async function loadDebugPrompt() {
  promptLoading.value = true;
  previewLoading.value = false;
  promptError.value = '';
  promptHint.value = '';
  promptSource.value = 'snapshot';
  try {
    const response = await fetch(`${API_BASE_URL}/orchestrator/debug/system_prompt`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = (await response.json()) as {
      system_prompt?: string | null;
      updated_at?: string | null;
      session_id?: string | null;
      user_id?: string | null;
      prompt_length?: number;
      hint?: string;
    };
    if (data.hint && !data.system_prompt) {
      promptHint.value = data.hint;
      promptText.value = '';
      promptMeta.value = '';
      return;
    }
    promptText.value = data.system_prompt ?? '';
    const parts: string[] = [];
    if (data.updated_at) parts.push(`更新于 ${data.updated_at}`);
    if (data.session_id) parts.push(`session ${data.session_id}`);
    if (data.user_id) parts.push(`user ${data.user_id}`);
    if (typeof data.prompt_length === 'number') parts.push(`${data.prompt_length} 字符`);
    promptMeta.value = parts.join(' · ');
    if (!promptText.value) {
      promptHint.value = data.hint || '当前没有可用的 system prompt 快照。';
    }
  } catch (fetchError) {
    promptError.value =
      fetchError instanceof Error ? fetchError.message : '未能加载调试数据';
  } finally {
    promptLoading.value = false;
  }
}

function fillExamplePreview() {
  promptPreviewSessionId.value = 'status-panel-preview';
  promptPreviewUserId.value = 'status-panel-user';
  promptPreviewMessage.value = '我叫阿暖测试员，我喜欢喝燕麦拿铁。今天北京天气怎么样？';
}

async function loadPromptPreview() {
  const msg = promptPreviewMessage.value.trim();
  if (!msg) {
    promptError.value = '请先填写「假设用户消息」';
    return;
  }
  previewLoading.value = true;
  promptLoading.value = false;
  promptError.value = '';
  promptHint.value = '';
  promptSource.value = 'preview';
  try {
    const response = await fetch(`${API_BASE_URL}/orchestrator/debug/prompt_preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: promptPreviewSessionId.value.trim() || 'status-panel-preview',
        user: { user_id: promptPreviewUserId.value.trim() || 'anonymous' },
        user_message: msg,
        platform: 'app',
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = (await response.json()) as {
      system_prompt?: string;
      prompt_length?: number;
      session_id?: string;
      user_id?: string;
      turn_id?: string;
    };
    promptText.value = data.system_prompt ?? '';
    const parts: string[] = [];
    if (data.turn_id) parts.push(`turn ${data.turn_id}`);
    if (data.session_id) parts.push(`session ${data.session_id}`);
    if (data.user_id) parts.push(`user ${data.user_id}`);
    if (typeof data.prompt_length === 'number') parts.push(`${data.prompt_length} 字符`);
    promptMeta.value = parts.join(' · ');
    if (!promptText.value) {
      promptHint.value = '接口返回空 prompt。';
    }
  } catch (fetchError) {
    promptError.value =
      fetchError instanceof Error ? fetchError.message : '未能加载预览数据';
  } finally {
    previewLoading.value = false;
  }
}

async function copyPromptToClipboard() {
  if (!promptText.value) return;
  promptCopying.value = true;
  try {
    await navigator.clipboard.writeText(promptText.value);
  } catch {
    promptError.value = '复制失败：浏览器未授权剪贴板';
  } finally {
    setTimeout(() => {
      promptCopying.value = false;
    }, 1200);
  }
}

function downloadPromptTxt() {
  if (!promptText.value) return;
  const blob = new Blob([promptText.value], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  a.href = url;
  a.download = `system-prompt-${stamp}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

async function loadStatus() {
  loading.value = true;
  error.value = '';

  try {
    const response = await fetch(`${API_BASE_URL}/orchestrator/project_status`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    statusData.value = (await response.json()) as ProjectStatusData;
  } catch (fetchError) {
    error.value =
      fetchError instanceof Error ? fetchError.message : '未能获取项目状态数据';
  } finally {
    loading.value = false;
  }
}

function closePanel() {
  emit('close');
}

function getStatusLabel(status: ModuleInfo['status']): string {
  const labels: Record<ModuleInfo['status'], string> = {
    completed: '已完成',
    in_progress: '推进中',
    planned: '规划中',
    blocked: '受阻',
  };
  return labels[status];
}

function getMilestoneLabel(status: string): string {
  const labels: Record<string, string> = {
    done: '已交付',
    active: '推进中',
    queued: '排队中',
  };
  return labels[status] || status;
}

function getReleaseCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    feature: '新特性',
    fix: '修复',
    docs: '文档',
    chore: '工程',
    infra: '基础设施',
  };
  return labels[category] || category;
}

function getReleaseCategoryClass(category: string): string {
  // Map to CSS class names that mirror the existing chip color tokens.
  const classes: Record<string, string> = {
    feature: 'release-feature',
    fix: 'release-fix',
    docs: 'release-docs',
    chore: 'release-chore',
    infra: 'release-infra',
  };
  return classes[category] || 'release-other';
}

function getModuleStatus(moduleId: string): ModuleInfo['status'] | 'planned' {
  const module = statusData.value?.modules.find((item) => item.id === moduleId);
  return module?.status || 'planned';
}

function getModuleName(moduleId: string): string {
  const module = statusData.value?.modules.find((item) => item.id === moduleId);
  return module?.name_zh || moduleId;
}

function scrollToModule(moduleId: string) {
  const element = document.getElementById(`module-${moduleId}`);
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

watch(
  () => props.visible,
  (isVisible) => {
    if (isVisible) {
      void loadStatus();
    }
  },
);

onMounted(() => {
  if (props.visible) {
    void loadStatus();
  }
});
</script>

<style scoped>
.prompt-debug-head {
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.prompt-debug-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.prompt-preview-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: flex-end;
  margin-top: 12px;
}

.prompt-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}

.prompt-field-block {
  width: 100%;
  margin-top: 10px;
}

.prompt-field-label {
  color: rgba(255, 255, 255, 0.55);
}

.prompt-field input {
  min-width: 180px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  font-size: 0.85rem;
}

.prompt-preview-textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  font-size: 0.85rem;
  line-height: 1.45;
  resize: vertical;
  font-family: inherit;
}

.prompt-preview-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.primary-ghost {
  border-color: rgba(96, 165, 250, 0.45);
  color: #bfdbfe;
}

.prompt-source-hint {
  font-size: 0.8rem;
}

.prompt-fill-btn {
  align-self: flex-end;
}

.prompt-debug-head .small {
  margin: 4px 0 0;
  font-size: 0.85rem;
  line-height: 1.4;
}

.compact-callout {
  margin-top: 0;
}

.prompt-meta {
  margin: 8px 0 0;
  font-size: 0.8rem;
}

.prompt-debug-pre {
  margin: 12px 0 0;
  max-height: 320px;
  overflow: auto;
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.status-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(233, 69, 96, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.18), transparent 26%),
    rgba(6, 10, 22, 0.82);
  backdrop-filter: blur(12px);
}

.status-panel {
  width: min(1320px, 100%);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 28px;
  background:
    linear-gradient(180deg, rgba(19, 27, 46, 0.98), rgba(9, 14, 25, 0.98));
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
}

.panel-shell {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px;
}

.hero-card,
.glass-card,
.module-card {
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(255, 255, 255, 0.04);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(233, 69, 96, 0.18), transparent 35%),
    radial-gradient(circle at bottom right, rgba(59, 130, 246, 0.18), transparent 30%),
    rgba(255, 255, 255, 0.04);
}

.hero-copy {
  max-width: 860px;
}

.eyebrow {
  margin: 0 0 10px;
  color: #fda4af;
  font-size: 12px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.hero-headline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-headline h2 {
  margin: 0;
  color: #f8fafc;
  font-size: clamp(28px, 4vw, 42px);
  line-height: 1.05;
}

.version-pill,
.phase-pill,
.chip,
.pill,
.dependency-pill,
.ghost-btn,
.module-chip,
.close-btn {
  border-radius: 999px;
}

.version-pill {
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  font-size: 13px;
}

.hero-summary {
  margin: 14px 0 0;
  color: #cbd5e1;
  font-size: 15px;
  line-height: 1.7;
}

.hero-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.phase-pill {
  padding: 8px 14px;
  background: rgba(251, 191, 36, 0.14);
  color: #fde68a;
  font-size: 13px;
  border: 1px solid rgba(251, 191, 36, 0.18);
}

.muted {
  color: #94a3b8;
  font-size: 13px;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.ghost-btn,
.close-btn {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #e2e8f0;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease;
}

.ghost-btn {
  padding: 10px 16px;
  font-size: 13px;
}

.close-btn {
  width: 42px;
  height: 42px;
  font-size: 24px;
  line-height: 1;
}

.ghost-btn:hover,
.close-btn:hover,
.module-chip:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.18);
}

.ghost-btn:disabled {
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
}

.callout {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-radius: 18px;
}

.callout.error {
  border: 1px solid rgba(248, 113, 113, 0.25);
  background: rgba(127, 29, 29, 0.32);
  color: #fecaca;
}

.overview-grid,
.content-grid {
  display: grid;
  gap: 20px;
}

.overview-grid {
  grid-template-columns: 1.4fr 1fr;
}

.content-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.glass-card {
  border-radius: 24px;
  padding: 22px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-label {
  color: #f8fafc;
  font-size: 15px;
  font-weight: 600;
}

.progress-card {
  background:
    radial-gradient(circle at right, rgba(74, 222, 128, 0.12), transparent 35%),
    rgba(255, 255, 255, 0.04);
}

.progress-value,
.metric-value,
.test-stat strong,
.progress-mini-label {
  font-variant-numeric: tabular-nums;
}

.progress-value {
  color: #86efac;
  font-size: 34px;
  font-weight: 700;
}

.progress-track {
  height: 12px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.07);
  border-radius: 999px;
}

.progress-track.mini {
  height: 8px;
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #e94560 0%, #fb7185 42%, #86efac 100%);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.metric-item {
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
}

.metric-value {
  display: block;
  color: #f8fafc;
  font-size: 26px;
  font-weight: 700;
}

.metric-value.accent {
  color: #fda4af;
}

.metric-value.warning {
  color: #fbbf24;
}

.metric-label {
  display: block;
  margin-top: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
  font-size: 12px;
}

.chip.neutral {
  max-width: 100%;
  text-align: right;
}

.chip.completed,
.chip.done {
  background: rgba(34, 197, 94, 0.15);
  color: #86efac;
}

.chip.in_progress,
.chip.active {
  background: rgba(59, 130, 246, 0.15);
  color: #93c5fd;
}

.chip.planned,
.chip.queued {
  background: rgba(148, 163, 184, 0.15);
  color: #cbd5e1;
}

.chip.blocked {
  background: rgba(248, 113, 113, 0.15);
  color: #fca5a5;
}

.test-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.test-stat {
  padding: 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.03);
}

.test-stat strong {
  display: block;
  font-size: 32px;
}

.test-stat span {
  color: #cbd5e1;
  font-size: 13px;
}

.test-stat.success strong {
  color: #86efac;
}

.test-stat.danger strong {
  color: #fca5a5;
}

.test-stat.neutral strong {
  color: #94a3b8;
}

.bullet-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.bullet-list li {
  position: relative;
  padding-left: 18px;
  color: #dbe4f0;
  font-size: 14px;
  line-height: 1.6;
}

.bullet-list li::before {
  content: '';
  position: absolute;
  top: 10px;
  left: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #fb7185;
  box-shadow: 0 0 18px rgba(251, 113, 133, 0.5);
}

.bullet-list.compact {
  gap: 8px;
}

.focus-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.focus-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(255, 255, 255, 0.03);
}

.focus-card strong {
  display: block;
  color: #f8fafc;
  font-size: 14px;
}

.focus-card p {
  margin: 8px 0 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.65;
}

.focus-card.risk {
  border-color: rgba(248, 113, 113, 0.1);
  background: rgba(127, 29, 29, 0.18);
}

.milestone-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.milestone-card {
  padding: 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.milestone-card.done {
  border-color: rgba(34, 197, 94, 0.18);
}

.milestone-card.active {
  border-color: rgba(59, 130, 246, 0.18);
}

.milestone-card.queued {
  border-color: rgba(148, 163, 184, 0.18);
}

.milestone-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.milestone-owner {
  color: #94a3b8;
  font-size: 12px;
}

.milestone-card h3 {
  margin: 14px 0 8px;
  color: #f8fafc;
  font-size: 17px;
}

.milestone-card p {
  margin: 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.65;
}

.layer-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.layer-row {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 16px;
  align-items: start;
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
}

.layer-name {
  padding-top: 4px;
  color: #f8fafc;
  font-size: 14px;
  font-weight: 600;
}

.layer-modules {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.module-chip {
  border: 1px solid transparent;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  color: #e2e8f0;
  font-size: 13px;
  cursor: pointer;
}

.module-chip.completed {
  border-color: rgba(34, 197, 94, 0.2);
  color: #86efac;
}

.module-chip.in_progress {
  border-color: rgba(59, 130, 246, 0.2);
  color: #93c5fd;
}

.module-chip.planned {
  border-color: rgba(148, 163, 184, 0.2);
  color: #cbd5e1;
}

.module-chip.blocked {
  border-color: rgba(248, 113, 113, 0.2);
  color: #fca5a5;
}

.module-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modules-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.module-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
  border-radius: 22px;
}

.module-card.completed {
  border-color: rgba(34, 197, 94, 0.16);
}

.module-card.in_progress {
  border-color: rgba(59, 130, 246, 0.16);
}

.module-card.planned {
  border-color: rgba(148, 163, 184, 0.16);
}

.module-card.blocked {
  border-color: rgba(248, 113, 113, 0.16);
}

.module-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.module-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.completed {
  background: #4ade80;
  box-shadow: 0 0 16px rgba(74, 222, 128, 0.6);
}

.status-dot.in_progress {
  background: #60a5fa;
  box-shadow: 0 0 16px rgba(96, 165, 250, 0.6);
}

.status-dot.planned {
  background: #cbd5e1;
}

.status-dot.blocked {
  background: #f87171;
  box-shadow: 0 0 16px rgba(248, 113, 113, 0.4);
}

.module-card h3 {
  margin: 0;
  color: #f8fafc;
  font-size: 18px;
}

.module-subtitle {
  margin: 6px 0 0 20px;
  color: #94a3b8;
  font-size: 12px;
}

.module-description {
  margin: 0;
  color: #dbe4f0;
  font-size: 14px;
  line-height: 1.65;
}

.module-progress {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  align-items: center;
}

.progress-mini-label {
  color: #cbd5e1;
  font-size: 13px;
}

.tag-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.tag-title {
  color: #94a3b8;
  font-size: 12px;
  min-width: 52px;
}

.pill,
.dependency-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid transparent;
  font-size: 12px;
}

.pill.lang {
  background: rgba(251, 113, 133, 0.12);
  color: #fda4af;
}

.pill.framework {
  background: rgba(59, 130, 246, 0.12);
  color: #93c5fd;
}

.pill.database {
  background: rgba(34, 197, 94, 0.12);
  color: #86efac;
}

.pill.api {
  background: rgba(251, 191, 36, 0.12);
  color: #fde68a;
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-block h4 {
  margin: 0;
  color: #f8fafc;
  font-size: 14px;
}

.bullet-list li.featured {
  color: #ffe4e6;
}

.dependency-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.dependency-pill {
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
}

.danger-list li {
  color: #fecaca;
}

.danger-list li::before {
  background: #f87171;
  box-shadow: 0 0 18px rgba(248, 113, 113, 0.45);
}

.module-footer {
  display: flex;
  justify-content: flex-end;
  color: #94a3b8;
  font-size: 12px;
}

/* ───────── 本轮交付 ───────── */
.release-card {
  background:
    radial-gradient(circle at top right, rgba(110, 231, 183, 0.14), transparent 40%),
    radial-gradient(circle at bottom left, rgba(192, 132, 252, 0.12), transparent 38%),
    rgba(255, 255, 255, 0.04);
}

.release-head {
  align-items: flex-start;
}

.release-title {
  margin: 4px 0 0;
  font-size: 18px;
  color: #f8fafc;
  letter-spacing: 0.01em;
}

.release-branch {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
}

.release-summary {
  margin: 0 0 14px;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.7;
}

.release-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.release-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.release-item {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 14px 16px;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: transform 0.18s ease, border-color 0.18s ease;
}

.release-item:hover {
  transform: translateY(-1px);
  border-color: rgba(255, 255, 255, 0.16);
}

.release-item-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.release-item-top strong {
  color: #f8fafc;
  font-size: 14px;
  line-height: 1.4;
}

.release-detail {
  margin: 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.65;
}

.release-impact {
  margin: 0;
  font-size: 12.5px;
  color: #d1fae5;
  line-height: 1.6;
}

.impact-label {
  color: #6ee7b7;
  font-weight: 600;
}

.release-refs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.release-ref {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 11px;
  color: #94a3b8;
  font-family: ui-monospace, SFMono-Regular, monospace;
  word-break: break-all;
}

/* Category-tinted chips and item left border. */
.chip.release-feature {
  background: rgba(110, 231, 183, 0.12);
  border: 1px solid rgba(110, 231, 183, 0.32);
  color: #6ee7b7;
}

.chip.release-fix {
  background: rgba(251, 191, 36, 0.12);
  border: 1px solid rgba(251, 191, 36, 0.32);
  color: #fcd34d;
}

.chip.release-docs {
  background: rgba(96, 165, 250, 0.14);
  border: 1px solid rgba(96, 165, 250, 0.32);
  color: #93c5fd;
}

.chip.release-chore {
  background: rgba(192, 132, 252, 0.14);
  border: 1px solid rgba(192, 132, 252, 0.32);
  color: #d8b4fe;
}

.chip.release-infra {
  background: rgba(56, 189, 248, 0.14);
  border: 1px solid rgba(56, 189, 248, 0.32);
  color: #7dd3fc;
}

.chip.release-other {
  background: rgba(148, 163, 184, 0.14);
  border: 1px solid rgba(148, 163, 184, 0.32);
  color: #cbd5e1;
}

.release-item.release-feature {
  border-left: 3px solid rgba(110, 231, 183, 0.6);
}

.release-item.release-fix {
  border-left: 3px solid rgba(251, 191, 36, 0.6);
}

.release-item.release-docs {
  border-left: 3px solid rgba(96, 165, 250, 0.6);
}

.release-item.release-chore {
  border-left: 3px solid rgba(192, 132, 252, 0.6);
}

.release-item.release-infra {
  border-left: 3px solid rgba(56, 189, 248, 0.6);
}

@media (max-width: 1100px) {
  .overview-grid,
  .content-grid,
  .milestone-grid,
  .modules-grid,
  .release-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }
}

@media (max-width: 720px) {
  .status-overlay {
    padding: 12px;
  }

  .panel-shell {
    padding: 16px;
  }

  .hero-card,
  .glass-card,
  .module-card {
    border-radius: 20px;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .layer-row {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .hero-actions {
    justify-content: space-between;
  }
}
</style>

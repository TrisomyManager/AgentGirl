/**
 * Companion AI — Web Configuration Page
 * Pure vanilla JS, no framework dependency
 */

// ============================================================
// Configuration Schema
// ============================================================
const CONFIG_SCHEMA = {
  // API Keys
  openai_api_key:       { type: 'password', label: 'OpenAI API Key', group: 'llm', required: true },
  openai_base_url:      { type: 'text', label: 'OpenAI Base URL', group: 'llm', required: false, placeholder: 'https://api.openai.com/v1' },
  anthropic_api_key:    { type: 'password', label: 'Anthropic API Key', group: 'llm', required: true },
  anthropic_base_url:   { type: 'text', label: 'Anthropic Base URL', group: 'llm', required: false, placeholder: 'https://api.anthropic.com/v1' },
  tts_api_key:          { type: 'password', label: 'TTS API Key', group: 'voice', required: false },
  tts_base_url:         { type: 'text', label: 'TTS Base URL', group: 'voice', required: false, placeholder: 'https://api.fish.audio/v1' },
  whisper_api_key:      { type: 'password', label: 'Whisper API Key', group: 'voice', required: false },
  whisper_base_url:     { type: 'text', label: 'Whisper Base URL', group: 'voice', required: false, placeholder: 'https://api.openai.com/v1' },
  action_api_key:       { type: 'password', label: '2D 动作生成 API Key', group: 'action', required: false },
  action_base_url:      { type: 'text', label: '2D 动作 Base URL', group: 'action', required: false, placeholder: 'https://dashscope.aliyuncs.com/api/v1' },

  // Model Selection
  default_llm_model:    { type: 'select', label: '默认对话模型', options: ['gpt-4o', 'gpt-4o-mini', 'claude-3-5-sonnet', 'claude-3-opus'], default: 'gpt-4o' },
  reasoning_llm_model:  { type: 'select', label: '推理模型', options: ['o3-mini', 'o1', 'claude-3-opus', 'gpt-4o'], default: 'o3-mini' },
  tts_provider:         { type: 'select', label: 'TTS 提供商', options: ['fish_audio', 'chattts', 'openai'], default: 'fish_audio' },
  default_voice_id:     { type: 'text', label: '语音 ID', default: 'zh-CN-XiaoxiaoNeural' },

  // Feature Flags
  lite_mode:                    { type: 'toggle', label: 'Lite Mode', desc: '本地开发模式（无需 Docker / Redis / PostgreSQL / Neo4j）' },
  enable_voice:                 { type: 'toggle', label: '启用语音', desc: '语音合成与语音识别功能' },
  enable_action_2d:             { type: 'toggle', label: '启用 2D 动作', desc: '2D 角色动作生成功能' },
  enable_knowledge_graph:       { type: 'toggle', label: '启用知识图谱', desc: '基于 Neo4j 的知识图谱功能' },
  enable_device_coordination:   { type: 'toggle', label: '启用跨设备', desc: '跨设备协调与同步功能' },
  enable_memory_pipeline:       { type: 'toggle', label: '启用记忆流水线', desc: '长期记忆存储与检索功能' },
};

const SERVICES = [
  { name: 'core_orchestrator', port: 8000, label: '核心编排器' },
  { name: 'persona_engine',    port: 8001, label: '人格引擎' },
  { name: 'memory_system',     port: 8002, label: '记忆系统' },
  { name: 'voice_layer',       port: 8003, label: '语音层' },
  { name: 'action_layer',      port: 8004, label: '动作层' },
];

const STORAGE_KEY = 'companion_ai_config';

// Default config values
const DEFAULT_CONFIG = {
  openai_api_key: '',
  openai_base_url: '',
  anthropic_api_key: '',
  anthropic_base_url: '',
  tts_api_key: '',
  tts_base_url: '',
  whisper_api_key: '',
  whisper_base_url: '',
  action_api_key: '',
  action_base_url: '',
  default_llm_model: 'gpt-4o',
  reasoning_llm_model: 'o3-mini',
  tts_provider: 'fish_audio',
  default_voice_id: 'zh-CN-XiaoxiaoNeural',
  lite_mode: false,
  enable_voice: true,
  enable_action_2d: true,
  enable_knowledge_graph: true,
  enable_device_coordination: true,
  enable_memory_pipeline: true,
};

// ============================================================
// State
// ============================================================
let currentConfig = { ...DEFAULT_CONFIG };
let activeSection = 'api-keys';

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  loadFromStorage();
  renderAll();
  setupNavigation();
  setupMobileMenu();
  setupFormListeners();
  setupTestButtons();
  setupActionButtons();
  updateLiteModeUI();
});

// ============================================================
// Rendering
// ============================================================
function renderAll() {
  renderApiKeysSection();
  renderModelSection();
  renderFeatureSection();
  renderCommandSection();
}

function renderApiKeysSection() {
  const container = document.getElementById('api-keys-content');
  if (!container) return;

  const llmPairs = [
    { key: 'openai_api_key', base: 'openai_base_url' },
    { key: 'anthropic_api_key', base: 'anthropic_base_url' },
  ];
  const voicePairs = [
    { key: 'tts_api_key', base: 'tts_base_url' },
    { key: 'whisper_api_key', base: 'whisper_base_url' },
  ];
  const actionPairs = [
    { key: 'action_api_key', base: 'action_base_url' },
  ];

  container.innerHTML = `
    <div class="api-group">
      <h3 style="font-size:0.95rem;color:var(--accent-primary);margin-bottom:16px;display:flex;align-items:center;gap:8px;">
        <span>🤖</span> LLM 大语言模型
      </h3>
      <div class="input-group">
        ${llmPairs.map(p => renderApiKeyPair(p.key, p.base)).join('')}
      </div>
      <p style="font-size:0.8rem;color:var(--text-muted);margin-top:8px;">OpenAI 和 Anthropic 至少填写一个。Base URL 留空则使用官方默认地址，也可填入中转站 / 代理地址。</p>
    </div>

    <div class="api-group" style="margin-top:24px;">
      <h3 style="font-size:0.95rem;color:var(--accent-primary);margin-bottom:16px;display:flex;align-items:center;gap:8px;">
        <span>🔊</span> 语音 (TTS / ASR)
      </h3>
      <div class="input-group">
        ${voicePairs.map(p => renderApiKeyPair(p.key, p.base)).join('')}
      </div>
    </div>

    <div class="api-group" style="margin-top:24px;">
      <h3 style="font-size:0.95rem;color:var(--accent-primary);margin-bottom:16px;display:flex;align-items:center;gap:8px;">
        <span>🎭</span> 2D 动作生成
      </h3>
      <div class="input-group">
        ${actionPairs.map(p => renderApiKeyPair(p.key, p.base)).join('')}
      </div>
    </div>
  `;

  // Attach visibility toggles
  container.querySelectorAll('.toggle-visibility').forEach(btn => {
    btn.addEventListener('click', () => togglePasswordVisibility(btn));
  });

  // Attach input listeners
  container.querySelectorAll('.form-input').forEach(input => {
    input.addEventListener('input', (e) => {
      currentConfig[e.target.dataset.key] = e.target.value;
      clearError(e.target);
    });
  });
}

function renderApiKeyPair(key, baseKey) {
  const keySchema = CONFIG_SCHEMA[key];
  const baseSchema = CONFIG_SCHEMA[baseKey];
  const keyValue = currentConfig[key] || '';
  const baseValue = currentConfig[baseKey] || '';
  const requiredNote = keySchema.required ? '<span class="required">*</span>' : '<span class="optional">可选</span>';
  return `
    <div class="form-group api-key-pair">
      <label class="form-label">${keySchema.label}${requiredNote}</label>
      <div class="form-input-wrap">
        <input type="password" class="form-input" data-key="${key}" value="${escapeHtml(keyValue)}" placeholder="请输入 ${keySchema.label}">
        <button type="button" class="toggle-visibility" title="显示/隐藏">👁️</button>
      </div>
      <label class="form-label" style="margin-top:8px;font-size:0.8rem;color:var(--text-muted);">服务商地址 (Base URL)</label>
      <input type="text" class="form-input" data-key="${baseKey}" value="${escapeHtml(baseValue)}" placeholder="${baseSchema.placeholder || '留空使用默认地址'}">
    </div>
  `;
}

function renderPasswordField(key) {
  const schema = CONFIG_SCHEMA[key];
  const value = currentConfig[key] || '';
  const requiredNote = schema.required ? '<span class="required">*</span>' : '<span class="optional">可选</span>';
  return `
    <div class="form-group">
      <label class="form-label">${schema.label}${requiredNote}</label>
      <div class="form-input-wrap">
        <input type="password" class="form-input" data-key="${key}" value="${escapeHtml(value)}" placeholder="请输入 ${schema.label}">
        <button type="button" class="toggle-visibility" title="显示/隐藏">👁️</button>
      </div>
    </div>
  `;
}

function renderModelSection() {
  const container = document.getElementById('model-content');
  if (!container) return;

  const modelKeys = ['default_llm_model', 'reasoning_llm_model', 'tts_provider'];
  const textKeys = ['default_voice_id'];

  container.innerHTML = `
    <div class="input-group">
      ${modelKeys.map(key => renderSelectField(key)).join('')}
    </div>
    <div class="input-group" style="margin-top:16px;">
      ${textKeys.map(key => renderTextField(key)).join('')}
    </div>
  `;

  container.querySelectorAll('.form-select').forEach(select => {
    select.addEventListener('change', (e) => {
      currentConfig[e.target.dataset.key] = e.target.value;
    });
  });

  container.querySelectorAll('.form-input').forEach(input => {
    input.addEventListener('input', (e) => {
      currentConfig[e.target.dataset.key] = e.target.value;
    });
  });
}

function renderSelectField(key) {
  const schema = CONFIG_SCHEMA[key];
  const value = currentConfig[key] || schema.default;
  return `
    <div class="form-group">
      <label class="form-label">${schema.label}</label>
      <select class="form-select" data-key="${key}">
        ${schema.options.map(opt => `<option value="${opt}" ${opt === value ? 'selected' : ''}>${opt}</option>`).join('')}
      </select>
    </div>
  `;
}

function renderTextField(key) {
  const schema = CONFIG_SCHEMA[key];
  const value = currentConfig[key] || schema.default || '';
  return `
    <div class="form-group">
      <label class="form-label">${schema.label}</label>
      <input type="text" class="form-input" data-key="${key}" value="${escapeHtml(value)}" placeholder="请输入 ${schema.label}">
    </div>
  `;
}

function renderFeatureSection() {
  const container = document.getElementById('feature-content');
  if (!container) return;

  const toggleKeys = [
    'lite_mode',
    'enable_voice',
    'enable_action_2d',
    'enable_knowledge_graph',
    'enable_device_coordination',
    'enable_memory_pipeline',
  ];

  container.innerHTML = toggleKeys.map(key => renderToggleField(key)).join('');

  container.querySelectorAll('.toggle-switch input').forEach(input => {
    input.addEventListener('change', (e) => {
      currentConfig[e.target.dataset.key] = e.target.checked;
      if (e.target.dataset.key === 'lite_mode') {
        updateLiteModeUI();
      }
    });
  });
}

function renderToggleField(key) {
  const schema = CONFIG_SCHEMA[key];
  const checked = currentConfig[key] ? 'checked' : '';
  const isLite = key === 'lite_mode';
  const highlightStyle = isLite ? 'background:rgba(79,195,247,0.05);border-radius:var(--radius-sm);padding:8px 12px;' : '';
  return `
    <div class="toggle-row" style="${highlightStyle}">
      <div class="toggle-info">
        <span class="toggle-label">${schema.label} ${isLite ? '<span style="color:var(--accent-primary);font-size:0.75rem;">(核心)</span>' : ''}</span>
        <span class="toggle-desc">${schema.desc}</span>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" data-key="${key}" ${checked}>
        <span class="toggle-slider"></span>
      </label>
    </div>
  `;
}

function renderCommandSection() {
  const container = document.getElementById('command-content');
  if (!container) return;

  const batCmd = generateBatCommand();
  const psCmd = generatePsCommand();

  container.innerHTML = `
    <div class="form-group">
      <label class="form-label">Windows CMD (run_local.bat)</label>
      <div class="command-block">
        <code>${escapeHtml(batCmd)}</code>
        <button class="btn btn-secondary copy-btn" data-cmd="bat">复制</button>
      </div>
    </div>
    <div class="form-group" style="margin-top:20px;">
      <label class="form-label">PowerShell (run_local.ps1)</label>
      <div class="command-block">
        <code>${escapeHtml(psCmd)}</code>
        <button class="btn btn-secondary copy-btn" data-cmd="ps">复制</button>
      </div>
    </div>
  `;

  container.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const cmd = btn.dataset.cmd === 'bat' ? batCmd : psCmd;
      copyToClipboard(cmd);
      showToast('启动命令已复制到剪贴板', 'success');
    });
  });
}

// ============================================================
// Lite Mode UI Toggle
// ============================================================
function updateLiteModeUI() {
  const isLite = currentConfig.lite_mode;
  const serverSection = document.getElementById('section-server');
  const banner = document.getElementById('lite-banner');

  if (serverSection) {
    if (isLite) {
      serverSection.classList.add('section-hidden');
    } else {
      serverSection.classList.remove('section-hidden');
    }
  }

  if (banner) {
    banner.style.display = isLite ? 'flex' : 'none';
  }
}

// ============================================================
// Navigation
// ============================================================
function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const section = item.dataset.section;
      switchSection(section);

      // Close mobile menu
      document.querySelector('.sidebar').classList.remove('open');
      document.querySelector('.sidebar-overlay').classList.remove('active');
    });
  });
}

function switchSection(section) {
  activeSection = section;

  // Update nav
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.section === section);
  });

  // Update content
  document.querySelectorAll('.content-section').forEach(sec => {
    sec.style.display = sec.id === `section-${section}` ? 'block' : 'none';
  });

  // Update page title
  const titles = {
    'api-keys': 'API Key 配置',
    'models': '模型选择',
    'features': '功能开关',
    'test': '连接测试',
    'export': '保存 / 导出',
  };
  const titleEl = document.getElementById('page-title');
  const descEl = document.getElementById('page-desc');
  if (titleEl) titleEl.textContent = titles[section] || '配置';
  if (descEl) {
    const descs = {
      'api-keys': '配置各服务的 API Key，至少填写一个 LLM 提供商的 Key',
      'models': '选择默认对话模型、推理模型和语音合成提供商',
      'features': '启用或禁用 Companion AI 的各项功能模块',
      'test': '测试 LLM API 和后端服务的连通性',
      'export': '保存配置到浏览器、导出 .env 文件或生成启动命令',
    };
    descEl.textContent = descs[section] || '';
  }
}

function setupMobileMenu() {
  const toggle = document.getElementById('mobile-toggle');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');

  if (toggle) {
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('active');
    });
  }

  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('active');
    });
  }
}

// ============================================================
// Form Listeners
// ============================================================
function setupFormListeners() {
  // Re-render command section when config changes
  const observer = new MutationObserver(() => {
    renderCommandSection();
  });

  // Observe all input changes via a delegated approach
  document.addEventListener('input', () => {
    // Debounced re-render of command section
    clearTimeout(window._cmdRenderTimeout);
    window._cmdRenderTimeout = setTimeout(() => renderCommandSection(), 300);
  });
}

// ============================================================
// Test Buttons
// ============================================================
function setupTestButtons() {
  const llmBtn = document.getElementById('test-llm-btn');
  const backendBtn = document.getElementById('test-backend-btn');

  if (llmBtn) {
    llmBtn.addEventListener('click', testLLMConnection);
  }
  if (backendBtn) {
    backendBtn.addEventListener('click', testBackendServices);
  }
}

async function testLLMConnection() {
  const resultsContainer = document.getElementById('llm-test-results');
  if (!resultsContainer) return;

  resultsContainer.innerHTML = '';

  const openaiKey = currentConfig.openai_api_key;
  const anthropicKey = currentConfig.anthropic_api_key;

  if (!openaiKey && !anthropicKey) {
    showToast('请至少配置一个 LLM API Key', 'error');
    return;
  }

  const tests = [];
  if (openaiKey) {
    tests.push({ name: 'OpenAI API', type: 'openai', key: openaiKey });
  }
  if (anthropicKey) {
    tests.push({ name: 'Anthropic API', type: 'anthropic', key: anthropicKey });
  }

  for (const test of tests) {
    const item = createTestItem(test.name, '测试中...');
    resultsContainer.appendChild(item);

    try {
      if (test.type === 'openai') {
        await testOpenAI(test.key);
        updateTestItem(item, true, '连接成功 — API Key 有效');
      } else {
        await testAnthropic(test.key);
        updateTestItem(item, true, '连接成功 — API Key 有效');
      }
    } catch (err) {
      updateTestItem(item, false, `连接失败 — ${err.message}`);
    }
  }
}

async function testOpenAI(apiKey) {
  const baseUrl = (currentConfig.openai_base_url || 'https://api.openai.com/v1').replace(/\/$/, '');
  const resp = await fetch(`${baseUrl}/models`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
    },
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error?.message || `HTTP ${resp.status}`);
  }
}

async function testAnthropic(apiKey) {
  const baseUrl = (currentConfig.anthropic_base_url || 'https://api.anthropic.com/v1').replace(/\/$/, '');
  const resp = await fetch(`${baseUrl}/models`, {
    method: 'GET',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error?.message || `HTTP ${resp.status}`);
  }
}

async function testBackendServices() {
  const resultsContainer = document.getElementById('backend-test-results');
  if (!resultsContainer) return;

  resultsContainer.innerHTML = '';

  for (const svc of SERVICES) {
    const item = createTestItem(svc.label, '测试中...');
    resultsContainer.appendChild(item);

    try {
      const resp = await fetchWithTimeout(`http://127.0.0.1:${svc.port}/health`, { method: 'GET' }, 5000);
      if (resp.ok) {
        const data = await resp.json().catch(() => ({}));
        updateTestItem(item, true, `运行正常 — ${JSON.stringify(data).slice(0, 60)}`);
      } else {
        updateTestItem(item, false, `HTTP ${resp.status}`);
      }
    } catch (err) {
      updateTestItem(item, false, `无法连接 — ${err.message}`);
    }
  }
}

function createTestItem(name, status) {
  const div = document.createElement('div');
  div.className = 'test-item testing';
  div.innerHTML = `
    <span class="test-icon">⏳</span>
    <span class="test-name">${escapeHtml(name)}</span>
    <span class="test-status">${escapeHtml(status)}</span>
  `;
  return div;
}

function updateTestItem(el, success, status) {
  el.classList.remove('testing');
  el.classList.add(success ? 'success' : 'error');
  el.querySelector('.test-icon').textContent = success ? '✅' : '❌';
  el.querySelector('.test-status').textContent = status;
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...options, signal: controller.signal });
    return resp;
  } finally {
    clearTimeout(timeout);
  }
}

// ============================================================
// Action Buttons (Save / Export / Import)
// ============================================================
function setupActionButtons() {
  // Save to localStorage
  const saveBtn = document.getElementById('save-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      if (!validateRequired()) return;
      saveToStorage();
      showToast('配置已保存到浏览器本地存储', 'success');
    });
  }

  // Export .env
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (!validateRequired()) return;
      exportEnvFile();
    });
  }

  // Import .env
  const importInput = document.getElementById('import-file');
  if (importInput) {
    importInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) importEnvFile(file);
    });
  }
}

function validateRequired() {
  const openai = currentConfig.openai_api_key;
  const anthropic = currentConfig.anthropic_api_key;

  if (!openai && !anthropic) {
    showToast('请至少填写 OpenAI 或 Anthropic API Key', 'error');
    // Highlight the fields
    document.querySelectorAll('[data-key="openai_api_key"], [data-key="anthropic_api_key"]').forEach(el => {
      el.classList.add('error');
    });
    // Switch to API keys section
    switchSection('api-keys');
    return false;
  }

  return true;
}

function clearError(input) {
  input.classList.remove('error');
}

function saveToStorage() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(currentConfig));
}

function loadFromStorage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      currentConfig = { ...DEFAULT_CONFIG, ...parsed };
    }
  } catch (e) {
    console.warn('Failed to load config from localStorage:', e);
  }
}

function exportEnvFile() {
  const lines = [];
  lines.push('# Companion AI Configuration');
  lines.push('# Generated by Companion AI Web Configurator');
  lines.push('# ' + new Date().toLocaleString('zh-CN'));
  lines.push('');

  // Map config keys to env vars with COMPANION_ prefix
  const envMap = {
    openai_api_key: 'COMPANION_OPENAI_API_KEY',
    openai_base_url: 'COMPANION_OPENAI_BASE_URL',
    anthropic_api_key: 'COMPANION_ANTHROPIC_API_KEY',
    anthropic_base_url: 'COMPANION_ANTHROPIC_BASE_URL',
    tts_api_key: 'COMPANION_TTS_API_KEY',
    tts_base_url: 'COMPANION_TTS_BASE_URL',
    whisper_api_key: 'COMPANION_WHISPER_API_KEY',
    whisper_base_url: 'COMPANION_WHISPER_BASE_URL',
    action_api_key: 'COMPANION_ACTION_API_KEY',
    action_base_url: 'COMPANION_ACTION_BASE_URL',
    default_llm_model: 'COMPANION_DEFAULT_LLM_MODEL',
    reasoning_llm_model: 'COMPANION_REASONING_LLM_MODEL',
    tts_provider: 'COMPANION_TTS_PROVIDER',
    default_voice_id: 'COMPANION_DEFAULT_VOICE_ID',
    lite_mode: 'COMPANION_LITE_MODE',
    enable_voice: 'COMPANION_ENABLE_VOICE',
    enable_action_2d: 'COMPANION_ENABLE_ACTION_2D',
    enable_knowledge_graph: 'COMPANION_ENABLE_KNOWLEDGE_GRAPH',
    enable_device_coordination: 'COMPANION_ENABLE_DEVICE_COORDINATION',
    enable_memory_pipeline: 'COMPANION_ENABLE_MEMORY_PIPELINE',
  };

  for (const [configKey, envKey] of Object.entries(envMap)) {
    const value = currentConfig[configKey];
    if (value !== undefined && value !== '') {
      if (typeof value === 'boolean') {
        lines.push(`${envKey}=${value ? 'true' : 'false'}`);
      } else {
        lines.push(`${envKey}=${value}`);
      }
    }
  }

  const content = lines.join('\n') + '\n';
  downloadFile(content, '.env', 'text/plain');
  showToast('.env 文件已导出', 'success');
}

function importEnvFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const text = e.target.result;
      const parsed = parseEnvFile(text);

      // Map env vars back to config keys
      const reverseMap = {
        'COMPANION_OPENAI_API_KEY': 'openai_api_key',
        'COMPANION_OPENAI_BASE_URL': 'openai_base_url',
        'COMPANION_ANTHROPIC_API_KEY': 'anthropic_api_key',
        'COMPANION_ANTHROPIC_BASE_URL': 'anthropic_base_url',
        'COMPANION_TTS_API_KEY': 'tts_api_key',
        'COMPANION_TTS_BASE_URL': 'tts_base_url',
        'COMPANION_WHISPER_API_KEY': 'whisper_api_key',
        'COMPANION_WHISPER_BASE_URL': 'whisper_base_url',
        'COMPANION_ACTION_API_KEY': 'action_api_key',
        'COMPANION_ACTION_BASE_URL': 'action_base_url',
        'COMPANION_DEFAULT_LLM_MODEL': 'default_llm_model',
        'COMPANION_REASONING_LLM_MODEL': 'reasoning_llm_model',
        'COMPANION_TTS_PROVIDER': 'tts_provider',
        'COMPANION_DEFAULT_VOICE_ID': 'default_voice_id',
        'COMPANION_LITE_MODE': 'lite_mode',
        'COMPANION_ENABLE_VOICE': 'enable_voice',
        'COMPANION_ENABLE_ACTION_2D': 'enable_action_2d',
        'COMPANION_ENABLE_KNOWLEDGE_GRAPH': 'enable_knowledge_graph',
        'COMPANION_ENABLE_DEVICE_COORDINATION': 'enable_device_coordination',
        'COMPANION_ENABLE_MEMORY_PIPELINE': 'enable_memory_pipeline',
      };

      for (const [envKey, configKey] of Object.entries(reverseMap)) {
        if (parsed[envKey] !== undefined) {
          let value = parsed[envKey];
          // Convert boolean strings
          if (value === 'true') value = true;
          else if (value === 'false') value = false;
          currentConfig[configKey] = value;
        }
      }

      renderAll();
      updateLiteModeUI();
      showToast('.env 文件导入成功', 'success');
    } catch (err) {
      showToast('导入失败: ' + err.message, 'error');
    }
  };
  reader.readAsText(file);
}

function parseEnvFile(text) {
  const result = {};
  const lines = text.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIndex = trimmed.indexOf('=');
    if (eqIndex > 0) {
      const key = trimmed.slice(0, eqIndex).trim();
      const value = trimmed.slice(eqIndex + 1).trim();
      // Remove surrounding quotes
      result[key] = value.replace(/^["']|["']$/g, '');
    }
  }
  return result;
}

// ============================================================
// Command Generation
// ============================================================
function generateBatCommand() {
  return `scripts\\run_local.bat`;
}

function generatePsCommand() {
  return `.\\scripts\\run_local.ps1`;
}

// ============================================================
// Utilities
// ============================================================
function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text);
  } else {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  toast.innerHTML = `<span>${icons[type] || icons.info}</span><span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('hiding');
    toast.addEventListener('animationend', () => toast.remove());
  }, 3000);
}

function togglePasswordVisibility(btn) {
  const input = btn.parentElement.querySelector('.form-input');
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁️';
  }
}

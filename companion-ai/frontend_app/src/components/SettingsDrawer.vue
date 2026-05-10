<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="visible" class="drawer-overlay" @click="$emit('close')"></div>
    </transition>
    <transition name="slide">
      <div v-if="visible" class="settings-drawer">
        <div class="drawer-header">
          <h3>设置</h3>
          <button class="close-btn" @click="$emit('close')">✕</button>
        </div>

        <div class="drawer-body">

          <!-- 用户昵称 -->
          <div class="setting-item">
            <label>用户昵称</label>
            <input
              v-model="localUserName"
              type="text"
              placeholder="输入你的昵称"
              @blur="updateName"
              @keydown.enter="updateName"
            />
          </div>

          <!-- 连接状态 -->
          <div class="setting-item">
            <label>后端状态</label>
            <div class="api-status">
              <span class="status-dot" :class="serverAvailable === true ? 'online' : serverAvailable === false ? 'offline' : 'unknown'"></span>
              <span>{{ serverStatusText }}</span>
            </div>
          </div>

          <!-- LLM 配置 -->
          <div class="setting-section">
            <div class="section-title">LLM 配置</div>

            <div class="setting-item">
              <label>Provider</label>
              <select v-model="llm.provider" class="select-input">
                <option value="">-- 选择服务商 --</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai_compatible">OpenAI 兼容接口（Kimi / DeepSeek 等）</option>
              </select>
            </div>

            <div class="setting-item">
              <label>API Key</label>
              <div class="key-input-row">
                <input
                  v-model="llm.api_key"
                  :type="showKey ? 'text' : 'password'"
                  placeholder="sk-..."
                  autocomplete="off"
                  spellcheck="false"
                />
                <button class="eye-btn" @click="showKey = !showKey" :title="showKey ? '隐藏' : '显示'">
                  {{ showKey ? '🙈' : '👁️' }}
                </button>
              </div>
            </div>

            <div class="setting-item">
              <label>Base URL <span class="optional">（留空使用默认）</span></label>
              <input
                v-model="llm.base_url"
                type="text"
                :placeholder="baseUrlPlaceholder"
              />
            </div>

            <div class="setting-item">
              <label>模型 <span class="optional" v-if="llm.provider !== 'openai_compatible'">（留空使用默认）</span><span class="required-mark" v-else>*必填</span></label>
              <input
                v-model="llm.model"
                type="text"
                :placeholder="modelPlaceholder"
                :class="{ 'input-error': llm.provider === 'openai_compatible' && !llm.model }"
              />
              <div v-if="llm.provider === 'openai_compatible'" class="model-hint">
                DashScope: <code>qwen-turbo</code> / <code>qwen-plus</code> / <code>qwen-max</code><br>
                DeepSeek: <code>deepseek-chat</code> &nbsp; Kimi: <code>moonshot-v1-8k</code>
              </div>
            </div>

            <div class="llm-actions">
              <button class="save-btn" @click="saveLlm" :disabled="saving">
                {{ saving ? '保存中...' : '保存并生效' }}
              </button>
              <button class="clear-llm-btn" @click="clearLlm" title="清除 LLM 配置，恢复规则回复">清除</button>
            </div>

            <div class="llm-actions test-row">
              <button
                class="test-btn"
                @click="testLlm"
                :disabled="testingLlm || (!llm.api_key_set && !llm.api_key)"
                title="向当前配置的 LLM 发送一个最小请求，测量延迟和返回内容"
              >
                <span v-if="testingLlm">⏳ 测试中... (最长 30s)</span>
                <span v-else>🧪 测试连接</span>
              </button>
            </div>

            <div v-if="llmTestResult" class="test-result" :class="llmTestResult.ok ? 'ok' : 'err'">
              <div class="test-result-header">
                <span class="test-status">
                  {{ llmTestResult.ok ? '✅ 连接成功' : '❌ 连接失败' }}
                </span>
                <span v-if="llmTestResult.ok" class="test-latency">
                  延迟 {{ llmTestResult.latency_ms }} ms
                  <span class="latency-tag" :class="latencyTag(llmTestResult.latency_ms)">
                    {{ latencyHint(llmTestResult.latency_ms) }}
                  </span>
                </span>
              </div>
              <div v-if="llmTestResult.ok && llmTestResult.sample_reply" class="test-sample">
                <span class="test-label">回复预览:</span>
                <span class="test-text">{{ llmTestResult.sample_reply }}</span>
              </div>
              <div v-if="!llmTestResult.ok && llmTestResult.error" class="test-error">
                <div class="test-label">错误:</div>
                <div class="test-error-msg">{{ llmTestResult.error }}</div>
                <div class="test-tips">
                  <strong>常见排查:</strong>
                  <ul>
                    <li>检查 API Key 是否正确（注意首尾空格）</li>
                    <li>Base URL 是否填错协议或路径（如 DashScope 兼容接口需 <code>https://dashscope.aliyuncs.com/compatible-mode/v1</code>）</li>
                    <li>模型名称是否拼对（如 <code>qwen-turbo</code>、<code>deepseek-chat</code>）</li>
                    <li>是否被防火墙/代理拦截，或需要梯子</li>
                  </ul>
                </div>
              </div>
            </div>

            <div v-if="llmMsg" class="llm-msg" :class="llmMsgType">{{ llmMsg }}</div>

            <div class="llm-hint">
              <div class="hint-row">
                <span class="hint-dot" :class="llm.api_key_set ? 'active' : 'inactive'"></span>
                {{ llm.api_key_set ? '已配置 API Key，使用真实 LLM 回复' : '未配置 API Key，使用规则回复' }}
              </div>
            </div>
          </div>

          <!-- 语音配置 -->
          <div class="setting-section voice-section">
            <div class="section-title">🎙️ 语音配置</div>

            <!-- ASR 子区块 -->
            <div class="sub-section">
              <div class="sub-title">语音识别 (ASR)</div>

              <div class="setting-item">
                <label>预设</label>
                <select v-model="asrPreset" class="select-input" @change="applyAsrPreset">
                  <option value="">-- 自定义 --</option>
                  <option value="dashscope">阿里云 DashScope Paraformer（国内 推荐）</option>
                  <option value="siliconflow">硅基流动 SiliconFlow（国内）</option>
                  <option value="groq">Groq（海外 免费 速度快）</option>
                  <option value="openai">OpenAI 官方</option>
                </select>
              </div>

              <div class="setting-item">
                <label>API Key</label>
                <div class="key-input-row">
                  <input
                    v-model="voice.asr_api_key"
                    :type="showAsrKey ? 'text' : 'password'"
                    placeholder="sk-..."
                    autocomplete="off"
                    spellcheck="false"
                  />
                  <button class="eye-btn" @click="showAsrKey = !showAsrKey" :title="showAsrKey ? '隐藏' : '显示'">
                    {{ showAsrKey ? '🙈' : '👁️' }}
                  </button>
                </div>
                <div v-if="voice.asr_api_key_set && !voice.asr_api_key" class="model-hint">
                  已设置（留空表示保留现有值）
                </div>
              </div>

              <div class="setting-item">
                <label>Base URL</label>
                <input
                  v-model="voice.asr_base_url"
                  type="text"
                  :placeholder="asrBaseUrlPlaceholder"
                />
              </div>

              <div class="setting-item">
                <label>模型 <span class="optional">（留空使用预设默认）</span></label>
                <input
                  v-model="voice.asr_model"
                  type="text"
                  :placeholder="asrModelPlaceholder"
                />
                <div class="model-hint">
                  阿里云: <code>paraformer-realtime-v2</code><br>
                  硅基流动: <code>FunAudioLLM/SenseVoiceSmall</code><br>
                  Groq: <code>whisper-large-v3</code> &nbsp; OpenAI: <code>whisper-1</code>
                </div>
              </div>
            </div>

            <!-- TTS 子区块 -->
            <div class="sub-section">
              <div class="sub-title">语音合成 (TTS)</div>

              <div class="setting-item">
                <label>Provider</label>
                <select v-model="voice.tts_provider" class="select-input" @change="applyTtsPreset">
                  <option value="">-- 不启用 TTS --</option>
                  <option value="xiaomi_mimo">小米 MiMo TTS v2.5（国内）</option>
                  <option value="dashscope">阿里云 DashScope CosyVoice（国内 推荐）</option>
                  <option value="siliconflow">硅基流动 SiliconFlow（国内）</option>
                  <option value="openai">OpenAI 官方</option>
                  <option value="fish_audio">Fish Audio</option>
                  <option value="chattts">ChatTTS</option>
                </select>
              </div>

              <div class="setting-item" v-if="voice.tts_provider">
                <label>API Key</label>
                <div class="key-input-row">
                  <input
                    v-model="voice.tts_api_key"
                    :type="showTtsKey ? 'text' : 'password'"
                    placeholder="sk-..."
                    autocomplete="off"
                    spellcheck="false"
                  />
                  <button class="eye-btn" @click="showTtsKey = !showTtsKey" :title="showTtsKey ? '隐藏' : '显示'">
                    {{ showTtsKey ? '🙈' : '👁️' }}
                  </button>
                </div>
              </div>

              <div class="setting-item" v-if="voice.tts_provider">
                <label>Base URL <span class="optional">（留空使用 Provider 默认）</span></label>
                <input
                  v-model="voice.tts_base_url"
                  type="text"
                  :placeholder="ttsBaseUrlPlaceholder"
                />
              </div>

              <div class="setting-item" v-if="voice.tts_provider">
                <label>模型 <span class="optional">（留空使用默认）</span></label>
                <input
                  v-model="voice.tts_model"
                  type="text"
                  :placeholder="ttsModelPlaceholder"
                />
              </div>

              <div class="setting-item" v-if="voice.tts_provider">
                <label>音色 / Voice ID</label>
                <input
                  v-model="voice.tts_voice_id"
                  type="text"
                  :placeholder="ttsVoicePlaceholder"
                />
                <div class="model-hint" v-if="voice.tts_provider === 'xiaomi_mimo'">
                  可选: <code>default_zh</code> / <code>mimo_default</code> / <code>default_en</code><br>
                  <code>Mia</code> / <code>Chloe</code> / <code>Milo</code> / <code>Dean</code>
                </div>
                <div class="model-hint" v-else-if="voice.tts_provider === 'dashscope'">
                  可选: <code>longxiaochun</code>(女) / <code>longxiaocheng</code>(男) / <code>longwan</code>(温柔) / <code>longyumi</code>(甜美)
                </div>
                <div class="model-hint" v-else-if="voice.tts_provider === 'siliconflow'">
                  示例: <code>FunAudioLLM/CosyVoice2-0.5B:alex</code> / <code>:anna</code>
                </div>
                <div class="model-hint" v-else-if="voice.tts_provider === 'openai'">
                  可选: <code>alloy</code> / <code>echo</code> / <code>nova</code> / <code>shimmer</code>
                </div>
              </div>
            </div>

            <div class="llm-actions">
              <button class="save-btn" @click="saveVoice" :disabled="savingVoice">
                {{ savingVoice ? '保存中...' : '保存语音配置' }}
              </button>
              <button class="clear-llm-btn" @click="clearVoice" title="清除语音配置">清除</button>
            </div>

            <div class="llm-actions test-row">
              <button
                class="test-btn"
                @click="testVoice"
                :disabled="testingVoice || (!voice.asr_api_key_set && !voice.tts_api_key_set)"
                title="检查 ASR 配置 + 调用 TTS 合成一段语音并播放"
              >
                <span v-if="testingVoice">⏳ 测试中... (TTS 需 1~3 秒)</span>
                <span v-else>🧪 测试语音 (ASR 检测 + 播放 TTS)</span>
              </button>
            </div>

            <div v-if="voiceTestResult" class="test-result" :class="(voiceTestResult.asr_ok && voiceTestResult.tts_ok) ? 'ok' : 'err'">
              <div class="test-result-header">
                <span class="test-status">
                  ASR: {{ voiceTestResult.asr_ok ? '✅' : '❌' }}
                  &nbsp; TTS: {{ voiceTestResult.tts_ok ? '✅' : '❌' }}
                </span>
                <span v-if="voiceTestResult.tts_ok" class="test-latency">
                  TTS {{ voiceTestResult.tts_latency_ms }} ms
                  <span class="latency-tag" :class="latencyTag(voiceTestResult.tts_latency_ms)">
                    {{ latencyHint(voiceTestResult.tts_latency_ms) }}
                  </span>
                </span>
              </div>

              <div class="test-sample">
                <span class="test-label">ASR:</span>
                <span class="test-text">{{ voiceTestResult.asr_message }}</span>
              </div>

              <div v-if="voiceTestResult.tts_ok" class="test-sample">
                <span class="test-label">TTS 试听:</span>
                <audio ref="ttsAudioRef" controls preload="auto" class="tts-audio" />
              </div>

              <div v-if="!voiceTestResult.tts_ok && voiceTestResult.tts_error" class="test-error">
                <div class="test-label">TTS 错误:</div>
                <div class="test-error-msg">{{ voiceTestResult.tts_error }}</div>
                <div class="test-tips">
                  <strong>常见排查:</strong>
                  <ul>
                    <li v-if="voice.tts_provider === 'xiaomi_mimo'">Base URL 应为 <code>https://api.xiaomimimo.com/v1</code></li>
                    <li v-if="voice.tts_provider === 'xiaomi_mimo'">模型名: <code>mimo-v2.5-tts</code>；音色: <code>default_zh</code> / <code>mimo_default</code></li>
                    <li v-if="voice.tts_provider === 'xiaomi_mimo'">API Key 需在 <a href="https://platform.xiaomimimo.com" target="_blank">platform.xiaomimimo.com</a> 获取</li>
                    <li v-if="voice.tts_provider !== 'xiaomi_mimo'">DashScope TTS 的 Base URL 应为 <code>https://dashscope.aliyuncs.com/api/v1</code>（不是 compatible-mode）</li>
                    <li v-if="voice.tts_provider !== 'xiaomi_mimo'">模型名建议: <code>cosyvoice-v3-flash</code> / <code>cosyvoice-v2</code> / <code>cosyvoice-v1</code></li>
                    <li v-if="voice.tts_provider !== 'xiaomi_mimo'">音色 ID 应为 <code>longxiaochun</code> / <code>longwan</code> / <code>longyumi</code> 等</li>
                    <li>API Key 是否开通了语音合成模型权限</li>
                  </ul>
                </div>
              </div>
            </div>

            <div v-if="voiceMsg" class="llm-msg" :class="voiceMsgType">{{ voiceMsg }}</div>

            <div class="llm-hint">
              <div class="hint-row">
                <span class="hint-dot" :class="voice.asr_api_key_set ? 'active' : 'inactive'"></span>
                ASR: {{ voice.asr_api_key_set ? '已配置' : '未配置' }}
              </div>
              <div class="hint-row">
                <span class="hint-dot" :class="voice.tts_api_key_set ? 'active' : 'inactive'"></span>
                TTS: {{ voice.tts_api_key_set ? `已配置 (${voice.tts_provider})` : '未配置' }}
              </div>
            </div>
          </div>

          <!-- Realtime Voice 调试信息 -->
          <div class="setting-section debug-section">
            <div class="section-title">🔍 Realtime Voice 调试</div>

            <div class="setting-item">
              <label>Realtime Provider</label>
              <div class="debug-value">
                <code>{{ realtimeProvider || '（未协商）' }}</code>
              </div>
            </div>

            <div class="setting-item">
              <label>Audio Format</label>
              <div class="debug-value">
                <code>{{ audioFormat || 'pcm' }}</code>
              </div>
            </div>

            <div class="setting-item">
              <label>Sample Rate</label>
              <div class="debug-value">
                <code v-if="sampleRate > 0">{{ sampleRate }} Hz</code>
                <code v-else>（未协商）</code>
              </div>
            </div>

            <div class="debug-hint">
              这些值由 <code>assistant_sentence_start</code> / <code>tts_start</code> 事件协商得出。若播放无声，请对比服务端实际格式。
            </div>
          </div>

          <!-- 会话 ID -->
          <div class="setting-item">
            <label>会话 ID</label>
            <div class="session-id-display">
              <code>{{ sessionId }}</code>
              <button class="copy-btn" @click="copySessionId" title="复制">📋</button>
            </div>
          </div>

          <!-- 危险操作 -->
          <div class="setting-item danger-zone">
            <label>危险操作</label>
            <button class="danger-btn" @click="confirmClear">🗑️ 清空对话记录</button>
          </div>

        </div>

        <div class="drawer-footer">
          <span class="version">Companion AI v1.0</span>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useApi } from '../composables/useApi';
import { currentAudioFormat, currentRealtimeProvider, currentSampleRate } from '../composables/useRealtimeVoice';

const props = defineProps<{
  visible: boolean;
  userName: string;
  sessionId: string;
  serverAvailable: boolean | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'update:userName', name: string): void;
  (e: 'clear'): void;
}>();

const { getLlmConfig, saveLlmConfig, testLlmConfig, getVoiceConfig, saveVoiceConfig, testVoiceConfig } = useApi();

const audioFormat = computed(() => currentAudioFormat.value);
const realtimeProvider = computed(() => currentRealtimeProvider.value);
const sampleRate = computed(() => currentSampleRate.value);

// ── user name ──
const localUserName = ref(props.userName);
watch(() => props.userName, (v) => { localUserName.value = v; });

function updateName() {
  const name = localUserName.value.trim();
  if (name) emit('update:userName', name);
}

const serverStatusText = computed(() => {
  if (props.serverAvailable === true) return '已连接';
  if (props.serverAvailable === false) return '未连接';
  return '检测中...';
});

// ── LLM config ──
const llm = reactive({ provider: '', api_key: '', base_url: '', model: '', api_key_set: false });
const showKey = ref(false);
const saving = ref(false);
const llmMsg = ref('');
const llmMsgType = ref<'ok' | 'err'>('ok');
const testingLlm = ref(false);
const llmTestResult = ref<null | {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  sample_reply: string;
  error: string;
}>(null);

const baseUrlPlaceholder = computed(() => {
  if (llm.provider === 'openai') return 'https://api.openai.com/v1';
  if (llm.provider === 'anthropic') return 'https://api.anthropic.com/v1';
  if (llm.provider === 'openai_compatible') return 'https://api.moonshot.cn/v1';
  return '';
});

const modelPlaceholder = computed(() => {
  if (llm.provider === 'openai') return 'gpt-4o-mini';
  if (llm.provider === 'anthropic') return 'claude-haiku-4-5-20251001';
  if (llm.provider === 'openai_compatible') return 'moonshot-v1-8k';
  return '';
});

async function loadLlmConfig() {
  const cfg = await getLlmConfig();
  if (cfg) {
    llm.provider = cfg.provider;
    llm.base_url = cfg.base_url;
    llm.model = cfg.model;
    llm.api_key_set = cfg.api_key_set;
    llm.api_key = '';  // never pre-fill key
  }
}

watch(() => props.visible, (v) => {
  if (v) {
    localUserName.value = props.userName;
    loadLlmConfig();
    loadVoiceConfig();
    llmMsg.value = '';
    voiceMsg.value = '';
    llmTestResult.value = null;
    voiceTestResult.value = null;
  }
});

async function saveLlm() {
  if (!llm.provider) { llmMsg.value = '请先选择 Provider'; llmMsgType.value = 'err'; return; }
  if (!llm.api_key && !llm.api_key_set) { llmMsg.value = '请输入 API Key'; llmMsgType.value = 'err'; return; }
  if (llm.provider === 'openai_compatible' && !llm.model) { llmMsg.value = '兼容接口必须填写模型名称（如 qwen-turbo）'; llmMsgType.value = 'err'; return; }
  saving.value = true;
  llmMsg.value = '';
  const result = await saveLlmConfig({
    provider: llm.provider,
    api_key: llm.api_key,
    base_url: llm.base_url,
    model: llm.model,
  });
  saving.value = false;
  if (result.ok) {
    llmMsg.value = '已保存，下一条消息开始使用真实 LLM';
    llmMsgType.value = 'ok';
    const c = result.config;
    llm.api_key_set = c.api_key_set;
    llm.provider = c.provider;
    llm.base_url = c.base_url;
    llm.model = c.model;
    llm.api_key = '';
  } else {
    llmMsg.value = result.detail || '保存失败，请检查后端是否运行';
    llmMsgType.value = 'err';
  }
}

async function clearLlm() {
  const cleared = await saveLlmConfig({ provider: '', api_key: '', base_url: '', model: '' });
  if (!cleared.ok) {
    llmMsg.value = cleared.detail || '清除失败';
    llmMsgType.value = 'err';
    return;
  }
  llm.provider = '';
  llm.api_key = '';
  llm.base_url = '';
  llm.model = '';
  llm.api_key_set = false;
  llmMsg.value = '已清除，恢复规则回复';
  llmMsgType.value = 'ok';
  llmTestResult.value = null;
}

async function testLlm() {
  if (!llm.api_key_set && !llm.api_key) {
    llmMsg.value = '请先保存 API Key 后再测试';
    llmMsgType.value = 'err';
    return;
  }
  testingLlm.value = true;
  llmTestResult.value = null;
  const result = await testLlmConfig();
  testingLlm.value = false;
  if (result) {
    llmTestResult.value = result;
  } else {
    llmTestResult.value = {
      ok: false,
      provider: llm.provider,
      model: llm.model,
      latency_ms: 0,
      sample_reply: '',
      error: '请求失败，后端可能未运行',
    };
  }
}

function latencyTag(ms: number): 'fast' | 'mid' | 'slow' {
  if (ms < 1500) return 'fast';
  if (ms < 4000) return 'mid';
  return 'slow';
}

function latencyHint(ms: number): string {
  if (ms < 1500) return '很快';
  if (ms < 4000) return '一般';
  return '偏慢';
}

// ── voice config ──
const voice = reactive({
  asr_api_key: '',
  asr_base_url: '',
  asr_model: '',
  asr_api_key_set: false,
  tts_provider: '',
  tts_api_key: '',
  tts_base_url: '',
  tts_model: '',
  tts_voice_id: '',
  tts_api_key_set: false,
});
const showAsrKey = ref(false);
const showTtsKey = ref(false);
const savingVoice = ref(false);
const voiceMsg = ref('');
const voiceMsgType = ref<'ok' | 'err'>('ok');
const asrPreset = ref('');
const testingVoice = ref(false);
const voiceTestResult = ref<null | {
  asr_ok: boolean;
  asr_provider: string;
  asr_model: string;
  asr_message: string;
  tts_ok: boolean;
  tts_provider: string;
  tts_model: string;
  tts_voice: string;
  tts_latency_ms: number;
  tts_audio_url: string;
  tts_duration_ms: number;
  tts_error: string;
}>(null);
const ttsAudioRef = ref<HTMLAudioElement | null>(null);

const ASR_PRESETS: Record<string, { base_url: string; model: string }> = {
  dashscope: { base_url: 'https://dashscope.aliyuncs.com', model: 'paraformer-realtime-v2' },
  siliconflow: { base_url: 'https://api.siliconflow.cn/v1', model: 'FunAudioLLM/SenseVoiceSmall' },
  groq: { base_url: 'https://api.groq.com/openai/v1', model: 'whisper-large-v3' },
  openai: { base_url: 'https://api.openai.com/v1', model: 'whisper-1' },
};

const TTS_PRESETS: Record<string, { base_url: string; model: string; voice: string }> = {
  xiaomi_mimo: { base_url: 'https://api.xiaomimimo.com/v1', model: 'mimo-v2.5-tts', voice: 'default_zh' },
  dashscope: { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'cosyvoice-v1', voice: 'longxiaochun' },
  siliconflow: { base_url: 'https://api.siliconflow.cn/v1', model: 'FunAudioLLM/CosyVoice2-0.5B', voice: 'FunAudioLLM/CosyVoice2-0.5B:alex' },
  openai: { base_url: 'https://api.openai.com/v1', model: 'tts-1', voice: 'alloy' },
  fish_audio: { base_url: 'https://api.fish.audio/v1', model: '', voice: '' },
  chattts: { base_url: 'https://api.chattts.com/v1', model: '', voice: '' },
};

const asrBaseUrlPlaceholder = computed(() => {
  if (asrPreset.value && ASR_PRESETS[asrPreset.value]) return ASR_PRESETS[asrPreset.value].base_url;
  return 'https://api.siliconflow.cn/v1';
});
const asrModelPlaceholder = computed(() => {
  if (asrPreset.value && ASR_PRESETS[asrPreset.value]) return ASR_PRESETS[asrPreset.value].model;
  return 'FunAudioLLM/SenseVoiceSmall';
});
const ttsBaseUrlPlaceholder = computed(() => {
  if (voice.tts_provider && TTS_PRESETS[voice.tts_provider]) return TTS_PRESETS[voice.tts_provider].base_url;
  return '';
});
const ttsModelPlaceholder = computed(() => {
  if (voice.tts_provider && TTS_PRESETS[voice.tts_provider]) return TTS_PRESETS[voice.tts_provider].model;
  return '';
});
const ttsVoicePlaceholder = computed(() => {
  if (voice.tts_provider && TTS_PRESETS[voice.tts_provider]) return TTS_PRESETS[voice.tts_provider].voice;
  return '';
});

function applyAsrPreset() {
  if (!asrPreset.value) return;
  const p = ASR_PRESETS[asrPreset.value];
  if (p) {
    voice.asr_base_url = p.base_url;
    voice.asr_model = p.model;
  }
}

function applyTtsPreset() {
  if (!voice.tts_provider) return;
  const p = TTS_PRESETS[voice.tts_provider];
  if (p) {
    if (!voice.tts_base_url) voice.tts_base_url = p.base_url;
    if (!voice.tts_model) voice.tts_model = p.model;
    if (!voice.tts_voice_id) voice.tts_voice_id = p.voice;
  }
}

async function loadVoiceConfig() {
  const cfg = await getVoiceConfig();
  if (cfg) {
    voice.asr_base_url = cfg.asr_base_url || '';
    voice.asr_model = cfg.asr_model || '';
    voice.asr_api_key_set = cfg.asr_api_key_set;
    voice.asr_api_key = '';
    voice.tts_provider = cfg.tts_provider || '';
    voice.tts_base_url = cfg.tts_base_url || '';
    voice.tts_model = cfg.tts_model || '';
    voice.tts_voice_id = cfg.tts_voice_id || '';
    voice.tts_api_key_set = cfg.tts_api_key_set;
    voice.tts_api_key = '';
    // Infer preset from base_url
    asrPreset.value = '';
    for (const [name, p] of Object.entries(ASR_PRESETS)) {
      if (cfg.asr_base_url && cfg.asr_base_url.includes(new URL(p.base_url).hostname)) {
        asrPreset.value = name;
        break;
      }
    }
  }
}

async function saveVoice() {
  savingVoice.value = true;
  voiceMsg.value = '';
  const ok = await saveVoiceConfig({
    asr_api_key: voice.asr_api_key,
    asr_base_url: voice.asr_base_url,
    asr_model: voice.asr_model,
    tts_provider: voice.tts_provider,
    tts_api_key: voice.tts_api_key,
    tts_base_url: voice.tts_base_url,
    tts_model: voice.tts_model,
    tts_voice_id: voice.tts_voice_id,
  });
  savingVoice.value = false;
  if (ok) {
    voiceMsg.value = '语音配置已保存并生效';
    voiceMsgType.value = 'ok';
    if (voice.asr_api_key) voice.asr_api_key_set = true;
    if (voice.tts_api_key) voice.tts_api_key_set = true;
    voice.asr_api_key = '';
    voice.tts_api_key = '';
  } else {
    voiceMsg.value = '保存失败，请检查后端';
    voiceMsgType.value = 'err';
  }
}

async function clearVoice() {
  await saveVoiceConfig({
    asr_api_key: '', asr_base_url: '', asr_model: '',
    tts_provider: '', tts_api_key: '', tts_base_url: '',
    tts_model: '', tts_voice_id: '',
  });
  voice.asr_api_key = '';
  voice.asr_base_url = '';
  voice.asr_model = '';
  voice.asr_api_key_set = false;
  voice.tts_provider = '';
  voice.tts_api_key = '';
  voice.tts_base_url = '';
  voice.tts_model = '';
  voice.tts_voice_id = '';
  voice.tts_api_key_set = false;
  asrPreset.value = '';
  voiceMsg.value = '语音配置已清除';
  voiceMsgType.value = 'ok';
  voiceTestResult.value = null;
}

async function testVoice() {
  testingVoice.value = true;
  voiceTestResult.value = null;
  const result = await testVoiceConfig();
  testingVoice.value = false;
  if (result) {
    voiceTestResult.value = result;
    if (result.tts_ok && result.tts_audio_url) {
      // auto-play the synthesized sample
      setTimeout(() => {
        const el = ttsAudioRef.value;
        if (el) {
          el.src = absoluteAudioUrl(result.tts_audio_url);
          el.play().catch(() => {/* user interaction needed */});
        }
      }, 100);
    }
  } else {
    voiceTestResult.value = {
      asr_ok: false, asr_provider: '', asr_model: '', asr_message: '请求失败',
      tts_ok: false, tts_provider: '', tts_model: '', tts_voice: '',
      tts_latency_ms: 0, tts_audio_url: '', tts_duration_ms: 0,
      tts_error: '请求失败，后端可能未运行',
    };
  }
}

function absoluteAudioUrl(url: string): string {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') || 'http://127.0.0.1:8000';
  return base + (url.startsWith('/') ? url : '/' + url);
}

// ── session ──
function copySessionId() {
  navigator.clipboard.writeText(props.sessionId).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = props.sessionId;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
}

function confirmClear() {
  if (confirm('确定要清空所有对话记录吗？此操作不可恢复。')) {
    emit('clear');
    emit('close');
  }
}
</script>

<style scoped>
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
}

.settings-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 360px;
  max-width: 92vw;
  height: 100vh;
  background: #0f0f1e;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  z-index: 101;
  display: flex;
  flex-direction: column;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.drawer-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #fff;
}

.close-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.05);
  color: #aaa;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.close-btn:hover { background: rgba(233, 69, 96, 0.2); color: #fff; }

.drawer-body {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
}

.setting-item {
  margin-bottom: 20px;
}

.setting-item label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 7px;
}

.optional {
  font-size: 10px;
  color: #475569;
  text-transform: none;
  font-weight: 400;
  letter-spacing: 0;
}

.required-mark {
  font-size: 10px;
  color: #f87171;
  text-transform: none;
  font-weight: 500;
  letter-spacing: 0;
}

.input-error { border-color: rgba(239, 68, 68, 0.5) !important; }

.model-hint {
  margin-top: 6px;
  font-size: 11px;
  color: #64748b;
  line-height: 1.7;
}
.model-hint code {
  background: rgba(255,255,255,0.06);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 11px;
  color: #94a3b8;
}

.setting-item input,
.select-input {
  width: 100%;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 15, 30, 0.7);
  color: #e2e8f0;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}
.setting-item input:focus,
.select-input:focus { border-color: rgba(233, 69, 96, 0.5); }
.select-input option { background: #1a1a2e; }

.key-input-row {
  display: flex;
  gap: 6px;
}
.key-input-row input { flex: 1; }

.eye-btn {
  width: 38px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  font-size: 14px;
  flex-shrink: 0;
}
.eye-btn:hover { background: rgba(255, 255, 255, 0.1); }

/* section */
.setting-section {
  margin-bottom: 24px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(233, 69, 96, 0.12);
  background: rgba(233, 69, 96, 0.03);
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #e94560;
  margin-bottom: 16px;
  letter-spacing: 0.3px;
}

/* voice section uses a different accent color */
.voice-section {
  border-color: rgba(139, 92, 246, 0.18);
  background: rgba(139, 92, 246, 0.04);
}
.voice-section .section-title {
  color: #a78bfa;
}

/* debug section uses a different accent */
.debug-section {
  border-color: rgba(74, 222, 128, 0.18);
  background: rgba(74, 222, 128, 0.04);
}
.debug-section .section-title {
  color: #4ade80;
}

.debug-value {
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(15, 15, 30, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.debug-value code {
  font-size: 13px;
  color: #94a3b8;
}

.debug-hint {
  margin-top: 10px;
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
}

.debug-hint code {
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 11px;
  color: #94a3b8;
}

.sub-section {
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.sub-title {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 10px;
  letter-spacing: 0.3px;
}

.llm-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 10px;
}

.save-btn {
  flex: 1;
  padding: 10px;
  border-radius: 10px;
  border: none;
  background: linear-gradient(135deg, #e94560, #c62a47);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.save-btn:not(:disabled):hover { opacity: 0.85; }

.clear-llm-btn {
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #94a3b8;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.clear-llm-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }

.llm-msg {
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 10px;
}
.llm-msg.ok { background: rgba(74, 222, 128, 0.1); color: #4ade80; }
.llm-msg.err { background: rgba(239, 68, 68, 0.1); color: #f87171; }

.llm-hint {
  font-size: 12px;
  color: #64748b;
}
.hint-row { display: flex; align-items: center; gap: 6px; }
.hint-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.hint-dot.active { background: #4ade80; box-shadow: 0 0 6px rgba(74,222,128,0.4); }
.hint-dot.inactive { background: #475569; }

/* api status */
.api-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #94a3b8;
}
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.online { background: #4ade80; box-shadow: 0 0 8px rgba(74,222,128,0.4); }
.status-dot.offline { background: #ef4444; }
.status-dot.unknown { background: #64748b; }

/* session id */
.session-id-display {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(15, 15, 30, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.session-id-display code {
  flex: 1;
  font-size: 11px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.copy-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: rgba(255, 255, 255, 0.05);
  cursor: pointer;
  font-size: 12px;
}
.copy-btn:hover { background: rgba(233, 69, 96, 0.2); }

/* danger */
.danger-zone { padding-top: 16px; border-top: 1px solid rgba(239, 68, 68, 0.15); }
.danger-btn {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.08);
  color: #f87171;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.danger-btn:hover { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.5); }

/* footer */
.drawer-footer {
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  text-align: center;
}
.version { font-size: 12px; color: #475569; }

/* transitions */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-enter-active, .slide-leave-active { transition: transform 0.3s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }

/* ===== LLM Test ===== */
.test-row {
  margin-top: 0;
  margin-bottom: 10px;
}

.test-btn {
  flex: 1;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(96, 165, 250, 0.35);
  background: rgba(96, 165, 250, 0.1);
  color: #93c5fd;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.test-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.test-btn:not(:disabled):hover {
  background: rgba(96, 165, 250, 0.18);
  color: #bfdbfe;
}

.test-result {
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.6;
}
.test-result.ok {
  background: rgba(74, 222, 128, 0.08);
  border: 1px solid rgba(74, 222, 128, 0.25);
}
.test-result.err {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.test-result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}
.test-status {
  font-weight: 600;
}
.test-result.ok .test-status { color: #4ade80; }
.test-result.err .test-status { color: #f87171; }

.test-latency {
  font-size: 11.5px;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.latency-tag {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 8px;
  font-size: 10.5px;
  font-weight: 600;
}
.latency-tag.fast { background: rgba(74, 222, 128, 0.18); color: #4ade80; }
.latency-tag.mid { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
.latency-tag.slow { background: rgba(239, 68, 68, 0.2); color: #f87171; }

.test-sample {
  margin-top: 6px;
  padding: 8px 10px;
  background: rgba(15, 15, 30, 0.5);
  border-radius: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.test-label {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
  flex-shrink: 0;
}
.test-text {
  flex: 1;
  color: #cbd5e1;
  word-break: break-word;
}

.test-error {
  margin-top: 6px;
}
.test-error-msg {
  padding: 8px 10px;
  background: rgba(15, 15, 30, 0.5);
  border-radius: 8px;
  color: #fca5a5;
  word-break: break-word;
  margin-bottom: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px;
}
.test-tips {
  font-size: 11.5px;
  color: #94a3b8;
}
.test-tips strong { color: #cbd5e1; }
.test-tips ul {
  margin: 4px 0 0;
  padding-left: 18px;
}
.test-tips li {
  margin-bottom: 3px;
  line-height: 1.55;
}
.tts-audio {
  flex: 1;
  height: 32px;
  min-width: 200px;
  border-radius: 8px;
}

.test-tips code {
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 11px;
  color: #cbd5e1;
}
</style>

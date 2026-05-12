<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="visible" class="call-overlay">
        <!-- 顶部状态栏（模拟手机状态条） -->
        <div class="status-bar">
          <span class="time-now">{{ clockText }}</span>
          <span class="signal">●●●● 5G</span>
        </div>

        <!-- 联系人区域 -->
        <div class="contact-area">
          <div class="contact-name">小暖</div>
          <div class="contact-status">{{ stateLabel }}</div>
          <div v-if="state === 'listening' || state === 'thinking' || state === 'speaking'" class="call-timer">
            {{ timerText }}
          </div>
        </div>

        <!-- 大头像 + 多层呼吸光环 -->
        <div class="avatar-wrap" :class="stateClass">
          <div class="halo halo-1"></div>
          <div class="halo halo-2"></div>
          <div class="halo halo-3"></div>
          <div class="avatar-core">
            <span class="avatar-emoji">{{ stateIcon }}</span>
          </div>
        </div>

        <!-- 实时字幕（小条幅，可关闭） -->
        <transition name="subtitle-fade">
          <div v-if="showSubtitles && latestSubtitle" class="subtitle-bar">
            <span class="subtitle-role">{{ latestSubtitle.role === 'user' ? '我' : '小暖' }}</span>
            <span class="subtitle-text">{{ latestSubtitle.text }}</span>
            <span v-if="latestSubtitle.streaming" class="subtitle-cursor">▌</span>
          </div>
        </transition>

        <!-- 错误条 -->
        <transition name="fade">
          <div v-if="errorMsg" class="error-bar">
            <span class="error-icon">⚠</span>
            <span>{{ errorMsg }}</span>
            <button class="error-hint-btn" v-if="needsConfig" @click="$emit('open-settings')">去配置</button>
          </div>
        </transition>

        <!-- 完整通话记录抽屉 -->
        <transition name="slide-up">
          <div v-if="showFullTranscript" class="transcript-sheet">
            <div class="sheet-header">
              <span>通话记录</span>
              <button class="sheet-close" @click="showFullTranscript = false">收起</button>
            </div>
            <div class="sheet-body" ref="transcriptRef">
              <div v-for="item in transcript" :key="item.id" class="bubble" :class="item.role">
                <span class="role-tag">{{ item.role === 'user' ? '我' : '小暖' }}</span>
                <span>{{ item.text }}</span>
              </div>
              <div v-if="partialAssistant" class="bubble assistant streaming">
                <span class="role-tag">小暖</span>
                <span>{{ partialAssistant }}</span>
                <span class="cursor">▌</span>
              </div>
              <div v-if="transcript.length === 0 && !partialAssistant" class="empty-tip">
                还没有对话内容
              </div>
            </div>
          </div>
        </transition>

        <!-- 底部按钮区（手机通话风格） -->
        <div class="action-bar">
          <!-- 次要按钮：字幕 -->
          <button class="circle-btn secondary" :class="{ active: showSubtitles }" @click="showSubtitles = !showSubtitles">
            <span class="ico">💬</span>
            <span class="lbl">字幕</span>
          </button>

          <!-- 主按钮：开始 / 挂断 -->
          <button
            v-if="state === 'idle' || state === 'error'"
            class="circle-btn primary call"
            @click="startCall"
            aria-label="开始通话"
          >
            <span class="ico-large">📞</span>
          </button>
          <button
            v-else
            class="circle-btn primary hangup"
            @click="hangUp"
            aria-label="挂断"
          >
            <span class="ico-large">✕</span>
          </button>

          <!-- 次要按钮：通话记录 -->
          <button class="circle-btn secondary" :class="{ active: showFullTranscript }" @click="showFullTranscript = !showFullTranscript">
            <span class="ico">📋</span>
            <span class="lbl">记录</span>
          </button>
        </div>

        <!-- 关闭整个面板（右上角小×） -->
        <button class="dismiss-btn" @click="dismiss" aria-label="关闭">⌄</button>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useRealtimeVoice } from '../composables/useRealtimeVoice';

const props = defineProps<{ visible: boolean }>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'open-settings'): void;
}>();

const { state, errorMsg, transcript, partialAssistant, startCall, stopCall } =
  useRealtimeVoice();

const transcriptRef = ref<HTMLElement | null>(null);
const showSubtitles = ref(true);
const showFullTranscript = ref(false);

// ── 通话计时器 ──
const callStartedAt = ref<number | null>(null);
const tickNow = ref(Date.now());
let tickHandle: number | null = null;

watch(state, (s, prev) => {
  const wasInactive = prev === 'idle' || prev === 'error' || prev === 'connecting';
  const isActive = s === 'listening' || s === 'thinking' || s === 'speaking';
  if (isActive && wasInactive && callStartedAt.value === null) {
    callStartedAt.value = Date.now();
  }
  if (s === 'idle' || s === 'error') {
    callStartedAt.value = null;
  }
});

if (typeof window !== 'undefined') {
  tickHandle = window.setInterval(() => {
    tickNow.value = Date.now();
  }, 1000);
}
onBeforeUnmount(() => {
  if (tickHandle !== null) {
    clearInterval(tickHandle);
    tickHandle = null;
  }
});

const timerText = computed(() => {
  if (callStartedAt.value === null) return '00:00';
  const sec = Math.max(0, Math.floor((tickNow.value - callStartedAt.value) / 1000));
  const m = Math.floor(sec / 60).toString().padStart(2, '0');
  const s = (sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
});

const clockText = computed(() => {
  const d = new Date(tickNow.value);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
});

// ── 状态文案 ──
const stateLabel = computed(() => {
  switch (state.value) {
    case 'idle': return '点击下方按钮开始通话';
    case 'connecting': return '正在连接...';
    case 'listening': return '我在听';
    case 'thinking': return '正在思考...';
    case 'speaking': return '正在说话';
    case 'error': return '通话异常';
    default: return '';
  }
});

const stateIcon = computed(() => {
  switch (state.value) {
    case 'listening': return '👂';
    case 'thinking': return '💭';
    case 'speaking': return '💬';
    case 'connecting': return '🔌';
    case 'error': return '⚠️';
    default: return '🌸';
  }
});

const stateClass = computed(() => `state-${state.value}`);

// ── 字幕：取最新一条 ──
const latestSubtitle = computed(() => {
  if (partialAssistant.value) {
    return { role: 'assistant' as const, text: partialAssistant.value, streaming: true };
  }
  if (transcript.value.length > 0) {
    const last = transcript.value[transcript.value.length - 1];
    return { role: last.role, text: last.text, streaming: false };
  }
  return null;
});

// ── 错误是否可能由配置导致 ──
const needsConfig = computed(() => {
  if (!errorMsg.value) return false;
  const m = errorMsg.value.toLowerCase();
  return (
    m.includes('asr') ||
    m.includes('tts') ||
    m.includes('api key') ||
    m.includes('apikey') ||
    m.includes('未配置') ||
    m.includes('not configured')
  );
});

watch([transcript, partialAssistant], () => {
  nextTick(() => {
    const el = transcriptRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}, { deep: true });

function hangUp() {
  void stopCall();
}

function dismiss() {
  void stopCall();
  emit('close');
}

watch(
  () => props.visible,
  (v) => {
    if (!v && state.value !== 'idle') {
      void stopCall();
    }
  }
);
</script>

<style scoped>
/* ===== 全屏「手机通话」背景 ===== */
.call-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background:
    radial-gradient(ellipse 120% 80% at 50% 0%, #2a1742 0%, #100620 45%, #050309 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #fff;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", system-ui, sans-serif;
  overflow: hidden;
  padding: env(safe-area-inset-top, 0) env(safe-area-inset-right, 0)
           env(safe-area-inset-bottom, 0) env(safe-area-inset-left, 0);
}

/* ===== 顶部状态条 ===== */
.status-bar {
  width: 100%;
  max-width: 480px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 28px 0;
  font-size: 13px;
  color: rgba(255,255,255,0.65);
  letter-spacing: 0.5px;
  font-variant-numeric: tabular-nums;
}
.signal { font-size: 11px; letter-spacing: 1px; }

/* ===== 收起按钮 ===== */
.dismiss-btn {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.4);
  font-size: 22px;
  cursor: pointer;
  width: 60px;
  height: 24px;
  line-height: 1;
  z-index: 5;
}
.dismiss-btn:hover { color: #fff; }

/* ===== 联系人 ===== */
.contact-area {
  margin-top: clamp(40px, 8vh, 70px);
  text-align: center;
}
.contact-name {
  font-size: clamp(28px, 4vh, 34px);
  font-weight: 500;
  letter-spacing: 1px;
  margin-bottom: 10px;
}
.contact-status {
  font-size: 14px;
  color: rgba(255,255,255,0.55);
  letter-spacing: 0.4px;
}
.call-timer {
  margin-top: 8px;
  font-size: 13px;
  color: rgba(255,255,255,0.45);
  font-variant-numeric: tabular-nums;
  letter-spacing: 1px;
}

/* ===== 头像 + 光环 ===== */
.avatar-wrap {
  position: relative;
  width: clamp(180px, 32vh, 240px);
  height: clamp(180px, 32vh, 240px);
  margin: clamp(36px, 6vh, 60px) 0 auto;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.halo {
  position: absolute;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(167, 139, 250, 0.28) 0%, transparent 70%);
}
.halo-1 { width: 100%; height: 100%; }
.halo-2 { width: 78%; height: 78%; opacity: 0.7; }
.halo-3 { width: 56%; height: 56%; opacity: 0.55; }

.avatar-core {
  width: 44%;
  height: 44%;
  border-radius: 50%;
  background:
    radial-gradient(circle at 30% 25%, #fff 0%, transparent 35%),
    linear-gradient(135deg, #e94560 0%, #8b5cf6 60%, #6366f1 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 16px 48px rgba(139, 92, 246, 0.55),
    inset 0 0 24px rgba(255,255,255,0.12);
  z-index: 2;
}
.avatar-emoji {
  font-size: clamp(38px, 6vh, 52px);
  filter: drop-shadow(0 2px 8px rgba(0,0,0,0.3));
}

/* 不同状态的光环动画 */
.state-listening .halo {
  animation: breath 2.6s ease-in-out infinite;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.38) 0%, transparent 70%);
}
.state-listening .halo-2 { animation-delay: 0.5s; }
.state-listening .halo-3 { animation-delay: 1s; }
.state-listening .avatar-core {
  background: radial-gradient(circle at 30% 25%, #fff 0%, transparent 35%),
              linear-gradient(135deg, #60a5fa, #3b82f6);
  box-shadow: 0 16px 48px rgba(96, 165, 250, 0.55);
}

.state-thinking .halo {
  animation: spin 6s linear infinite;
  background: conic-gradient(from 0deg, transparent 70%, rgba(251, 191, 36, 0.45));
}
.state-thinking .halo-2 { animation-direction: reverse; animation-duration: 4s; }
.state-thinking .avatar-core {
  background: radial-gradient(circle at 30% 25%, #fff 0%, transparent 35%),
              linear-gradient(135deg, #fbbf24, #f59e0b);
  box-shadow: 0 16px 48px rgba(251, 191, 36, 0.5);
}

.state-speaking .halo {
  animation: speakWave 1.4s ease-in-out infinite;
  background: radial-gradient(circle, rgba(167, 139, 250, 0.48) 0%, transparent 70%);
}
.state-speaking .halo-2 { animation-delay: 0.3s; }
.state-speaking .halo-3 { animation-delay: 0.6s; }

.state-connecting .halo {
  animation: breath 1.2s ease-in-out infinite;
  background: radial-gradient(circle, rgba(148, 163, 184, 0.3) 0%, transparent 70%);
}

.state-error .avatar-core {
  background: radial-gradient(circle at 30% 25%, #fff 0%, transparent 35%),
              linear-gradient(135deg, #ef4444, #b91c1c);
  box-shadow: 0 16px 48px rgba(239, 68, 68, 0.5);
}

@keyframes breath {
  0%, 100% { transform: scale(1); opacity: 0.55; }
  50% { transform: scale(1.12); opacity: 1; }
}
@keyframes speakWave {
  0%, 100% { transform: scale(0.95); opacity: 0.5; }
  50% { transform: scale(1.18); opacity: 1; }
}
@keyframes spin {
  from { transform: rotate(0); }
  to { transform: rotate(360deg); }
}

/* ===== 实时字幕条 ===== */
.subtitle-bar {
  position: relative;
  width: calc(100% - 40px);
  max-width: 460px;
  margin: 0 auto 16px;
  padding: 12px 18px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 14px;
  line-height: 1.55;
  color: #f1f5f9;
  display: flex;
  gap: 10px;
  max-height: 4.5em;
  overflow: hidden;
  flex-shrink: 0;
}
.subtitle-role {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: #a78bfa;
  padding-top: 3px;
  letter-spacing: 0.5px;
}
.subtitle-text {
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.subtitle-cursor {
  color: #a78bfa;
  animation: blink 0.8s ease-in-out infinite;
}
@keyframes blink {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}

/* ===== 错误条 ===== */
.error-bar {
  width: calc(100% - 40px);
  max-width: 460px;
  margin: 0 auto 14px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #fca5a5;
}
.error-icon { flex-shrink: 0; }
.error-hint-btn {
  margin-left: auto;
  padding: 4px 12px;
  border-radius: 8px;
  border: 1px solid rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.1);
  color: #fca5a5;
  font-size: 12px;
  cursor: pointer;
}
.error-hint-btn:hover { background: rgba(239, 68, 68, 0.2); }

/* ===== 通话记录抽屉 ===== */
.transcript-sheet {
  position: absolute;
  left: 50%;
  bottom: 200px;
  transform: translateX(-50%);
  width: calc(100% - 32px);
  max-width: 480px;
  max-height: 50vh;
  background: rgba(15, 15, 30, 0.92);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-radius: 18px;
  border: 1px solid rgba(255,255,255,0.08);
  display: flex;
  flex-direction: column;
  z-index: 4;
  box-shadow: 0 -10px 40px rgba(0,0,0,0.5);
}
.sheet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 14px;
  font-weight: 500;
}
.sheet-close {
  background: transparent;
  border: none;
  color: #a78bfa;
  font-size: 13px;
  cursor: pointer;
}
.sheet-body {
  padding: 14px 18px;
  overflow-y: auto;
  flex: 1;
}
.empty-tip {
  text-align: center;
  color: #64748b;
  font-size: 13px;
  padding: 20px;
}
.bubble {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.55;
}
.bubble.user {
  background: rgba(96, 165, 250, 0.12);
  border: 1px solid rgba(96, 165, 250, 0.18);
}
.bubble.assistant {
  background: rgba(167, 139, 250, 0.12);
  border: 1px solid rgba(167, 139, 250, 0.18);
}
.role-tag {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  padding-top: 2px;
}
.cursor { color: #a78bfa; animation: blink 0.8s infinite; }

/* ===== 底部按钮区 ===== */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-around;
  width: 100%;
  max-width: 480px;
  padding: 0 28px clamp(28px, 5vh, 48px);
  margin-top: auto;
  flex-shrink: 0;
}
.circle-btn {
  border: none;
  background: rgba(255,255,255,0.06);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid rgba(255,255,255,0.05);
}
.circle-btn:active { transform: scale(0.92); }

.circle-btn.secondary {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  font-size: 11px;
  color: rgba(255,255,255,0.7);
}
.circle-btn.secondary .ico { font-size: 22px; }
.circle-btn.secondary .lbl { font-size: 10px; letter-spacing: 0.4px; }
.circle-btn.secondary:hover { background: rgba(255,255,255,0.1); }
.circle-btn.secondary.active {
  background: rgba(167, 139, 250, 0.2);
  border-color: rgba(167, 139, 250, 0.4);
  color: #c4b5fd;
}

.circle-btn.primary {
  width: 78px;
  height: 78px;
  border-radius: 50%;
  border: none;
}
.circle-btn.primary.call {
  background: linear-gradient(135deg, #4ade80, #16a34a);
  box-shadow: 0 8px 30px rgba(34, 197, 94, 0.55);
}
.circle-btn.primary.call:hover { box-shadow: 0 8px 40px rgba(34, 197, 94, 0.75); }
.circle-btn.primary.hangup {
  background: linear-gradient(135deg, #ef4444, #b91c1c);
  box-shadow: 0 8px 30px rgba(239, 68, 68, 0.55);
  animation: hangup-pulse 2s ease-in-out infinite;
}
@keyframes hangup-pulse {
  0%, 100% { box-shadow: 0 8px 30px rgba(239, 68, 68, 0.55); }
  50% { box-shadow: 0 8px 44px rgba(239, 68, 68, 0.85); }
}
.circle-btn.primary .ico-large { font-size: 30px; }

/* ===== 过渡 ===== */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.subtitle-fade-enter-active, .subtitle-fade-leave-active { transition: all 0.25s ease; }
.subtitle-fade-enter-from, .subtitle-fade-leave-to { opacity: 0; transform: translateY(8px); }

.slide-up-enter-active, .slide-up-leave-active { transition: all 0.28s ease; }
.slide-up-enter-from, .slide-up-leave-to { opacity: 0; transform: translate(-50%, 20px); }

/* 适配低高度 */
@media (max-height: 700px) {
  .contact-area { margin-top: 24px; }
  .avatar-wrap {
    width: clamp(140px, 26vh, 180px);
    height: clamp(140px, 26vh, 180px);
    margin: 18px 0 auto;
  }
  .circle-btn.secondary { width: 56px; height: 56px; }
  .circle-btn.primary { width: 68px; height: 68px; }
}
</style>

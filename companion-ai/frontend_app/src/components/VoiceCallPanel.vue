<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="visible" class="call-overlay">
        <div class="call-panel">
          <button class="close-btn" @click="hangUp">✕</button>

          <!-- Avatar with state-driven animation -->
          <div class="avatar-wrap" :class="stateClass">
            <div class="avatar-ring ring-1"></div>
            <div class="avatar-ring ring-2"></div>
            <div class="avatar-ring ring-3"></div>
            <div class="avatar-core">
              <span class="avatar-icon">{{ stateIcon }}</span>
            </div>
          </div>

          <!-- State label -->
          <div class="state-label">{{ stateLabel }}</div>

          <!-- Transcript stream -->
          <div class="transcript-area" ref="transcriptRef">
            <div
              v-for="item in transcript"
              :key="item.id"
              class="bubble"
              :class="item.role"
            >
              <span class="role-tag">{{ item.role === 'user' ? '你' : '小暖' }}</span>
              <span class="text">{{ item.text }}</span>
            </div>
            <div v-if="partialAssistant" class="bubble assistant streaming">
              <span class="role-tag">小暖</span>
              <span class="text">{{ partialAssistant }}</span>
              <span class="cursor">▌</span>
            </div>
          </div>

          <!-- Error -->
          <div v-if="errorMsg" class="error-bar">{{ errorMsg }}</div>

          <!-- Bottom controls -->
          <div class="controls">
            <button
              v-if="state === 'idle' || state === 'error'"
              class="primary-btn call-btn"
              @click="startCall"
            >
              <span class="ico">📞</span>
              <span>开始通话</span>
            </button>
            <button
              v-else
              class="primary-btn hangup-btn"
              @click="hangUp"
            >
              <span class="ico">🔴</span>
              <span>挂断</span>
            </button>
          </div>

          <div class="hint">
            <span v-if="state === 'listening'">🎤 边说边听，说完会自动回答</span>
            <span v-else-if="state === 'thinking'">⚡ 正在思考...</span>
            <span v-else-if="state === 'speaking'">🔊 小暖正在说话（再说一句即可打断）</span>
            <span v-else-if="state === 'connecting'">🔌 连接中...</span>
            <span v-else>支持自然打断 · 全程本地推理</span>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRealtimeVoice } from '../composables/useRealtimeVoice';

const props = defineProps<{ visible: boolean }>();
const emit = defineEmits<{ (e: 'close'): void }>();

const { state, errorMsg, transcript, partialAssistant, startCall, stopCall } =
  useRealtimeVoice();

const transcriptRef = ref<HTMLElement | null>(null);

const stateLabel = computed(() => {
  switch (state.value) {
    case 'idle':
      return '准备就绪';
    case 'connecting':
      return '连接中';
    case 'listening':
      return '我在听...';
    case 'thinking':
      return '思考中';
    case 'speaking':
      return '正在回复';
    case 'error':
      return '出错了';
    default:
      return '';
  }
});

const stateIcon = computed(() => {
  switch (state.value) {
    case 'listening':
      return '👂';
    case 'thinking':
      return '💭';
    case 'speaking':
      return '💬';
    case 'connecting':
      return '🔌';
    case 'error':
      return '⚠️';
    default:
      return '🌸';
  }
});

const stateClass = computed(() => `state-${state.value}`);

watch([transcript, partialAssistant], () => {
  nextTick(() => {
    const el = transcriptRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}, { deep: true });

function hangUp() {
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
.call-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: radial-gradient(ellipse at center, #1a1530 0%, #08080f 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.call-panel {
  width: 100%;
  max-width: 540px;
  height: 100dvh;
  max-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: clamp(18px, 3vh, 28px) clamp(16px, 3vw, 24px) clamp(20px, 4vh, 32px);
  position: relative;
  color: #e2e8f0;
  overflow: hidden;
}

.close-btn {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.06);
  color: #cbd5e1;
  font-size: 14px;
  cursor: pointer;
  z-index: 10;
}
.close-btn:hover { background: rgba(233, 69, 96, 0.25); color: #fff; }

/* Avatar with reactive rings */
.avatar-wrap {
  position: relative;
  width: clamp(150px, 26vh, 220px);
  height: clamp(150px, 26vh, 220px);
  margin: clamp(18px, 4vh, 32px) 0 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-ring {
  position: absolute;
  border-radius: 50%;
  border: 2px solid rgba(233, 69, 96, 0.25);
}
.ring-1 { width: 100%; height: 100%; }
.ring-2 { width: 82%; height: 82%; }
.ring-3 { width: 64%; height: 64%; }

.avatar-core {
  width: 50%;
  height: 50%;
  border-radius: 50%;
  background: linear-gradient(135deg, #e94560, #8b5cf6);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 32px rgba(233, 69, 96, 0.45);
  z-index: 2;
}

.avatar-icon { font-size: 48px; }

.state-listening .avatar-ring {
  animation: pulseRing 1.6s ease-out infinite;
  border-color: rgba(96, 165, 250, 0.6);
}
.state-listening .ring-2 { animation-delay: 0.4s; }
.state-listening .ring-3 { animation-delay: 0.8s; }
.state-listening .avatar-core {
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
}

.state-thinking .avatar-ring {
  animation: spin 2s linear infinite;
  border-color: rgba(251, 191, 36, 0.5);
  border-style: dashed;
}
.state-thinking .ring-2 { animation-direction: reverse; }
.state-thinking .avatar-core {
  background: linear-gradient(135deg, #fbbf24, #f59e0b);
}

.state-speaking .avatar-ring {
  animation: speakWave 1.2s ease-in-out infinite;
  border-color: rgba(167, 139, 250, 0.5);
}
.state-speaking .ring-2 { animation-delay: 0.3s; }
.state-speaking .ring-3 { animation-delay: 0.6s; }
.state-speaking .avatar-core {
  background: linear-gradient(135deg, #a78bfa, #8b5cf6);
}

@keyframes pulseRing {
  0% { transform: scale(0.85); opacity: 0.8; }
  100% { transform: scale(1.2); opacity: 0; }
}
@keyframes speakWave {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.06); opacity: 1; }
}
@keyframes spin {
  from { transform: rotate(0); }
  to { transform: rotate(360deg); }
}

.state-label {
  margin-top: 8px;
  font-size: clamp(16px, 2.4vh, 18px);
  font-weight: 600;
  color: #fff;
}

.transcript-area {
  flex: 1;
  width: 100%;
  margin: 24px 0;
  overflow-y: auto;
  padding: 4px;
}

.transcript-area::-webkit-scrollbar { width: 4px; }
.transcript-area::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }

.bubble {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 8px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.55;
}

.bubble.user {
  background: rgba(96, 165, 250, 0.1);
  border: 1px solid rgba(96, 165, 250, 0.2);
}
.bubble.assistant {
  background: rgba(167, 139, 250, 0.1);
  border: 1px solid rgba(167, 139, 250, 0.2);
}

.role-tag {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding-top: 3px;
}

.text { flex: 1; }

.cursor {
  animation: blink 0.8s ease-in-out infinite;
  color: #a78bfa;
  margin-left: 2px;
}
@keyframes blink {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}

.error-bar {
  width: 100%;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #f87171;
  font-size: 13px;
}

.controls {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}

.primary-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  border-radius: 32px;
  border: none;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  color: #fff;
}

.call-btn {
  background: linear-gradient(135deg, #4ade80, #22c55e);
  box-shadow: 0 4px 18px rgba(74, 222, 128, 0.35);
}

.hangup-btn {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  box-shadow: 0 4px 18px rgba(239, 68, 68, 0.4);
}

.primary-btn:hover { transform: scale(1.04); }
.primary-btn:active { transform: scale(0.98); }
.ico { font-size: 17px; }

.hint {
  font-size: 12px;
  color: #64748b;
  text-align: center;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (max-height: 760px) {
  .call-panel {
    padding-top: 16px;
    padding-bottom: 18px;
  }

  .avatar-wrap {
    width: clamp(132px, 22vh, 180px);
    height: clamp(132px, 22vh, 180px);
    margin: 16px 0 10px;
  }

  .transcript-area {
    margin: 16px 0;
  }

  .primary-btn {
    padding: 12px 24px;
  }
}
</style>

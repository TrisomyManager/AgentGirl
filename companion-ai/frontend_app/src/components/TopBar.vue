<template>
  <header class="top-bar">
    <div class="top-bar-left">
      <div class="avatar-wrapper">
        <img
          src="https://placehold.co/48x48/e94560/FFF?text=暖"
          alt="小暖"
          class="avatar-img"
        />
        <div class="avatar-status"></div>
      </div>
      <div class="companion-info">
        <span class="companion-name">小暖</span>
        <span v-if="serverAvailable === false" class="offline-badge">离线</span>
      </div>
    </div>

    <div class="top-bar-center">
      <div class="emotion-tag" :class="emotionClass">
        <span class="emotion-dot"></span>
        <span>{{ emotionLabel }}</span>
      </div>
    </div>

    <div class="top-bar-right">
      <button class="icon-btn call-btn" @click="$emit('open-call')" title="语音通话">
        <span class="icon-call">📞</span>
      </button>
      <button class="icon-btn memory-btn" @click="$emit('open-memory')" title="记忆库">
        <span class="icon-memory">🧠</span>
      </button>
      <button
        class="icon-btn"
        :class="{ active: voice.autoPlayEnabled.value }"
        @click="voice.toggleAutoPlay()"
        :title="voice.autoPlayEnabled.value ? '语音已开启' : '语音已关闭'"
      >
        <span class="icon-sound" :class="{ playing: voice.isPlaying.value }">
          {{ voice.autoPlayEnabled.value ? '🔊' : '🔇' }}
        </span>
      </button>
      <button class="icon-btn" @click="$emit('open-status')" title="项目状态">
        <span class="icon-status">📊</span>
      </button>
      <button class="icon-btn" @click="$emit('open-settings')" title="设置">
        <span class="icon-gear">⚙️</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { useVoice } from '../composables/useVoice';

defineEmits<{
  (e: 'open-settings'): void;
  (e: 'open-status'): void;
  (e: 'open-call'): void;
  (e: 'open-memory'): void;
}>();

const props = defineProps<{
  emotionLabel: string;
  emotion: string;
  serverAvailable: boolean | null;
  voice: ReturnType<typeof useVoice>;
}>();

const emotionClass = computed(() => {
  const map: Record<string, string> = {
    happy: 'emotion-happy',
    excited: 'emotion-happy',
    sad: 'emotion-sad',
    angry: 'emotion-angry',
    surprised: 'emotion-surprised',
    calm: 'emotion-calm',
    neutral: 'emotion-calm',
  };
  return map[props.emotion] || 'emotion-calm';
});
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: rgba(26, 26, 46, 0.8);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  flex-shrink: 0;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.avatar-wrapper {
  position: relative;
  width: 40px;
  height: 40px;
}

.avatar-img {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid rgba(233, 69, 96, 0.5);
}

.avatar-status {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 10px;
  height: 10px;
  background: #4ade80;
  border-radius: 50%;
  border: 2px solid #1a1a2e;
}

.companion-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.companion-name {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
}

.offline-badge {
  font-size: 11px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.15);
  padding: 1px 6px;
  border-radius: 10px;
  width: fit-content;
}

.top-bar-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.emotion-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  background: rgba(255, 255, 255, 0.05);
  color: #ccc;
  transition: all 0.3s ease;
}

.emotion-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.emotion-happy {
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.12);
}

.emotion-sad {
  color: #60a5fa;
  background: rgba(96, 165, 250, 0.12);
}

.emotion-angry {
  color: #f87171;
  background: rgba(248, 113, 113, 0.12);
}

.emotion-surprised {
  color: #c084fc;
  background: rgba(192, 132, 252, 0.12);
}

.emotion-calm {
  color: #6ee7b7;
  background: rgba(110, 231, 183, 0.12);
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  justify-content: flex-end;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.05);
  color: #aaa;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all 0.2s ease;
}

.icon-btn:hover {
  background: rgba(233, 69, 96, 0.2);
  color: #fff;
}

.icon-btn.active {
  background: rgba(233, 69, 96, 0.2);
  color: #e94560;
}

.call-btn {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}
.call-btn:hover {
  background: rgba(74, 222, 128, 0.3);
  color: #fff;
}

.memory-btn {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
}
.memory-btn:hover {
  background: rgba(167, 139, 250, 0.3);
  color: #fff;
}

.icon-sound.playing {
  animation: soundPulse 0.8s ease-in-out infinite;
}

@keyframes soundPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}
</style>

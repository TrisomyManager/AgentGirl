<template>
  <header class="top-bar">
    <div class="identity-block">
      <div class="avatar-wrapper">
        <img
          src="https://placehold.co/48x48/e94560/FFF?text=暖"
          alt="小暖"
          class="avatar-img"
        />
        <div class="avatar-status"></div>
      </div>

      <div class="identity-copy">
        <span class="companion-name">小暖</span>
        <div class="identity-meta">
          <span class="companion-role">Companion Console</span>
          <span v-if="serverAvailable === false" class="offline-badge">离线</span>
        </div>
      </div>
    </div>

    <div class="center-pill">
      <div class="emotion-tag" :class="emotionClass">
        <span class="emotion-dot"></span>
        <span>{{ emotionLabel }}</span>
      </div>
    </div>

    <nav class="action-strip" aria-label="主操作">
      <button class="icon-btn call-btn" @click="$emit('open-call')" title="语音通话">
        <span>📞</span>
      </button>
      <button class="icon-btn memory-btn" @click="$emit('open-memory')" title="记忆库">
        <span>🧠</span>
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
        <span>📊</span>
      </button>
      <button class="icon-btn" @click="$emit('open-settings')" title="设置">
        <span>⚙️</span>
      </button>
    </nav>
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
    affectionate: 'emotion-affectionate',
    concerned: 'emotion-concerned',
    fearful: 'emotion-concerned',
    disgusted: 'emotion-angry',
    calm: 'emotion-calm',
    neutral: 'emotion-calm',
  };
  return map[props.emotion] || 'emotion-calm';
});
</script>

<style scoped>
.top-bar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0));
  flex-shrink: 0;
  min-width: 0;
}

.identity-block {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  flex: 1 1 0;
  z-index: 3;
}

.avatar-wrapper {
  position: relative;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
}

.avatar-img {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid rgba(251, 113, 133, 0.55);
  box-shadow: 0 0 24px rgba(233, 69, 96, 0.18);
}

.avatar-status {
  position: absolute;
  right: 2px;
  bottom: 2px;
  width: 11px;
  height: 11px;
  border: 2px solid #101626;
  border-radius: 50%;
  background: #4ade80;
}

.identity-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.companion-name {
  color: #f8fafc;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.1;
}

.identity-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  min-width: 0;
}

.companion-role {
  color: #94a3b8;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.offline-badge {
  padding: 2px 8px;
  border: 1px solid rgba(248, 113, 113, 0.2);
  border-radius: 999px;
  background: rgba(127, 29, 29, 0.28);
  color: #fca5a5;
  font-size: 11px;
}

.center-pill {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  justify-content: center;
  pointer-events: none;
  z-index: 2;
}

.center-pill .emotion-tag {
  pointer-events: auto;
}

.emotion-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
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
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
}

.emotion-angry {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.12);
}

.emotion-surprised {
  color: #d8b4fe;
  background: rgba(192, 132, 252, 0.12);
}

.emotion-calm {
  color: #86efac;
  background: rgba(74, 222, 128, 0.12);
}

.emotion-affectionate {
  color: #fda4af;
  background: rgba(244, 114, 182, 0.14);
}

.emotion-concerned {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.14);
}

.action-strip {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1 1 0;
  min-width: 0;
  z-index: 3;
}

.icon-btn {
  width: 40px;
  height: 40px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
}

.icon-btn:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.14);
  color: #fff;
}

.icon-btn.active {
  background: rgba(233, 69, 96, 0.18);
  border-color: rgba(251, 113, 133, 0.24);
  color: #fda4af;
}

.call-btn {
  color: #86efac;
  background: rgba(34, 197, 94, 0.12);
}

.memory-btn {
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.12);
}

.icon-sound.playing {
  animation: soundPulse 0.8s ease-in-out infinite;
}

@keyframes soundPulse {
  0%, 100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.18);
  }
}

@media (max-width: 960px) {
  .top-bar {
    flex-wrap: wrap;
    row-gap: 12px;
    padding: 16px 16px 14px;
  }

  .identity-block {
    flex: 1 1 auto;
    min-width: min(100%, 200px);
  }

  .center-pill {
    position: static;
    transform: none;
    order: 3;
    flex: 1 1 100%;
    justify-content: center;
    pointer-events: auto;
  }

  .action-strip {
    flex: 0 0 auto;
  }
}

@media (max-width: 640px) {
  .top-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding: 14px 14px 12px;
  }

  .identity-block {
    flex: none;
    order: 1;
  }

  .center-pill {
    position: static;
    transform: none;
    order: 2;
    pointer-events: auto;
  }

  .action-strip {
    flex: none;
    justify-content: center;
    flex-wrap: wrap;
    order: 3;
  }

  .companion-name {
    font-size: 17px;
  }
}
</style>

<template>
  <div class="avatar-display">
    <!-- Live2D容器 -->
    <div class="avatar-container" :class="{ floating: isTyping }">
      <div class="avatar-glow"></div>

      <!-- Live2D Canvas -->
      <div
        ref="live2dContainer"
        class="live2d-canvas"
        :class="{ hidden: isLoading || !!live2dError }"
      ></div>

      <!-- 加载中占位符 -->
      <div v-if="isLoading" class="placeholder loading">
        <div class="spinner"></div>
        <p>加载小暖中...</p>
      </div>

      <!-- 错误降级到静态图片 -->
      <img
        v-if="live2dError"
        src="https://placehold.co/400x600/1a1a2e/FFF?text=小暖"
        alt="小暖"
        class="avatar-image fallback"
      />
    </div>

    <div class="avatar-info">
      <div class="emotion-badge" :class="emotionClass">
        <span class="emotion-icon">{{ emotionIcon }}</span>
        <span>{{ emotionLabel }}</span>
      </div>
      <div v-if="actionLabel" class="action-text">
        {{ actionLabel }}
      </div>
    </div>

    <div class="decoration-orbs">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLive2D } from '../composables/useLive2D';

const props = defineProps<{
  emotionLabel: string;
  emotion: string;
  actionLabel: string;
  isTyping: boolean;
}>();

// Live2D容器引用
const live2dContainer = ref<HTMLElement | null>(null);

// 使用免费CDN测试模型（Shizuku - SDK 2.x样本）
const {
  isLoading,
  error: live2dError,
  playMotion,
  setExpression,
  getMotionGroups,
} = useLive2D(live2dContainer, {
  modelPath:
    'https://raw.githubusercontent.com/guansss/pixi-live2d-display/master/test/assets/shizuku/shizuku.model.json',
  width: 260,
  height: 390,
  autoInteract: true,
});

// 情绪映射到Live2D动作
const emotionToMotion: Record<string, string> = {
  happy: 'tap_body',
  excited: 'shake',
  sad: 'flick_head',
  angry: 'pinch_in',
  surprised: 'shake',
  calm: 'idle',
  neutral: 'idle',
};

// 监听情绪变化，播放对应动作
watch(
  () => props.emotion,
  (newEmotion) => {
    const motionGroup = emotionToMotion[newEmotion] || 'idle';
    playMotion(motionGroup, 0, 2);
  }
);

// 监听打字状态
watch(
  () => props.isTyping,
  (typing) => {
    if (typing) {
      playMotion('tap_body', 0, 3); // 高优先级打字动作
    }
  }
);

// 调试：输出可用的动作组
onMounted(() => {
  setTimeout(() => {
    const groups = getMotionGroups();
    if (groups.length > 0) {
      console.log('Available Live2D motion groups:', groups);
    }
  }, 2000);
});

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

const emotionIcon = computed(() => {
  const map: Record<string, string> = {
    happy: '😊',
    excited: '🤩',
    sad: '😢',
    angry: '😠',
    surprised: '😲',
    fearful: '😨',
    disgusted: '🤢',
    affectionate: '🥰',
    concerned: '😟',
    calm: '😌',
    neutral: '😐',
  };
  return map[props.emotion] || '😐';
});
</script>

<style scoped>
.avatar-display {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: clamp(12px, 2vh, 24px);
  height: 100%;
  width: 100%;
  min-height: 0;
  padding: clamp(14px, 1.8vw, 20px);
  overflow: hidden;
}

.avatar-container {
  position: relative;
  flex: 0 1 auto;
  width: min(100%, clamp(180px, 19vw, 280px));
  aspect-ratio: 2 / 3;
  height: auto;
  max-height: min(52vh, 420px);
  border-radius: 20px;
  overflow: hidden;
  transition: transform 0.3s ease;
}

.avatar-container.floating {
  animation: float 2s ease-in-out infinite;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-5px);
  }
}

.avatar-glow {
  position: absolute;
  inset: -10px;
  background: radial-gradient(
    ellipse at center,
    rgba(233, 69, 96, 0.15) 0%,
    transparent 70%
  );
  border-radius: 30px;
  z-index: 0;
  animation: glowPulse 3s ease-in-out infinite;
}

@keyframes glowPulse {
  0%, 100% {
    opacity: 0.5;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}

.live2d-canvas {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  border-radius: 20px;
  transition: opacity 0.3s ease;
}

.live2d-canvas.hidden {
  opacity: 0;
  pointer-events: none;
}

.placeholder {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 2;
  background: rgba(26, 26, 46, 0.6);
  border-radius: 20px;
}

.placeholder.loading {
  color: #94a3b8;
  font-size: 13px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(233, 69, 96, 0.2);
  border-top-color: #e94560;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.avatar-image {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.avatar-image.fallback {
  position: absolute;
  top: 0;
  left: 0;
}

.avatar-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  z-index: 1;
}

.emotion-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border-radius: 24px;
  font-size: 14px;
  font-weight: 500;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: all 0.3s ease;
}

.emotion-icon {
  font-size: 18px;
}

.emotion-happy {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.2);
  background: rgba(251, 191, 36, 0.08);
}

.emotion-sad {
  color: #60a5fa;
  border-color: rgba(96, 165, 250, 0.2);
  background: rgba(96, 165, 250, 0.08);
}

.emotion-angry {
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.2);
  background: rgba(248, 113, 113, 0.08);
}

.emotion-surprised {
  color: #c084fc;
  border-color: rgba(192, 132, 252, 0.2);
  background: rgba(192, 132, 252, 0.08);
}

.emotion-calm {
  color: #6ee7b7;
  border-color: rgba(110, 231, 183, 0.2);
  background: rgba(110, 231, 183, 0.08);
}

.action-text {
  font-size: 13px;
  color: #e94560;
  padding: 4px 14px;
  border-radius: 12px;
  background: rgba(233, 69, 96, 0.1);
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.decoration-orbs {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.3;
}

.orb-1 {
  width: 120px;
  height: 120px;
  background: rgba(233, 69, 96, 0.3);
  top: 10%;
  left: 10%;
  animation: orbMove1 8s ease-in-out infinite;
}

.orb-2 {
  width: 80px;
  height: 80px;
  background: rgba(139, 92, 246, 0.2);
  bottom: 20%;
  right: 15%;
  animation: orbMove2 10s ease-in-out infinite;
}

.orb-3 {
  width: 60px;
  height: 60px;
  background: rgba(59, 130, 246, 0.2);
  top: 40%;
  right: 10%;
  animation: orbMove3 7s ease-in-out infinite;
}

@keyframes orbMove1 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(20px, 30px); }
}

@keyframes orbMove2 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(-15px, -20px); }
}

@keyframes orbMove3 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(10px, -15px); }
}

@media (max-height: 780px) {
  .avatar-display {
    gap: 12px;
    padding: 12px;
  }

  .avatar-container {
    width: min(100%, 210px);
    max-height: min(38vh, 315px);
  }

  .avatar-info {
    gap: 8px;
  }

  .emotion-badge {
    padding: 7px 16px;
    font-size: 13px;
  }
}
</style>

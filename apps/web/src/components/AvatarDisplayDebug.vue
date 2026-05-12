<template>
  <div class="avatar-display">
    <!-- 调试信息面板 -->
    <div class="debug-panel">
      <h3>Live2D Debug</h3>
      <p>Loading: {{ isLoading }}</p>
      <p>Error: {{ live2dError || 'None' }}</p>
      <p>Container: {{ live2dContainer ? 'Ready' : 'Not Ready' }}</p>
    </div>

    <!-- 简化版Avatar容器 -->
    <div class="avatar-container">
      <div ref="live2dContainer" class="live2d-canvas"></div>

      <div v-if="isLoading" class="placeholder">
        <div class="spinner"></div>
        <p>Loading...</p>
      </div>

      <div v-if="live2dError" class="error-msg">
        <p>{{ live2dError }}</p>
        <img src="https://placehold.co/400x600/1a1a2e/FFF?text=Fallback" alt="Fallback" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useLive2D } from '../composables/useLive2D';

const live2dContainer = ref<HTMLElement | null>(null);

const { isLoading, error: live2dError } = useLive2D(live2dContainer, {
  modelPath:
    'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json',
  width: 260,
  height: 390,
  autoInteract: true,
});
</script>

<style scoped>
.avatar-display {
  padding: 20px;
  background: #0d0d1a;
  color: #e2e8f0;
  min-height: 100vh;
}

.debug-panel {
  background: rgba(255, 255, 255, 0.05);
  padding: 16px;
  margin-bottom: 20px;
  border-radius: 8px;
  font-size: 14px;
  font-family: monospace;
}

.debug-panel h3 {
  margin: 0 0 12px 0;
  color: #e94560;
}

.debug-panel p {
  margin: 4px 0;
}

.avatar-container {
  position: relative;
  width: 260px;
  height: 390px;
  border: 2px solid #e94560;
  border-radius: 20px;
  overflow: hidden;
}

.live2d-canvas {
  width: 100%;
  height: 100%;
  background: rgba(26, 26, 46, 0.5);
}

.placeholder,
.error-msg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(13, 13, 26, 0.9);
  z-index: 10;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(233, 69, 96, 0.2);
  border-top-color: #e94560;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-msg img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>

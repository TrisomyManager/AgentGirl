<template>
  <div class="debug-app">
    <h1>Live2D Debug Page</h1>
    <AvatarDisplayDebug />
  </div>
</template>

<script setup lang="ts">
import AvatarDisplayDebug from './components/AvatarDisplayDebug.vue';
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.debug-app {
  background: #0d0d1a;
  color: #e2e8f0;
  min-height: 100vh;
  padding: 20px;
  font-family: 'Inter', sans-serif;
}

.debug-app h1 {
  color: #e94560;
  margin-bottom: 20px;
}
</style>

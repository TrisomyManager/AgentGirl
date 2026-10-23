// Use Vite alias to reach apps/web/src/
import { createApp } from 'vue';

// Keep the transparent pet surface separate from the full chat UI and its CSS.
async function start() {
  const module = new URLSearchParams(location.search).get('view') === 'pet'
    ? await import('@/components/DesktopPet.vue') : await import('@/App.vue');
  createApp(module.default as any).mount('#app');
}
void start();

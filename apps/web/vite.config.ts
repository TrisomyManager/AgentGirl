import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';
import { fileURLToPath } from 'node:url';
import { runtimeAssets } from '../../packages/web-runtime-assets/vite.mts';

export default defineConfig({
  plugins: [vue(), runtimeAssets(fileURLToPath(new URL('.', import.meta.url)))],
  resolve: {
    dedupe: ['vue', '@ricky0123/vad-web', 'onnxruntime-web'],
    alias: {
      '@': resolve(fileURLToPath(new URL('.', import.meta.url)), 'src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    // Cloudflare Quick Tunnel / reverse proxies send non-local Host headers.
    allowedHosts: true,
  },
});

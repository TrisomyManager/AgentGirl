import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import electron from 'vite-plugin-electron';
import { resolve } from 'path';
import { fileURLToPath } from 'node:url';
import { runtimeAssets } from '../../packages/web-runtime-assets/vite.mts';

const projectRoot = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  base: './',
  publicDir: resolve(projectRoot, '../web/public'),
  plugins: [
    vue(),
    runtimeAssets(projectRoot),
    electron([
      {
        entry: 'electron/main.ts',
        vite: {
          build: {
            outDir: 'dist-electron',
            rolldownOptions: {
              external: ['electron', 'electron-store'],
            },
          },
          resolve: {
            conditions: ['node'],
          },
          define: {
            'process.env.ELECTRON_RUN_AS_NODE': '""',
          },
        },
      },
      {
        entry: 'electron/preload.ts',
        onstart(options) {
          options.reload();
        },
        vite: {
          build: {
            outDir: 'dist-electron',
          },
        },
      },
    ]),
  ],
  resolve: {
    dedupe: ['vue', '@ricky0123/vad-web', 'onnxruntime-web', 'pixi.js', 'pixi-live2d-display'],
    alias: {
      '@': resolve(projectRoot, '../web/src'),
    },
  },
  // Prevent Node.js built-ins from leaking into renderer via deep deps
  optimizeDeps: {
    exclude: [],
  },
  server: {
    port: 5174,
    host: true,
    fs: {
      allow: ['..', '../web/src'],
    },
  },
  build: {
    outDir: 'dist',
  },
});

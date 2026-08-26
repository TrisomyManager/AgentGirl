import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import electron from 'vite-plugin-electron';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    vue(),
    electron([
      {
        entry: 'electron/main.ts',
        vite: {
          build: {
            outDir: 'dist-electron',
            rollupOptions: {
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
    alias: {
      '@': resolve(__dirname, '../web/src'),
    },
  },
  // Prevent Node.js built-ins from leaking into renderer via deep deps
  optimizeDeps: {
    exclude: [],
  },
  define: {
    'process.env.NODE_ENV': '"development"',
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

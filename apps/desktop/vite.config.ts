import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Vite config for the WindAgent desktop app with Phase UI11 Rollup code-splitting & Shared App.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@windagent/ui': path.resolve(__dirname, '../../frontend/packages/ui/src/index.ts'),
      '@windagent/app/src': path.resolve(__dirname, '../../frontend/app/src'),
      '@windagent/app': path.resolve(__dirname, '../../frontend/app/src/index.ts'),
      '@windagent/api-contracts': path.resolve(__dirname, '../../frontend/packages/api-contracts/src/index.ts'),
      '@windagent/api-client': path.resolve(__dirname, '../../frontend/packages/api-client/src/index.ts'),
      '@windagent/realtime': path.resolve(__dirname, '../../frontend/packages/realtime/src/index.ts'),
      '@windagent/studio-shell': path.resolve(__dirname, '../../frontend/packages/studio-shell/src/index.ts'),
      '@windagent/story-ui': path.resolve(__dirname, '../../frontend/packages/story-ui/src/index.ts'),
      '@windagent/production-contracts': path.resolve(__dirname, '../../frontend/packages/production-contracts/src/index.ts'),
      '@windagent/production-client': path.resolve(__dirname, '../../frontend/packages/production-client/src/index.ts'),
      '@windagent/production-platform': path.resolve(__dirname, '../../frontend/packages/production-platform/src/index.ts'),
      '@windagent/production-state': path.resolve(__dirname, '../../frontend/packages/production-state/src/index.ts'),
      '@windagent/production-ui': path.resolve(__dirname, '../../frontend/packages/production-ui/src/index.ts'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: {
      allow: ['..', '../../frontend'],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        ws: true,
      },
      "/health": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom')) {
              return 'vendor-react';
            }
            if (id.includes('lucide-react')) {
              return 'vendor-icons';
            }
          }
          if (id.includes('frontend/packages/ui')) {
            return 'shared-ui';
          }
          if (id.includes('frontend/packages/story-ui')) {
            return 'story-ui';
          }
          if (id.includes('frontend/packages/studio-shell')) {
            return 'studio-shell';
          }
          if (id.includes('frontend/app')) {
            return 'shared-app';
          }
        },
      },
    },
  },
});
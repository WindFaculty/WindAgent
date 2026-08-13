import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Vite config for the WindAgent desktop app with Phase UI11 Rollup code-splitting.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
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
        rewrite: (p) => p.replace(/^\/api/, ""),
        ws: true,
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
          if (id.includes('frontend/packages/story-ui')) {
            return 'story-ui';
          }
          if (id.includes('frontend/packages/studio-shell')) {
            return 'studio-shell';
          }
        },
      },
    },
  },
});
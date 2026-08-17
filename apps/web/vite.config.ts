import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      '@desktop': path.resolve(__dirname, '../desktop/src'),
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
      allow: ['..', '../../frontend', '../desktop'],
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
    emptyOutDir: true,
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    passWithNoTests: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      thresholds: {
        statements: 75,
        branches: 65,
        functions: 70,
        lines: 75,
      },
    },
  },
});

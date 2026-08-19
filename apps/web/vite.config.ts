import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      "@": path.resolve(__dirname, "./src"),
      'react': path.resolve(__dirname, '../../frontend/node_modules/react'),
      'react-dom': path.resolve(__dirname, '../../frontend/node_modules/react-dom'),
      '@testing-library/react': path.resolve(__dirname, '../../frontend/node_modules/@testing-library/react'),
      '@tanstack/react-query': path.resolve(__dirname, '../../frontend/node_modules/@tanstack/react-query'),
      '@windagent/app/styles.css': path.resolve(__dirname, '../../frontend/app/src/styles/index.css'),
      '@windagent/app/src': path.resolve(__dirname, '../../frontend/app/src'),
      '@windagent/app': path.resolve(__dirname, '../../frontend/app/src/index.ts'),
      '@windagent/ui/styles.css': path.resolve(__dirname, '../../frontend/packages/ui/src/styles/index.css'),
      '@windagent/ui': path.resolve(__dirname, '../../frontend/packages/ui/src/index.ts'),
      '@windagent/api-contracts': path.resolve(__dirname, '../../frontend/packages/api-contracts/src/index.ts'),
      '@windagent/api-client': path.resolve(__dirname, '../../frontend/packages/api-client/src/index.ts'),
      '@windagent/realtime': path.resolve(__dirname, '../../frontend/packages/realtime/src/index.ts'),
      '@windagent/studio-shell': path.resolve(__dirname, '../../frontend/packages/studio-shell/src/index.ts'),
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
        target: "http://127.0.0.1:8765",
        ws: true,
        changeOrigin: true,
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

// Vitest config for the WindAgent desktop app.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // All frontend deps share ONE react copy (frontend root) — RTL included,
      // else components and renderer bind to different React instances.
      // Order matters: most specific subpaths first (alias is prefix-matched).
      'react/jsx-dev-runtime': path.resolve(__dirname, '../../frontend/node_modules/react/jsx-dev-runtime.js'),
      'react/jsx-runtime': path.resolve(__dirname, '../../frontend/node_modules/react/jsx-runtime.js'),
      'react-dom/client': path.resolve(__dirname, '../../frontend/node_modules/react-dom/client.js'),
      'react-dom': path.resolve(__dirname, '../../frontend/node_modules/react-dom/index.js'),
      'react': path.resolve(__dirname, '../../frontend/node_modules/react/index.js'),
      '@testing-library/react': path.resolve(__dirname, '../../frontend/node_modules/@testing-library/react'),
      '@testing-library/dom': path.resolve(__dirname, '../../frontend/node_modules/@testing-library/dom'),
      '@windagent/ui': path.resolve(__dirname, '../../frontend/packages/ui/src/index.ts'),
      '@tanstack/react-query': path.resolve(__dirname, '../../frontend/node_modules/@tanstack/react-query'),
      // Single React copy — desktop + @windagent/app must share one instance or hooks break.
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
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

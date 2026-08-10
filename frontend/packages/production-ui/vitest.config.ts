// Vitest config for the shared @windagent/production-ui package.
//
// Mirrors the desktop app config (apps/desktop/vitest.config.ts): tests use
// global describe/it/expect and happy-dom so component tests behave the same
// in the shared package and the Tauri shell.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

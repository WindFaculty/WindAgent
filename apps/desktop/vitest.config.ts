// Vitest config for the WindAgent desktop app.
//
// We reuse the Vite config so React + TypeScript paths work the same
// way as in dev/build, but override `test` to use happy-dom (lighter
// than jsdom, works on Windows without extra C++ deps).
//
// See https://vitest.dev/config/ for the full schema.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // CSS imports in components would otherwise error; we don't load
    // styles.css from any component, so no need for a CSS stub plugin.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

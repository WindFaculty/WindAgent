import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite config for the WindAgent desktop app.
//
// Dev server proxies `/api` to the FastAPI backend on localhost:8765 so
// the React app can call same-origin paths in dev. In Tauri production,
// the backend runs as a sidecar (Phase 9) and the host is `tauri://`.
//
// WebSocket path is `/ws/...` which the proxy also forwards.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
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
  },
});
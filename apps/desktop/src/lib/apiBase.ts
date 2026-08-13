/**
 * ONE DESKTOP API BASE AUTHORITY (UI0-INFRA-01).
 *
 * The canonical WindAgent backend authority is 127.0.0.1:8765
 * (scripts/dev_api.ps1, vite dev proxy, scripts/healthcheck.ps1, run.ps1).
 * VITE_API_BASE stays the override knob. The previous divergent defaults —
 * api/client.ts hardcode, StudioPage `http://localhost:8000`, routerApi
 * relative-to-origin — are collapsed here so every client in the app
 * resolves the same base.
 */
const VITE_API_BASE: string | undefined =
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_BASE) ||
  (typeof process !== "undefined" ? process.env?.VITE_API_BASE : undefined);

export const API_BASE: string = VITE_API_BASE || "http://127.0.0.1:8765";
export const WS_BASE: string = API_BASE.replace(/^http/, "ws");

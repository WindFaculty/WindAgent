import { describe, expect, it, vi } from "vitest";

describe("apiBase — one desktop API base authority (UI0-INFRA-01)", () => {
  it("defaults to the canonical backend authority 127.0.0.1:8765", async () => {
    vi.stubEnv("VITE_API_BASE", "");
    vi.resetModules();
    const { API_BASE, WS_BASE } = await import("./apiBase");
    expect(API_BASE).toBe("http://127.0.0.1:8765");
    expect(WS_BASE).toBe("ws://127.0.0.1:8765");
    vi.unstubAllEnvs();
  });

  it("honors the VITE_API_BASE override", async () => {
    vi.stubEnv("VITE_API_BASE", "http://10.0.0.5:9000");
    vi.resetModules();
    const { API_BASE, WS_BASE } = await import("./apiBase");
    expect(API_BASE).toBe("http://10.0.0.5:9000");
    expect(WS_BASE).toBe("ws://10.0.0.5:9000");
    vi.unstubAllEnvs();
  });
});

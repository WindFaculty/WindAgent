import { describe, expect, it } from "vitest";
import { createQueryClient } from "../query-client.ts";
import { useConnectionStatus } from "../connection-status.ts";

describe("createQueryClient", () => {
  it("uses the canonical V2 cache defaults", () => {
    const client = createQueryClient();
    const defaults = client.getDefaultOptions().queries;
    expect(defaults?.staleTime).toBe(5_000);
    expect(defaults?.retry).toBe(1);
    expect(defaults?.refetchOnWindowFocus).toBe(false);
  });
});

describe("useConnectionStatus", () => {
  it("starts idle and can be updated", () => {
    expect(useConnectionStatus.getState().status).toBe("idle");
    useConnectionStatus.getState().setStatus("connected");
    expect(useConnectionStatus.getState().status).toBe("connected");
    useConnectionStatus.getState().setStatus("idle");
  });
});

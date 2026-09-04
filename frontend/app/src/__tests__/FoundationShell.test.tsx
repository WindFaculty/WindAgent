import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createQueryClient } from "@windagent/platform";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FoundationShell } from "../app/shell/FoundationShell.tsx";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("FoundationShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { status: "ok", version: "0.1.0" })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a healthy status pill once the health query resolves", async () => {
    const client = createQueryClient();
    render(
      <QueryClientProvider client={client}>
        <FoundationShell />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status-pill").getAttribute("data-level")).toBe("ok");
    });
    expect(screen.getByTestId("status-pill").textContent).toContain("API healthy");
  });
});

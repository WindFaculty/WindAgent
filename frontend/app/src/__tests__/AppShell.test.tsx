import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createQueryClient } from "@windagent/platform";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../app/shell/AppShell.tsx";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: unknown) => {
        const url = String(input);
        if (url.includes("/health")) {
          return jsonResponse(200, { status: "ok", version: "0.1.0" });
        }
        if (url.includes("/api/v4/workspaces")) {
          return jsonResponse(200, [
            {
              id: "ws-default",
              name: "Primary Studio Workspace",
              slug: "primary-studio",
              owner_id: "user-admin",
              status: "active",
              created_at: "2026-09-02T10:00:00Z",
              updated_at: "2026-09-02T10:00:00Z",
              members_count: 3,
            },
          ]);
        }
        return jsonResponse(200, {});
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the master layout with sidebar navigation and active workspace", async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AppShell />
      </QueryClientProvider>,
    );

    expect(screen.getByText("WindAgent")).toBeDefined();
    expect(screen.getByText("Workspaces")).toBeDefined();
    expect(screen.getByText("Studio & Story")).toBeDefined();
    expect(screen.getByText("Agent Runtime")).toBeDefined();
    expect(screen.getByText("Model Gateway")).toBeDefined();
    expect(screen.getByText("Automation Tools")).toBeDefined();
    expect(screen.getByText("Video Production")).toBeDefined();
    expect(screen.getByText("Live Record")).toBeDefined();
    expect(screen.getByText("Quality & Gates")).toBeDefined();
    expect(screen.getByText("Operations & Logs")).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText("API v4 Connected")).toBeDefined();
    });
  });
});

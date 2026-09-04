import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "../client.ts";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("createApiClient", () => {
  it("GETs /health and types the response", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async () => jsonResponse(200, { status: "ok", version: "0.1.0" }),
    });
    await expect(client.health()).resolves.toEqual({ status: "ok", version: "0.1.0" });
  });

  it("throws ApiError on non-2xx with error details", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async () => jsonResponse(503, { error: "Database unreachable" }),
    });
    await expect(client.ready()).rejects.toBeInstanceOf(ApiError);
  });

  it("strips a trailing slash from baseUrl", async () => {
    let seen = "";
    const client = createApiClient({
      baseUrl: "http://api.test/",
      fetch: async (input) => {
        seen = String(input);
        return jsonResponse(200, { status: "ready", environment: "development", database: "postgresql+asyncpg" });
      },
    });
    await client.ready();
    expect(seen).toBe("http://api.test/ready");
  });

  it("calls workspace endpoints correctly", async () => {
    let capturedUrl = "";
    let capturedMethod = "";
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async (input, init) => {
        capturedUrl = String(input);
        capturedMethod = init?.method ?? "GET";
        return jsonResponse(200, [
          {
            id: "ws-1",
            name: "Default Workspace",
            slug: "default",
            owner_id: "user-1",
            status: "active",
            created_at: "2026-09-02T00:00:00Z",
            updated_at: "2026-09-02T00:00:00Z",
            members_count: 1,
          },
        ]);
      },
    });

    const workspaces = await client.listWorkspaces();
    expect(capturedUrl).toBe("http://api.test/api/v4/workspaces");
    expect(capturedMethod).toBe("GET");
    expect(workspaces).toHaveLength(1);
    expect(workspaces[0]?.slug).toBe("default");
  });

  it("calls studio story generator with payload", async () => {
    let capturedBody = "";
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async (_, init) => {
        capturedBody = String(init?.body);
        return jsonResponse(200, { story_text: "Once upon a time in Neo Tokyo..." });
      },
    });

    const res = await client.generateStory({ project_id: "proj-123", prompt: "Cyberpunk heist" });
    expect(res.story_text).toContain("Neo Tokyo");
    expect(JSON.parse(capturedBody)).toEqual({ project_id: "proj-123", prompt: "Cyberpunk heist" });
  });

  it("resolves approval requests with boolean response", async () => {
    let capturedUrl = "";
    let capturedBody = "";
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async (input, init) => {
        capturedUrl = String(input);
        capturedBody = String(init?.body);
        return jsonResponse(200, {
          id: "appr-1",
          session_id: "sess-1",
          action_name: "deploy_production",
          risk_level: "critical",
          description: "Deploy new model",
          parameters: {},
          status: "approved",
          created_at: "2026-09-02T00:00:00Z",
        });
      },
    });

    const res = await client.resolveApproval("appr-1", true);
    expect(capturedUrl).toBe("http://api.test/api/v4/agent-runtime/approvals/appr-1/resolve");
    expect(JSON.parse(capturedBody)).toEqual({ approved: true });
    expect(res.status).toBe("approved");
  });
});

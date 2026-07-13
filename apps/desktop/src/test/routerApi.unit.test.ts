/**
 * routerApi.unit.test.ts — Phase 6 unit tests for the Router API client.
 *
 * Tests use vitest's mock to avoid real HTTP requests.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  RouterApiError,
  fetchRoutingRules,
  fetchRoutingStats,
  fetchTrafficDistribution,
  fetchRoutingGraph,
  deleteRoutingRule,
  createRoutingRule,
  simulateRoute,
  testRoute,
} from "../lib/routerApi";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(response: unknown, status = 200, ok = true) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
    ok,
    status,
    json: async () => response,
  } as Response);
}

function mockFetchError(status: number, detail: string) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
    ok: false,
    status,
    json: async () => ({ detail }),
  } as Response);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("routerApi — happy path", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetchRoutingRules returns array", async () => {
    mockFetch([{ role: "Planner", name: "Test Rule" }]);
    const rules = await fetchRoutingRules();
    expect(Array.isArray(rules)).toBe(true);
    expect(rules[0].role).toBe("Planner");
  });

  it("fetchRoutingStats returns stats object", async () => {
    mockFetch({ total_routes: 5, active_rules: 3 });
    const stats = await fetchRoutingStats();
    expect(stats).toHaveProperty("total_routes");
  });

  it("fetchTrafficDistribution returns distribution", async () => {
    mockFetch({ totalRequests: 10, distribution: [] });
    const data = await fetchTrafficDistribution();
    expect(data).toHaveProperty("distribution");
  });

  it("fetchRoutingGraph returns graph shape", async () => {
    mockFetch({ roles: ["Planner"], models: ["gpt-4"], links: [] });
    const graph = await fetchRoutingGraph();
    expect(graph).toHaveProperty("roles");
    expect(graph).toHaveProperty("links");
  });

  it("createRoutingRule resolves without error on 201", async () => {
    mockFetch({ status: "success" }, 201);
    await expect(
      createRoutingRule({ role: "Planner", name: "My Rule" })
    ).resolves.not.toThrow();
  });

  it("deleteRoutingRule resolves without error on 200", async () => {
    mockFetch({ status: "success" });
    await expect(deleteRoutingRule("Planner")).resolves.not.toThrow();
  });

  it("simulateRoute returns simulation result", async () => {
    mockFetch({
      decision: "Primary Model",
      selectedModel: "gpt-4",
      flowSteps: ["User Request", "Router Decision", "Primary Model"],
    });
    const result = await simulateRoute("Planner", "explain something");
    expect(result.decision).toBe("Primary Model");
  });

  it("testRoute returns success response", async () => {
    mockFetch({ success: true, latencyMs: 200 });
    const result = await testRoute("Planner");
    expect(result.success).toBe(true);
  });
});

describe("routerApi — error handling", () => {
  afterEach(() => vi.restoreAllMocks());

  it("throws RouterApiError with correct status on HTTP 404", async () => {
    mockFetchError(404, "Rule not found");
    await expect(fetchRoutingRules()).rejects.toThrow(RouterApiError);
    try {
      mockFetchError(404, "Rule not found");
      await fetchRoutingRules();
    } catch (e) {
      expect(e).toBeInstanceOf(RouterApiError);
      expect((e as RouterApiError).status).toBe(404);
      expect((e as RouterApiError).message).toContain("Rule not found");
    }
  });

  it("throws RouterApiError with correct status on HTTP 500", async () => {
    mockFetchError(500, "Internal server error");
    await expect(fetchRoutingStats()).rejects.toThrow(RouterApiError);
  });

  it("throws TypeError on network failure (not RouterApiError)", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(
      new TypeError("Failed to fetch")
    );
    await expect(fetchRoutingGraph()).rejects.toThrow(TypeError);
  });
});

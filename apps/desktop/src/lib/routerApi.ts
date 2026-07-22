/**
 * routerApi.ts — Phase 6 centralized API client for the Router Console.
 *
 * All fetch calls related to the router are consolidated here to:
 *   - Avoid scattered fetch logic in Router.tsx
 *   - Provide typed error handling
 *   - Make unit testing straightforward
 *   - Prevent hardcoded path sprawl
 */

// ---------------------------------------------------------------------------
// Base URL — configurable via environment variables
// ---------------------------------------------------------------------------
const API_BASE = (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_BASE) || "";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

export class RouterApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "RouterApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // ignore parse errors — keep status message
    }
    throw new RouterApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types (mirrors backend DTOs)
// ---------------------------------------------------------------------------

export interface RoutingRuleRaw {
  role: string;
  name: string;
  description?: string;
  status: string;
  primary?: string;
  fallback?: string;
  finalFallbackModel?: string;
  tags?: string[];
  primaryUsage?: number;
  fallbackUsage?: number;
  successRate?: number;
  avgLatency?: string;
  sparkPoints?: string;
  health?: Array<{ name: string; latency: string; status: string }>;
  activity?: string[];
  // legacy raw fields from backend
  primary_model_id?: string;
  fallback_model_id?: string;
  final_fallback_model_id?: string;
  stats?: {
    primary_ratio?: number;
    fallback_ratio?: number;
    success_rate?: number;
    avg_latency_ms?: number;
  };
  recent_logs?: Array<{ message: string; timestamp: string }>;
}

export interface RouterStatsRaw {
  total_routes?: number;
  active_rules?: number;
  fallback_chains?: number;
  avg_latency_ms?: number;
  success_rate?: number;
  traffic_balance?: number;
  // new structured format
  totalRoutes?: { value: number };
  activeRules?: { value: number };
  fallbackChains?: { value: number };
  avgLatency?: { value: string };
  successRate?: { value: string };
  trafficBalance?: { value: string };
}

export interface TrafficItem {
  modelId: string;
  name: string;
  count: number;
  percentage: number;
}

export interface TrafficData {
  totalRequests: number;
  distribution: TrafficItem[];
}

export interface GraphData {
  roles: string[];
  models: string[];
  links: Array<{ source: string; target: string; type: string }>;
}

export interface ModelItem {
  id: string;
  display_name?: string;
  model_id?: string;
  provider_id?: string;
  type?: string;
}

export interface SimulationResult {
  decision?: string;
  selectedModel?: string;
  fallbackNeeded?: boolean;
  confidence?: number;
  estimatedCost?: number;
  etaSeconds?: number;
  flowSteps?: string[];
  error?: string;
}

export interface RouteTestResult {
  success: boolean;
  selectedModel?: string;
  latencyMs?: number;
  tier?: string;
  error?: string;
}

export interface RuntimeSummary {
  request_count_by_agent: Record<string, number>;
  request_count_by_model: Record<string, number>;
  avg_latency_ms: number;
  error_rate: number;
  fallback_count: number;
  quota_usage: Record<string, unknown>;
  last_executions: unknown[];
  degraded_providers: string[];
}

export interface CreateRulePayload {
  role: string;
  name: string;
  description?: string;
  primary_model_id?: string | null;
  fallback_model_id?: string | null;
  final_fallback_model_id?: string | null;
  status?: string;
}

export interface PatchRulePayload extends Partial<CreateRulePayload> {
  tags?: string[];
  policy?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Fetch all routing rules. */
export async function fetchRoutingRules(): Promise<RoutingRuleRaw[]> {
  return apiFetch<RoutingRuleRaw[]>("/api/models/routing/rules");
}

/** Fetch routing stats. */
export async function fetchRoutingStats(): Promise<RouterStatsRaw> {
  return apiFetch<RouterStatsRaw>("/api/models/routing/stats");
}

/** Fetch traffic distribution data. */
export async function fetchTrafficDistribution(timeframeHours = 24): Promise<TrafficData> {
  return apiFetch<TrafficData>(`/api/models/routing/traffic?timeframe_hours=${timeframeHours}`);
}

/** Fetch routing graph. */
export async function fetchRoutingGraph(): Promise<GraphData> {
  return apiFetch<GraphData>("/api/models/routing/graph");
}

/** Fetch available models. */
export async function fetchModels(): Promise<ModelItem[]> {
  return apiFetch<ModelItem[]>("/api/v1/models");
}

/** Fetch router runtime summary (Phase 6 observability). */
export async function fetchRuntimeSummary(): Promise<RuntimeSummary> {
  return apiFetch<RuntimeSummary>("/api/router/runtime/summary");
}

/** Fetch last N execution logs (Phase 6 observability). */
export async function fetchExecutionLogs(limit = 50): Promise<unknown[]> {
  return apiFetch<unknown[]>(`/api/router/runtime/executions?limit=${limit}`);
}

/** Fetch provider health status. */
export async function fetchProviderHealth(): Promise<unknown[]> {
  return apiFetch<unknown[]>("/api/router/runtime/providers/health");
}

/** Create a new routing rule. */
export async function createRoutingRule(payload: CreateRulePayload): Promise<void> {
  await apiFetch<unknown>("/api/models/routing/rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** Update (patch) an existing routing rule. */
export async function patchRoutingRule(role: string, payload: PatchRulePayload): Promise<void> {
  await apiFetch<unknown>(`/api/models/routing/rules/${encodeURIComponent(role)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** Delete a routing rule. */
export async function deleteRoutingRule(role: string): Promise<void> {
  await apiFetch<unknown>(`/api/models/routing/rules/${encodeURIComponent(role)}`, {
    method: "DELETE",
  });
}

/** Test a specific route. */
export async function testRoute(role: string, prompt = "Quick diagnostic probe."): Promise<RouteTestResult> {
  return apiFetch<RouteTestResult>(`/api/models/routing/rules/${encodeURIComponent(role)}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
}

/** Run a route simulation. */
export async function simulateRoute(role: string, prompt: string): Promise<SimulationResult> {
  return apiFetch<SimulationResult>("/api/models/routing/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, prompt }),
  });
}

/**
 * Canonical Routing API Contracts (Phase 12).
 */

export interface RoutingRuleResource {
  id: string;
  name: string;
  version: number;
  enabled: boolean;
  priority: number;
  canonical_model_id: string;
  fallback_model_id?: string;
  final_fallback_model_id?: string;
  description: string;
  task_labels: string[];
  agent_types: string[];
  workflow_types: string[];
  required_capabilities: string[];
  min_context_tokens: number;
  requires_tools: boolean;
  requires_vision: boolean;
  cost_classes: string[];
  requires_local: boolean;
  requires_private: boolean;
  user_preference_model?: string;
  primary_usage: number;
  fallback_usage: number;
  success_rate: number;
  avg_latency_ms: number;
  created_at: string;
  updated_at: string;
}

export interface RoutingGraphNode {
  id: string;
  label: string;
  type: 'role' | 'rule' | 'model' | 'provider';
}

export interface RoutingGraphLink {
  source: string;
  target: string;
  label?: string;
  weight?: number;
}

export interface RoutingGraphData {
  nodes: RoutingGraphNode[];
  links: RoutingGraphLink[];
}

export interface TrafficDistributionItem {
  model_id: string;
  model_name: string;
  provider: string;
  percentage: number;
  request_count: number;
}

export interface RoutingMetricsData {
  total_routes: number;
  active_rules: number;
  fallback_chains: number;
  avg_latency_ms: number;
  success_rate_percent: number;
  traffic_balance_percent: number;
  traffic_distribution: TrafficDistributionItem[];
}

export interface RouteSimulationRequest {
  role: string;
  prompt?: string;
  estimated_tokens?: number;
  required_capabilities?: string[];
  cost_class?: string;
  requires_tools?: boolean;
  requires_vision?: boolean;
  requires_local?: boolean;
  user_preference_model?: string;
}

export interface RouteDecisionResource {
  request_id: string;
  requested_role: string;
  canonical_model_id: string;
  selected_provider: string;
  selected_endpoint: string;
  rule_id: string;
  rule_name: string;
  reason: string;
  fallback_chain: string[];
  route_lock_id: string;
  evaluated_at: string;
}

export interface RouteLockDetailResource {
  lock_id: string;
  scope: string;
  scope_id: string;
  canonical_model_id: string;
  status: string;
  created_at: string;
  routing_snapshot: {
    rule_id: string;
    rule_version: number;
    canonical_model_id: string;
    selected_at: number;
    reason: string;
  };
}

/** P0.3.1 — canonical story model-routing role (server authority). */
export interface StoryRoleResource {
  role: string;
  label: string;
  capability_labels: string[];
  llm_routed: boolean;
  aliases: string[];
}

/** P0.3.6 — durable per-task route receipt written by the model router. */
export interface RouteReceiptResource {
  id: string;
  task_id: string;
  role: string;
  rule_id: string;
  route_lock_id: string;
  selected_provider?: string | null;
  selected_model_id: string;
  provider_model_id?: string | null;
  endpoint_id?: string | null;
  fallback_used: boolean;
  fallback_reason?: string | null;
  status: 'success' | 'failed';
  error_code?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

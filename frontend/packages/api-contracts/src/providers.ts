/**
 * Canonical Providers API Contracts (Phase 12).
 */

export type ProviderType =
  | 'anthropic'
  | 'openai'
  | 'google'
  | 'mistral'
  | 'ollama'
  | 'openrouter'
  | 'cloud'
  | 'local'
  | 'custom';

export type ProviderStatus = 'healthy' | 'degraded' | 'offline' | 'unconfigured';

export interface ProviderEndpointResource {
  id: string;
  provider_id: string;
  name: string;
  base_url: string;
  status: ProviderStatus;
  latency_ms: number;
  rate_limit_rpm: number;
  rate_limit_tpm: number;
  credential_reference: string;
  is_configured: boolean;
  credential_label?: string | null;
  credential_updated_at?: string | null;
  models_count: number;
  last_checked_at: string;
}

export interface ProviderResource {
  id: string;
  display_name: string;
  type: ProviderType;
  status: ProviderStatus;
  enabled?: boolean;
  capabilities: string[];
  website_url?: string;
  endpoints: ProviderEndpointResource[];
  models_count: number;
  has_credentials: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderConnectionTestReceipt {
  test_id: string;
  provider_id: string;
  endpoint_id: string;
  started_at: string;
}

export interface ProviderConnectionTestResult {
  test_id: string;
  provider_id: string;
  endpoint_id: string;
  reachable: boolean;
  latency_ms: number;
  auth_valid: boolean;
  model_discovery: string[];
  error_code?: string;
  message: string;
  completed_at: string;
}

export interface ProviderHealthMap {
  [provider_id: string]: {
    status: ProviderStatus;
    avg_latency_ms: number;
    endpoints_healthy: number;
    endpoints_total: number;
  };
}

export interface AddProviderRequest {
  id: string;
  name: string;
  type: 'cloud' | 'local' | 'custom';
  base_url: string;
  protocol_mode: 'openai' | 'anthropic' | 'gemini' | 'ollama';
  api_key?: string;
  credential_label?: string;
  endpoint_id?: string;
  supports_model_discovery?: boolean;
  supports_openai_compatible?: boolean;
}

export interface ProviderModelRuleResource {
  role: string;
  name: string;
  description?: string;
  primary_canonical_model_id: string;
  fallback_canonical_model_id?: string;
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface AssignProviderModelRuleRequest {
  role: string;
  name: string;
  primary_canonical_model_id: string;
  fallback_canonical_model_id?: string;
  description?: string;
  enabled?: boolean;
  priority?: number;
}

/** P0.1 — partial provider edit. Secrets are NEVER part of an update. */
export interface UpdateProviderRequest {
  name?: string;
  base_url?: string;
  protocol_mode?: 'openai' | 'anthropic' | 'gemini' | 'ollama';
  enabled?: boolean;
  supports_model_discovery?: boolean;
  supports_openai_compatible?: boolean;
}

export interface RotateCredentialRequest {
  api_key: string;
  label?: string;
}

export interface CredentialStatusResource {
  provider_id: string;
  configured: boolean;
  credential_reference: string;
  label?: string | null;
  secret_version: number;
  updated_at: string;
}

export interface RoutingRuleDependency {
  role: string;
  name: string;
  primary_canonical_model_id: string;
  fallback_canonical_model_id?: string | null;
}

export interface DeleteProviderConflict {
  message: string;
  blocking_rules: RoutingRuleDependency[];
  resolution: string;
}

export interface DeleteProviderResult {
  provider_id: string;
  deleted: boolean;
  removed_endpoints: number;
  removed_credentials: number;
  removed_bindings: number;
  disabled_rule_roles: string[];
}

/** P0.2.1/P0.2.4 — explicit Sync Models operation receipt. */
export interface SyncModelsResult {
  provider_id: string;
  endpoint_id: string;
  ok: boolean;
  added: string[];
  updated: string[];
  unchanged: string[];
  unavailable: string[];
  discovered_count: number;
  error_code?: string;
  message: string;
  completed_at: string;
}

export interface TestModelRequest {
  model_id: string;
}

/** P0.2.5 — tiny real inference receipt; carries NO quality metrics. */
export interface ModelProbeReceiptResource {
  provider_id: string;
  endpoint_id: string;
  canonical_model_id: string;
  provider_model_id: string;
  ok: boolean;
  latency_ms: number;
  finish_reason?: string | null;
  error_code?: string | null;
  message: string;
  completed_at: string;
}

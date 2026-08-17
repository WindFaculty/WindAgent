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
  models_count: number;
  last_checked_at: string;
}

export interface ProviderResource {
  id: string;
  display_name: string;
  type: ProviderType;
  status: ProviderStatus;
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

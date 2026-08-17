/**
 * Canonical Models API Contracts (Phase 12).
 */

export type ModelCapability =
  | 'chat'
  | 'code'
  | 'vision'
  | 'audio'
  | 'tools'
  | 'embedding'
  | 'reasoning';

export type ModelModality =
  | 'text->text'
  | 'text->image'
  | 'multimodal->text'
  | 'text->audio'
  | 'multimodal->multimodal';

export interface ModelEndpointBinding {
  id: string;
  endpoint_id: string;
  provider_id: string;
  provider_model_id: string;
  equivalence_level: 'exact' | 'compatible' | 'approximate' | 'fallback';
  confidence: number;
  is_active: boolean;
}

export interface ModelPricing {
  input_per_million?: number;
  output_per_million?: number;
}

export interface ModelDefinitionResource {
  id: string;
  name: string;
  vendor: string;
  family: string;
  description: string;
  context_window: number;
  max_output_tokens: number;
  capabilities: ModelCapability[];
  modalities: ModelModality[];
  is_local: boolean;
  is_active: boolean;
  pricing?: ModelPricing;
  bindings: ModelEndpointBinding[];
  benchmarks?: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface ModelFilterParams {
  provider?: string;
  capability?: string;
  modality?: string;
  is_local?: boolean;
  search?: string;
  cursor?: string;
  limit?: number;
}

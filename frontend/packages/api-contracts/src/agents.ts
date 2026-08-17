/**
 * Canonical Agent Definition, Instance, and Metric Contracts (Phase 11).
 */

import type { ResourceBase } from './resource';

export interface AgentDefinitionResource extends ResourceBase {
  name: string;
  slug?: string;
  description?: string;
  role: string;
  system_prompt?: string;
  skill_ids?: string[];
  tool_permissions?: string[];
  model_provider?: string | null;
  model_name?: string | null;
  model_policy?: Record<string, unknown>;
  tool_policy?: Record<string, unknown>;
  permission_profile?: Record<string, unknown>;
  memory_policy?: Record<string, unknown>;
  default_configuration?: Record<string, unknown>;
  version: number;
}

export type AgentInstanceStatus =
  | 'IDLE'
  | 'RUNNING'
  | 'WAITING'
  | 'BLOCKED'
  | 'FAILED'
  | 'TERMINATED'
  | 'OFFLINE';

export interface AgentInstanceResource extends ResourceBase {
  definition_id?: string;
  agent_definition_id?: string;
  conversation_id?: string;
  session_id?: string;
  status: AgentInstanceStatus | string;
  state?: AgentInstanceStatus | string;
  canonical_model_id?: string | null;
  provider_binding_id?: string | null;
  route_lock_id?: string | null;
  assigned_task_id?: string | null;
  current_tool?: string | null;
  started_at?: string | null;
  stopped_at?: string | null;
  runtime_metadata?: Record<string, unknown>;
  working_memory?: Record<string, unknown>;
  version: number;
}

export interface AgentSummaryMetrics {
  total: number;
  running: number;
  idle: number;
  offline: number;
  tasks_running: number;
}

export interface AgentActivityItem {
  id: string;
  agent_id: string;
  action_type: string;
  message: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

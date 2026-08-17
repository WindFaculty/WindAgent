/**
 * Canonical Task and Task Graph Contracts (Phase 11).
 */

import type { ResourceBase } from './resource';

export type TaskState =
  | 'PENDING'
  | 'READY'
  | 'RUNNING'
  | 'BLOCKED'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED';

export interface TaskResource extends ResourceBase {
  conversation_id: string;
  objective: string;
  state: TaskState;
  assigned_agent_instance_id?: string | null;
  parent_task_id?: string | null;
  dependencies: string[];
  concurrency_group?: string | null;
  attempts: number;
  result?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
  version: number;
}

export interface TaskGraphNode {
  node_id: string;
  position: number;
  objective: string;
  agent_type?: string | null;
  assigned_agent_instance_id?: string | null;
  state: TaskState;
  concurrency_group?: string | null;
  dependencies: string[];
  version: number;
}

export interface TaskGraphEdge {
  edge_id: string;
  from_node_id: string;
  to_node_id: string;
}

export interface TaskGraphResource {
  conversation_id: string;
  parent_task_id?: string;
  objective?: string;
  version: number;
  nodes: TaskGraphNode[];
  edges: TaskGraphEdge[];
}

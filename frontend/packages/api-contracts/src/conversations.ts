/**
 * Canonical Conversation Contracts (Phase 11).
 */

import type { ResourceBase } from './resource';
import type { AgentInstanceResource } from './agents';
import type { TaskResource } from './tasks';

export interface ConversationResource extends ResourceBase {
  title?: string;
  objective?: string;
  status: 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'CANCELLED' | string;
  plan_version_id?: string | null;
  orchestrator_instance_id?: string | null;
  version: number;
}

export interface ConversationDetailResource {
  conversation: ConversationResource;
  plan_versions: Record<string, unknown>[];
  agents: AgentInstanceResource[];
  tasks: TaskResource[];
  events: Record<string, unknown>[];
}

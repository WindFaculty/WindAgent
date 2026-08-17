/**
 * Canonical Workflow and Workflow Run Contracts (Phase 11).
 */

import type { ResourceBase } from './resource';

export interface WorkflowStepDefinition {
  id: string;
  name: string;
  description?: string;
  tool_name?: string;
  timeout_seconds?: number;
}

export interface WorkflowDefinitionResource extends ResourceBase {
  name: string;
  description?: string;
  type?: string;
  trigger?: string;
  owner?: string;
  tags: string[];
  steps: WorkflowStepDefinition[];
  acceptance_criteria: string[];
  version: number;
}

export type WorkflowStepRunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'SKIPPED';

export interface WorkflowStepRunResource extends ResourceBase {
  run_id: string;
  step_id: string;
  step_name: string;
  status: WorkflowStepRunStatus;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  attempts: number;
}

export type WorkflowRunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'PAUSED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface WorkflowRunResource extends ResourceBase {
  workflow_id: string;
  workflow_name: string;
  status: WorkflowRunStatus;
  triggered_by?: string;
  steps: WorkflowStepRunResource[];
  progress_percent: number;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  version: number;
}

export type ProjectStatus = 'idle' | 'loading' | 'ready' | 'error';
export type RevisionStatus = 'draft' | 'committed' | 'locked' | 'DRAFT' | 'COMMITTED' | 'LOCKED';
export type SyncStatus = 'synced' | 'unsaved' | 'syncing' | 'conflict' | 'reconnecting' | 'stale' | 'offline';
export type BackendStatus = 'online' | 'offline' | 'degraded';
export type ProductionPage = 'script' | 'assets' | 'video';

export interface ProductionProject {
  id: string;
  name: string;
  description?: string;
  status?: string;
  active_revision_id?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface ProductionRevision {
  id: string;
  projectId: string;
  sequenceNumber: number;
  status: RevisionStatus;
  createdAt: string;
}

export interface ProductionRoute {
  projectId: string;
  page: ProductionPage;
  entityId?: string;
  revisionId?: string;
  sceneId?: string;
  entityType?: 'CHARACTER' | 'LOCATION' | 'PROP' | 'SCENE' | 'SHOT';
  assetId?: string;
  requirementId?: string;
  resolutionAction?: 'search_library' | 'search_internet' | 'generate' | 'upload';
}

export interface SelectedEntity {
  entityId: string;
  entityType: 'CHARACTER' | 'LOCATION' | 'PROP' | 'SCENE' | 'SHOT';
}

export interface ProductionAssetBindingDTO {
  binding_id: string;
  project_id: string;
  production_revision_id: string;
  screenplay_entity_type: 'CHARACTER' | 'LOCATION' | 'PROP' | 'SCENE' | 'SHOT';
  screenplay_entity_id: string;
  role_key: string;
  asset_id: string;
  asset_revision_id: string;
  status: 'ACTIVE' | 'UNBOUND' | 'SUPERSEDED' | 'INVALID';
  created_by: string;
  created_at: string;
  supersedes_binding_id?: string;
  unbound_at?: string;
}

export interface AssetEligibilityResultDTO {
  is_eligible: boolean;
  asset_id: string;
  asset_revision_id: string;
  entity_type: string;
  entity_id: string;
  blocking_reasons: string[];
  warning_reasons: string[];
}

export interface SelectedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  path?: string;
  fileObject?: File;
}

export interface AssetRequirementDTO {
  requirement_id: string;
  project_id: string;
  revision_id: string;
  screenplay_entity_id: string;
  screenplay_entity_type: 'CHARACTER' | 'LOCATION' | 'PROP' | 'SCENE' | 'SHOT';
  role_key: string;
  required_kind: string;
  required_media: string;
  description?: string;
  severity?: 'BLOCKING' | 'WARNING' | 'INFO';
  status?: 'OPEN' | 'ACTIVE' | 'FULFILLED' | 'RESOLVING' | 'STALE';
  candidate_asset_ids?: string[];
}

export type WorkspaceCommandType =
  | 'UPDATE_SCENE'
  | 'ADD_SHOT'
  | 'UPDATE_ASSET'
  | 'APPROVE_CANDIDATE'
  | 'REJECT_CANDIDATE'
  | 'OVERRIDE_CANDIDATE'
  | 'AUTHORIZE_COST'
  | 'HUMAN_TAKEOVER'
  | 'CANCEL_JOB'
  | 'PUBLISH_DELIVERABLE'
  | 'BIND_ASSET'
  | 'UNBIND_ASSET'
  | 'RESOLVE_REQUIREMENT';

export type WorkspaceCommandStatus =
  | 'COMPLETED'
  | 'REJECTED_STALE'
  | 'REJECTED_LOCKED'
  | 'IDEMPOTENCY_MISMATCH'
  | 'FAILED';

export interface WorkspaceCommandRequest {
  command_type: WorkspaceCommandType;
  project_id: string;
  target_revision_id: string;
  entity_id: string;
  reason?: string;
  payload?: Record<string, unknown>;
  client_context?: Record<string, unknown>;
}

export interface WorkspaceCommandResult {
  command_id: string;
  status: WorkspaceCommandStatus;
  updated_revision_id: string;
  message: string;
  current_sequence?: number;
  payload?: Record<string, unknown>;
}

export interface WorkspaceSnapshot {
  project_id: string;
  revision_id: string;
  project_status: string;
  revision_status?: string;
  creative_brief_locked: boolean;
  screenplay_locked: boolean;
  total_shots: number;
  candidates_count: number;
  cost_summary?: Record<string, unknown>;
  human_takeover_state?: Record<string, unknown> | null;
  current_sequence: number;
  authorized_media_urls?: Record<string, string>;
  screenplay?: Record<string, unknown>;
  asset_summary?: Record<string, unknown>;
  pipeline_summary?: Record<string, unknown>;
}

export interface ProductionEventEnvelope {
  event_id: string;
  sequence: number;
  event_type: string;
  project_id: string;
  revision_id?: string;
  aggregate_type?: string;
  aggregate_id?: string;
  payload: Record<string, unknown>;
  occurred_at?: string;
}

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  target_revision_id?: string;
  current_revision_id?: string;
  current_sequence?: number;
}

export type ProposalStatus =
  | 'PENDING'
  | 'REQUIRES_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'SUPERSEDED'
  | 'EXPIRED'
  | 'APPLY_FAILED';

export type ProposalType =
  | 'SCREENPLAY_CHANGE'
  | 'ASSET_BINDING_CHANGE'
  | 'LICENSE_CHANGE'
  | 'ASSET_APPROVAL_CHANGE';

export interface ProductionChangeProposal {
  proposal_id: string;
  proposal_type: ProposalType;
  project_id: string;
  target_revision_id: string;
  base_sequence: number;
  affected_entities: string[];
  candidate: Record<string, unknown>;
  diff?: Record<string, unknown>;
  impact?: Record<string, unknown>;
  created_by_agent: string;
  created_at: string;
  status: ProposalStatus;
  decision_by?: string;
  decision_at?: string;
  decision_reason?: string;
  resulting_command_id?: string;
  resulting_revision_id?: string;
  version: number;
  hash: string;
}

export type ActivityCategory =
  | 'SCRIPT'
  | 'ASSET'
  | 'BINDING'
  | 'JOB'
  | 'PROPOSAL'
  | 'VALIDATION'
  | 'SYSTEM';

export type ActivityStatus = 'SUCCESS' | 'FAILED' | 'PENDING' | 'WARNING';

export interface EntityLinkDTO {
  entity_id: string;
  entity_type: string;
  display_name: string;
}

export interface ProductionActivity {
  activity_id: string;
  project_id: string;
  revision_id: string;
  category: ActivityCategory;
  actor: string;
  title: string;
  summary: string;
  entity_links: EntityLinkDTO[];
  status: ActivityStatus;
  occurred_at: string;
  source_event_ids: string[];
  correlation_id: string;
}

export type RecoveryStatus =
  | 'IDLE'
  | 'SAVING'
  | 'RECOVERED'
  | 'STALE_DRAFT_DETECTED'
  | 'CORRUPT_CLEARED'
  | 'OFFLINE_READ_ONLY'
  | 'CONFLICT';

export interface ProductionRecoverySnapshot {
  schema_version: string;
  saved_at: string;
  expires_at?: string;
  project_id: string;
  route: string;
  revision_id: string;
  base_sequence: number;
  selected_scene_id?: string;
  selected_asset_id?: string;
  editor_mode: string;
  draft_kind: string;
  edit_units: Record<string, unknown>;
  last_acknowledged_command?: string;
  checksum: string;
}

export type ConflictClassification =
  | 'NO_CONFLICT'
  | 'LOCAL_ONLY_CHANGE'
  | 'REMOTE_ONLY_CHANGE'
  | 'NON_OVERLAPPING_MERGEABLE'
  | 'OVERLAPPING_REQUIRES_REVIEW'
  | 'ENTITY_DELETED'
  | 'ORDER_CONFLICT'
  | 'UNSUPPORTED_UNKNOWN';

export type ResolutionStrategy = 'ACCEPT_LOCAL' | 'ACCEPT_REMOTE' | 'MERGE_CANDIDATE' | 'CUSTOM';

export interface FieldConflictDTO {
  field_name: string;
  base_value: unknown;
  local_value: unknown;
  remote_value: unknown;
  is_overlapping: boolean;
  merged_value?: unknown;
}

export interface EntityConflictDTO {
  entity_type: string;
  entity_id: string;
  classification: ConflictClassification;
  title: string;
  field_conflicts: FieldConflictDTO[];
}

export interface ThreeWayDiffResultDTO {
  project_id: string;
  base_revision_id: string;
  latest_revision_id: string;
  overall_classification: ConflictClassification;
  can_auto_merge: boolean;
  entity_conflicts: EntityConflictDTO[];
  auto_merged_payload?: Record<string, unknown>;
}

export interface ConflictResolutionPayloadDTO {
  project_id: string;
  base_revision_id: string;
  latest_revision_id: string;
  strategy: ResolutionStrategy;
  custom_screenplay_payload?: Record<string, unknown>;
  resolved_by?: string;
}


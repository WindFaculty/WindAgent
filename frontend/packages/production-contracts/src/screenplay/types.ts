/**
 * Screenplay Workspace Domain Contracts & Types (Stage C — UI8 to UI18).
 */

export interface DialogueReadDTO {
  dialogue_id: string;
  scene_id: string;
  character_id: string;
  character_name: string;
  order: number;
  text: string;
  delivery?: string;
}

export interface SceneReadDTO {
  scene_id: string;
  order: number;
  title: string;
  location_id: string;
  location_name: string;
  character_ids: string[];
  action_description: string;
  time_of_day: string;
  dialogue_lines: DialogueReadDTO[];
  estimated_duration_seconds: number;
}

export interface CharacterSummaryDTO {
  character_id: string;
  name: string;
  role: string;
  dialogue_count: number;
}

export interface LocationSummaryDTO {
  location_id: string;
  name: string;
  setting_type: string;
  scene_count: number;
}

export interface ValidationSummaryDTO {
  total_issues: number;
  blocking_count: number;
  warning_count: number;
  info_count: number;
  is_lockable: boolean;
}

export interface DownstreamBindingDTO {
  scene_id: string;
  bound_shot_ids: string[];
  bound_audio_track_ids: string[];
  bound_asset_ids: string[];
}

export interface ScreenplayReadModelDTO {
  screenplay_id: string;
  project_id: string;
  revision_id: string;
  parent_revision_id?: string | null;
  title: string;
  logline: string;
  status: 'DRAFT' | 'LOCKED';
  is_locked: boolean;
  current_sequence: number;
  scenes: SceneReadDTO[];
  characters: CharacterSummaryDTO[];
  locations: LocationSummaryDTO[];
  validation: ValidationSummaryDTO;
  estimated_duration_seconds: number;
  downstream_bindings: DownstreamBindingDTO[];
}

// Local Edit Unit Buffer & Machine Types (UI10 & UI13)
export interface EditUnit {
  unit_id: string;
  timestamp: number;
  target_type: 'SCREENPLAY' | 'SCENE' | 'DIALOGUE';
  entity_id: string;
  field_name: string;
  old_value: unknown;
  new_value: unknown;
}

export type DraftSaveStatus = 'SERVER' | 'LOCAL_MODIFIED' | 'SAVING' | 'SAVED' | 'CONFLICT' | 'FAILED';

export interface FieldChangeDTO {
  field_name: string;
  old_value: unknown;
  new_value: unknown;
}

export interface EntityDiffSummaryDTO {
  entity_type: 'SCREENPLAY' | 'SCENE' | 'DIALOGUE' | 'CHARACTER' | 'LOCATION';
  entity_id: string;
  change_type: 'ADDED' | 'DELETED' | 'MODIFIED' | 'MOVED' | 'UNCHANGED';
  title: string;
  changes: FieldChangeDTO[];
}

export interface ScreenplayDiffResultDTO {
  base_revision_id: string;
  target_revision_id: string;
  has_changes: boolean;
  total_added: number;
  total_deleted: number;
  total_modified: number;
  total_moved: number;
  entity_diffs: EntityDiffSummaryDTO[];
}

export interface ScreenplayChangeImpactDTO {
  project_id: string;
  base_revision_id: string;
  target_revision_id: string;
  invalidation_intent: 'EXACT' | 'CONSERVATIVE' | 'UNKNOWN';
  changed_scenes: string[];
  changed_dialogue: string[];
  changed_characters: string[];
  changed_locations: string[];
  affected_shots: string[];
  affected_audio: string[];
  affected_animation: string[];
  affected_assets: string[];
  affected_renders: string[];
  is_high_impact: boolean;
  warning_message: string;
}

export interface ScriptRevisionProposalDTO {
  proposal_id: string;
  project_id: string;
  target_revision_id: string;
  action_type: 'REWRITE' | 'SHORTEN' | 'EXPAND' | 'CHANGE_TONE' | 'POLISH_DIALOGUE';
  instruction: string;
  target_scene_id?: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  candidate_screenplay: Record<string, unknown>;
  diff_result: ScreenplayDiffResultDTO;
  change_impact: ScreenplayChangeImpactDTO;
}

export interface ValidationIssueDTO {
  code: string;
  severity: 'BLOCKING' | 'WARNING' | 'INFO';
  entity_type: 'SCENE' | 'DIALOGUE' | 'CHARACTER' | 'LOCATION' | 'SCREENPLAY';
  entity_id: string;
  message: string;
  remediation_hint: string;
}

export interface AssetRequirementDTO {
  requirement_id: string;
  asset_type: 'CHARACTER' | 'LOCATION' | 'PROP';
  ref_id: string;
  display_name: string;
  required_in_scenes: string[];
}

export interface ScreenplayValidationReportDTO {
  project_id: string;
  revision_id: string;
  is_lockable: boolean;
  total_issues: number;
  blocking_count: number;
  warning_count: number;
  info_count: number;
  issues: ValidationIssueDTO[];
  asset_requirements: AssetRequirementDTO[];
}

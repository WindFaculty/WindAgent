/**
 * Canonical Project and Episode Domain Contracts.
 */

import type { ResourceBase } from './resource';

export interface ProjectResource extends ResourceBase {
  name: string;
  description?: string | null;
  current_revision_id?: string | null;
  status?: 'ACTIVE' | 'ARCHIVED' | 'DRAFT' | string;
  episodes_count?: number;
  metadata?: Record<string, unknown>;
}

export interface EpisodeResource extends ResourceBase {
  project_id: string;
  episode_number: number;
  title: string;
  state?: 'DRAFT' | 'IDEA' | 'STORY_BIBLE' | 'OUTLINE' | 'SCREENPLAY' | 'REVIEW' | 'LOCKED' | 'READY_FOR_PRODUCTION' | string;
  current_checkpoint?: 'IDEA' | 'STORY_BIBLE' | 'OUTLINE' | 'SCREENPLAY' | 'REVIEW' | 'LOCKED' | string;
  current_revision_id?: string | null;
  progress_percent?: number;
  description?: string | null;
  status?: 'DRAFT' | 'IN_PROGRESS' | 'COMPLETED' | string;
}

export type EpisodeDetail = EpisodeResource;

export interface EpisodeArtifactEnvelope {
  artifact_id: string;
  episode_id: string;
  kind: 'IdeaCandidateSet' | 'StoryBible' | 'EpisodeOutline' | 'ScreenplayDraft' | 'SceneBeats' | string;
  revision_id: string;
  content: Record<string, any>;
  created_at: string;
}

export interface PipelineRun {
  run_id: string;
  episode_id: string;
  checkpoint: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | string;
  progress_percent: number;
  started_at: string;
  completed_at?: string | null;
  error_message?: string | null;
}

export interface CharacterIdentity {
  name: string;
  role: string;
  biography: string;
}

export interface CharacterPsychology {
  dominant_trait: string;
  flaw: string;
  alignment_score: number;
}

export interface CharacterVisualProfile {
  avatar_url?: string | null;
  banner_url?: string | null;
  physical_description: string;
  style_notes: string;
}

export interface CharacterVoiceProfile {
  voice_model_id?: string | null;
  voice_style: string;
  sample_lines: string[];
}

export interface CharacterRelationship {
  target_character_id: string;
  target_name: string;
  relationship_type: string;
}

export interface CharacterResource extends ResourceBase {
  project_id: string;
  identity: CharacterIdentity;
  psychology: CharacterPsychology;
  visual_profile: CharacterVisualProfile;
  voice_profile: CharacterVoiceProfile;
  relationships: CharacterRelationship[];
}

// ─── World Bible ────────────────────────────────────────────────────────────

export interface WorldBibleResource {
  project_id: string;
  world_name: string;
  setting_summary: string;
  core_theme: string;
  rules: string[];
  timeline_era: string;
  version: number;
  locations_count: number;
  factions_count: number;
  lore_count: number;
  updated_at: string;
}

export interface LocationResource extends ResourceBase {
  project_id: string;
  name: string;
  type: string;
  description: string;
  atmosphere: string;
}

export interface FactionResource extends ResourceBase {
  project_id: string;
  name: string;
  ideology: string;
  influence_level: number;
  description: string;
}

export interface LoreEntryResource extends ResourceBase {
  project_id: string;
  title: string;
  category: string;
  content: string;
}

// ─── Storyboard ─────────────────────────────────────────────────────────────

export interface SceneResource extends ResourceBase {
  storyboard_id: string;
  episode_id: string;
  scene_number: number;
  title: string;
  status: 'DRAFT' | 'GENERATING' | 'CONCEPT_READY' | 'LOCKED' | string;
  script_text: string;
  duration_seconds: number;
  location: string;
  character_ids: string[];
  concept_image_url?: string | null;
  source_screenplay_revision_id?: string | null;
}

export interface StoryboardResource extends ResourceBase {
  episode_id: string;
  source_screenplay_revision_id: string;
  status: 'DRAFT' | 'SYNCED' | 'LOCKED' | string;
  scenes_count: number;
}

export interface GenerationJobResource {
  generation_id: string;
  scene_id: string;
  episode_id: string;
  status: 'QUEUED' | 'STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | string;
  progress_percent: number;
  submitted_at: string;
  completed_at?: string | null;
  result_asset_url?: string | null;
  error_message?: string | null;
}

// ─── Reviews ────────────────────────────────────────────────────────────────

export type ReviewSubjectType = 'storyboard' | 'character_revision' | 'asset_revision' | 'production_preview' | 'screenplay';
export type ReviewDecisionKind = 'APPROVED' | 'REVISION_NEEDED' | 'REJECTED';

export interface ReviewCommentResource extends ResourceBase {
  review_id: string;
  author: string;
  role: string;
  text: string;
  timestamp: string;
}

export interface ReviewDecisionResource {
  id: string;
  review_id: string;
  decision: ReviewDecisionKind;
  revision_id: string;
  expected_version: number;
  reason: string;
  decided_by: string;
  decided_at: string;
}

export interface ReviewResource extends ResourceBase {
  subject_type: ReviewSubjectType;
  subject_id: string;
  episode_id?: string | null;
  project_id?: string | null;
  status: 'PENDING' | 'APPROVED' | 'REVISION_NEEDED' | 'REJECTED' | string;
  comments_count: number;
  decision?: ReviewDecisionResource | null;
}

// ─── Assets ─────────────────────────────────────────────────────────────────

export interface AssetProvenance {
  source: 'GENERATED' | 'UPLOADED' | 'IMPORTED' | string;
  generator?: string | null;
  model?: string | null;
  prompt?: string | null;
  reference_ids: string[];
  job_id?: string | null;
  content_hash: string;
  parent_revision_id?: string | null;
  created_at: string;
}

export interface AssetRevisionResource {
  revision_id: string;
  asset_id: string;
  version: number;
  status: 'DRAFT' | 'APPROVED' | 'REJECTED' | string;
  media_url?: string | null;
  provenance: AssetProvenance;
  created_at: string;
}

export type AssetType = 'IMAGE' | 'AUDIO' | 'VIDEO' | 'MODEL_3D' | 'REFERENCE';

export interface AssetResource extends ResourceBase {
  name: string;
  type: AssetType;
  episode_id?: string | null;
  project_id?: string | null;
  scene_id?: string | null;
  character_id?: string | null;
  current_revision_id?: string | null;
  status: 'DRAFT' | 'APPROVED' | 'REJECTED' | string;
  provenance: AssetProvenance;
}

// ─── Project Template ────────────────────────────────────────────────────────

export interface ProjectTemplate {
  id: string;
  title: string;
  description: string;
  genre: string;
  initial_episode: string;
  episode_brief: string;
  accent_color: string;
}

// ─── Phase 10 — Production Cutover ──────────────────────────────────────────

export type ProductionPlanStatus = 'PLANNING' | 'ACTIVE' | 'READY_FOR_RENDER' | 'COMPLETED' | 'BLOCKED' | string;
export type ShotStatus = 'DRAFT' | 'AUDIO_PENDING' | 'ANIMATION_PENDING' | 'RENDER_PENDING' | 'RENDERED' | 'FAILED' | string;
export type JobStage = 'AUDIO' | 'ANIMATION' | 'RENDER' | 'VIDEO';
export type JobState = 'PENDING' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'BLOCKED';

export interface ProductionPlanResource extends ResourceBase {
  episode_id: string;
  project_id?: string | null;
  screenplay_revision_id: string;
  storyboard_revision_id: string;
  character_references: string[];
  asset_references: string[];
  status: ProductionPlanStatus;
  progress_percent: number;
  shots_count: number;
}

export interface ShotResource extends ResourceBase {
  episode_id: string;
  production_plan_id: string;
  scene_id?: string | null;
  shot_number: number;
  camera_movement: string;
  focal_length: string;
  status: ShotStatus;
  duration_seconds: number;
  audio_asset_id?: string | null;
  animation_asset_id?: string | null;
  render_asset_id?: string | null;
}

export interface ProductionJobResource {
  job_id: string;
  episode_id: string;
  shot_id?: string | null;
  job_type: JobStage;
  state: JobState;
  progress_percent: number;
  error_code?: string | null;
  retryable: boolean;
  failure_stage?: string | null;
  attempt: number;
  max_attempts: number;
  artifact_id?: string | null;
  correlation_id?: string | null;
  submitted_at: string;
  completed_at?: string | null;
}

export interface JobSubmissionReceipt {
  job_id: string;
  state: JobState;
  submitted_at: string;
  correlation_id?: string | null;
}

export interface DeliveryArtifactResource {
  id: string;
  episode_id: string;
  video_asset_id?: string | null;
  resolution: string;
  codec: string;
  duration_seconds: number;
  file_size_bytes: number;
  download_url?: string | null;
  manifest_url?: string | null;
  created_at: string;
}

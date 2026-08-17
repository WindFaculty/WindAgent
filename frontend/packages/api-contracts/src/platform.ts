/**
 * Phase 13 — Platform & Administration Contracts.
 * Browser Runtime Console / Workspace Files / Memory / Logs / Settings.
 */

// ─── 13A — Browser Runtime Console ─────────────────────────────────────────

export interface BrowserSessionResource {
  id: string;
  url: string;
  title: string;
  loading: boolean;
  screenshot_url: string | null;
  controlled_by: string; // "agent" | "user"
  extracted_chars: number;
  error: string | null;
  authenticated: boolean;
  profile: string | null;
  created_at: string;
}

export interface CreateBrowserSessionRequest {
  authenticated?: boolean;
  profile?: string | null;
}

export interface BrowserActionResponse {
  session_id: string;
  url: string;
  title: string;
  loading: boolean;
  screenshot_url: string | null;
  extracted_chars: number;
  error: string | null;
  event: string;
  timestamp: string;
}

export interface BrowserNavigateRequest {
  url: string;
}

export interface BrowserClickRequest {
  x: number;
  y: number;
}

export interface BrowserTypeRequest {
  selector: string;
  text: string;
}

export interface BrowserScrollRequest {
  direction?: 'up' | 'down';
  pixels?: number;
}

// ─── 13B — Workspace Files ─────────────────────────────────────────────────

export interface FileResource {
  id: string;
  path: string; // workspace-relative
  name: string;
  media_type: string;
  size: number;
  checksum: string;
  created_at: string;
  modified_at: string;
  permissions: Record<string, unknown>;
}

export interface CreateFileRequest {
  path: string;
  name: string;
  media_type?: string;
  content?: string;
}

// ─── 13C — Memory ──────────────────────────────────────────────────────────

export type MemoryScope = 'conversation' | 'project' | 'agent' | 'global';
export type MemoryType = 'working' | 'short_term' | 'long_term';

export interface MemoryRecordResource {
  id: string;
  scope: MemoryScope;
  owner: string | null;
  type: MemoryType;
  content: string;
  metadata: Record<string, unknown>;
  embedding_state: 'NOT_EMBEDDED' | 'INDEXED';
  created_at: string;
  last_accessed_at: string;
  version: number;
}

export interface CreateMemoryRequest {
  scope: MemoryScope;
  owner?: string | null;
  type?: MemoryType;
  content: string;
  metadata?: Record<string, unknown>;
}

export interface MemorySearchRequest {
  scope?: MemoryScope | null;
  owner?: string | null;
  query?: string;
  limit?: number;
}

// ─── 13D — Logs ────────────────────────────────────────────────────────────

export interface LogRecord {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  source: string;
  message: string;
  correlation_id?: string | null;
  trace_id?: string | null;
  conversation_id?: string | null;
  agent_instance_id?: string | null;
  task_id?: string | null;
  metadata: Record<string, unknown>;
}

export interface LogQueryParams {
  level?: string;
  source?: string;
  correlation_id?: string;
  conversation_id?: string;
  agent_instance_id?: string;
  task_id?: string;
  limit?: number;
}

// ─── 13E — Settings ────────────────────────────────────────────────────────

export interface SettingSchemaItem {
  key: string;
  type: 'string' | 'number' | 'boolean' | 'enum' | 'secret';
  default?: unknown;
  value?: unknown; // secret values are { configured: boolean }
  requires_restart?: boolean;
  secret?: boolean;
  read_only?: boolean;
  min?: number | null;
  max?: number | null;
  enum?: string[] | null;
  description?: string;
  group: string;
}

export interface SettingsResponse {
  settings: SettingSchemaItem[];
  schema_version: number;
}

export interface SecretConfiguredStatus {
  configured: boolean;
}

export interface PatchSettingsRequest {
  values: Record<string, unknown>;
}
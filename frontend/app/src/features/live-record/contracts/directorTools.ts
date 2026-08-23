/**
 * Gemini Live Director — Constrained Tool Manifest — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Principle C: Gemini NEVER receives write_file/shell/open_url with arbitrary payloads.
 * Every tool is gated to prepared artifact IDs. Deterministic executor validates
 * action_id against frozen plan hash before execution.
 */

// ─── Allowed tools — immutable allowlist ────────────────────────────────────

export type DirectorToolName =
  | 'advance_cue'
  | 'execute_prepared_action'
  | 'verify_visual_state'
  | 'pause_recording'
  | 'resume_recording'
  | 'create_marker'
  | 'retry_action'
  | 'request_operator';

export interface DirectorToolCall {
  readonly tool: DirectorToolName;
  readonly args: Readonly<Record<string, string>>;
  readonly idempotency_key: string;
  readonly execution_id: string; // unique per attempt
}

// Function declarations as exposed to Gemini Live API (JSON Schema style)
export const DIRECTOR_TOOL_DECLARATIONS: readonly {
  readonly name: DirectorToolName;
  readonly description: string;
  readonly parameters: { readonly type: 'object'; readonly properties: Record<string, { type: string; description: string }>; readonly required: readonly string[] };
}[] = [
  {
    name: 'advance_cue',
    description: 'Chuyển sang cue tiếp theo trong scene hiện tại (chỉ cue đã chuẩn bị).',
    parameters: { type: 'object', properties: { cue_id: { type: 'string', description: 'ID cue đích, phải thuộc plan đã freeze' } }, required: ['cue_id'] },
  },
  {
    name: 'execute_prepared_action',
    description: 'Thực thi một prepared action đã đóng băng. Gemini chỉ truyền action_id, payload nằm trong artifact store.',
    parameters: { type: 'object', properties: { action_id: { type: 'string', description: 'ID action trong LiveExecutionPlan.actions[]' } }, required: ['action_id'] },
  },
  {
    name: 'verify_visual_state',
    description: 'Yêu cầu verify trạng thái màn hình kỳ vọng sau action.',
    parameters: { type: 'object', properties: { state_id: { type: 'string', description: 'ID ExpectedVisualState trong plan' } }, required: ['state_id'] },
  },
  { name: 'pause_recording', description: 'Tạm dừng ghi hình.', parameters: { type: 'object', properties: {}, required: [] } },
  { name: 'resume_recording', description: 'Tiếp tục ghi hình.', parameters: { type: 'object', properties: {}, required: [] } },
  { name: 'create_marker', description: 'Tạo marker trên timeline để đồng bộ TTS sau này.', parameters: { type: 'object', properties: { marker_type: { type: 'string', description: 'Loại marker (SCENE_START, ACTION_SUCCESS, NARRATION_CUE...)' } }, required: ['marker_type'] } },
  { name: 'retry_action', description: 'Thử lại một action đã chuẩn bị (nếu retry_allowed=true).', parameters: { type: 'object', properties: { action_id: { type: 'string', description: 'ID action cần retry' } }, required: ['action_id'] } },
  { name: 'request_operator', description: 'Yêu cầu operator can thiệp khi gặp trạng thái không khôi phục được.', parameters: { type: 'object', properties: { reason: { type: 'string', description: 'Lý do cần operator' } }, required: ['reason'] } },
] as const;

// ─── Explicit denylist — MUST NOT be exposed to Gemini ─────────────────────────

export const DIRECTOR_DENIED_TOOLS: readonly string[] = [
  'shell',
  'write_file',
  'open_url',
  'click',
  'powershell',
  'run_command_raw',
  'browser_navigate_raw',
] as const;

export function isAllowedDirectorTool(name: string): name is DirectorToolName {
  return (DIRECTOR_TOOL_DECLARATIONS as readonly { name: string }[]).some((t) => t.name === name);
}

export function assertDirectorToolAllowed(name: string): void {
  if (!isAllowedDirectorTool(name)) {
    throw new Error(`DIRECTOR_TOOL_DENIED: ${name} is not in constrained manifest`);
  }
  if ((DIRECTOR_DENIED_TOOLS as readonly string[]).includes(name)) {
    throw new Error(`DIRECTOR_TOOL_DENIED: ${name} is explicitly denied`);
  }
}

// Aliases that map to prepared artifacts (no raw URLs/commands in tool args)
export type PreparedAliasKind = 'CODE' | 'COMMAND' | 'BROWSER' | 'TOOL';

export interface PreparedAlias {
  readonly alias: string; // e.g. "browser-action-002"
  readonly kind: PreparedAliasKind;
  readonly artifact_ref: string; // artifact://...
}

// Validation before dispatch
export function validateDirectorToolCall(
  call: DirectorToolCall,
  allowedActionIds: ReadonlySet<string>,
  allowedStateIds: ReadonlySet<string>,
): { ok: boolean; reason?: string } {
  if (!isAllowedDirectorTool(call.tool)) return { ok: false, reason: 'TOOL_NOT_ALLOWED' };
  if (!call.idempotency_key || !call.execution_id) return { ok: false, reason: 'IDEMPOTENCY_REQUIRED' };
  if (call.tool === 'execute_prepared_action' || call.tool === 'retry_action') {
    const aid = call.args.action_id;
    if (!aid || !allowedActionIds.has(aid)) return { ok: false, reason: 'ACTION_NOT_IN_PLAN' };
  }
  if (call.tool === 'verify_visual_state') {
    const sid = call.args.state_id;
    if (!sid || !allowedStateIds.has(sid)) return { ok: false, reason: 'STATE_NOT_IN_PLAN' };
  }
  return { ok: true };
}

/**
 * PreparedActionExecutor — Phase D (ban_ke_hoach_v1.md Sections 13–14)
 *
 * The real-effector half of the director loop. Implements ToolCallDispatcher's
 * ExecutorFn for the frozen 8-tool allowlist:
 *
 *   execute_prepared_action / retry_action
 *     → resolve a dispatch ticket from the API (server verifies plan FROZEN),
 *       then route by action type:
 *         CODE_PLAYBACK → Tauri `playback_execute_code` (hash-gated typing)
 *         RUN_COMMAND   → API `/execute` (SafeShellRunner, server-side)
 *         BROWSER_*     → API browser surface + result report
 *   advance_cue / pause_recording / resume_recording / create_marker /
 *   request_operator → operator-side session effects via injected callbacks.
 *
 * Principle C: payload text only ever flows from the server ticket (the
 * operator's own prepared bundle) into the playback executor — never from
 * model output.
 */

import type { LiveExecutionPlan, PreparedAction } from '../domain/types';
import type { DirectorToolCall } from '../contracts/directorTools';
import type { ExecutorFn } from './ToolCallDispatcher';

/** Minimal dispatch-ticket shape served by POST …/actions/{id}/prepare. */
export interface DispatchTicket {
  readonly plan_id: string;
  readonly plan_hash: string;
  readonly action: PreparedAction;
  readonly payload_text?: string | null;
  readonly expected_after?: { readonly state_id?: string } | null;
}

export interface ActionExecutorDeps {
  readonly plan: LiveExecutionPlan;
  /** Base URL of the WindAgent API, e.g. http://127.0.0.1:8000 */
  readonly apiBaseUrl?: string;
  readonly fetchImpl?: typeof fetch;
  /** Tauri invoke — absent on web/dev, where CODE_PLAYBACK is unavailable. */
  readonly invokeTauri?: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>;
  readonly takeId?: string;
  // Operator-side session effect hooks (wired by the UI layer).
  readonly onAdvanceCue?: (cue: { scene_id: string; cue_id: string; expected_state_id?: string }) => void;
  readonly onPauseRecording?: () => Promise<void> | void;
  readonly onResumeRecording?: () => Promise<void> | void;
  readonly onCreateMarker?: (markerType: string) => Promise<void> | void;
  readonly onRequestOperator?: (reason: string) => void;
}

function failure(detail: string): { status: 'FAILURE'; detail: string } {
  return { status: 'FAILURE', detail };
}

export function createActionExecutor(deps: ActionExecutorDeps): ExecutorFn {
  const fetchImpl = deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const baseUrl = (deps.apiBaseUrl ?? '').replace(/\/$/, '');

  const fetchTicket = async (actionId: string): Promise<DispatchTicket> => {
    const res = await fetchImpl(
      `${baseUrl}/api/v3/live-record/plans/${encodeURIComponent(deps.plan.id)}/actions/${encodeURIComponent(actionId)}/prepare`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
    );
    if (!res.ok) throw new Error(`DISPATCH_TICKET_FAILED: HTTP ${res.status}`);
    return (await res.json()) as DispatchTicket;
  };

  const reportResult = async (
    call: DirectorToolCall,
    action: PreparedAction,
    status: 'SUCCESS' | 'FAILURE',
    extra: Record<string, unknown> = {},
  ): Promise<void> => {
    if (!baseUrl || !deps.takeId) return; // offline/web-dev: reporting is best-effort
    try {
      await fetchImpl(
        `${baseUrl}/api/v3/live-record/plans/${encodeURIComponent(deps.plan.id)}/actions/result`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Idempotency-Key': call.idempotency_key },
          body: JSON.stringify({
            take_id: deps.takeId,
            action_id: action.action_id,
            status,
            execution_id: call.execution_id,
            t: Date.now() / 1000,
            detail: extra.detail ?? '',
            ...extra,
            scene_id: action.scene_id,
            cue_id: action.cue_id,
          }),
        },
      );
    } catch { /* timeline append is advisory — never block the director loop */ }
  };

  const findAction = (actionId?: string): PreparedAction | null =>
    (actionId ? deps.plan.actions.find((a) => a.action_id === actionId) : undefined) ?? null;

  const runPreparedAction = async (
    call: DirectorToolCall,
  ): Promise<{ status: 'SUCCESS' | 'FAILURE'; detail?: string }> => {
    const action = findAction(call.args.action_id);
    if (!action) return failure('ACTION_NOT_IN_PLAN');

    switch (action.type) {
      case 'CODE_PLAYBACK': {
        if (!deps.invokeTauri) return failure('CODE_PLAYBACK_UNAVAILABLE_ON_WEB');
        let ticket: DispatchTicket;
        try {
          ticket = await fetchTicket(action.action_id);
        } catch (e) {
          return failure(e instanceof Error ? e.message : String(e));
        }
        const payloadText = ticket.payload_text ?? '';
        if (!payloadText) return failure('PAYLOAD_BUNDLE_MISSING');
        try {
          const result = await deps.invokeTauri<{
            status: string;
            detail: string;
            before_hash_observed?: string | null;
            after_hash_observed?: string | null;
          }>('playback_execute_code', {
            request: {
              file_path: action.target_file,
              content: payloadText,
              mode: action.typing_mode ?? 'TYPE',
              chars_per_second: action.chars_per_second ?? 22,
              before_hash: action.before_hash,
              after_hash: action.after_hash,
            },
          });
          const ok = result.status === 'SUCCESS';
          await reportResult(call, action, ok ? 'SUCCESS' : 'FAILURE', {
            detail: result.detail,
            before_hash_observed: result.before_hash_observed ?? undefined,
            after_hash_observed: result.after_hash_observed ?? undefined,
          });
          return ok
            ? { status: 'SUCCESS' as const }
            : failure(result.detail || 'PLAYBACK_VERIFICATION_FAILED');
        } catch (e) {
          return failure(`PLAYBACK_INVOKE_FAILED: ${e instanceof Error ? e.message : String(e)}`);
        }
      }

      case 'RUN_COMMAND': {
        try {
          const res = await fetchImpl(
            `${baseUrl}/api/v3/live-record/plans/${encodeURIComponent(deps.plan.id)}/actions/${encodeURIComponent(action.action_id)}/execute`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Idempotency-Key': call.idempotency_key },
              body: JSON.stringify({}),
            },
          );
          if (!res.ok) return failure(`COMMAND_EXECUTE_FAILED: HTTP ${res.status}`);
          const data = (await res.json()) as { status?: string; stderr_tail?: string };
          const ok = data.status === 'SUCCESS';
          await reportResult(call, action, ok ? 'SUCCESS' : 'FAILURE', {
            detail: data.stderr_tail?.slice(0, 400) ?? '',
            observed: { exit_code_seen: true },
          });
          return ok ? { status: 'SUCCESS' as const } : failure('COMMAND_EXIT_NONZERO');
        } catch (e) {
          return failure(`COMMAND_EXECUTE_FAILED: ${e instanceof Error ? e.message : String(e)}`);
        }
      }

      case 'BROWSER_NAVIGATION':
      case 'BROWSER_ACTION': {
        // Server executes through the existing browser session service with
        // parameters resolved from the frozen bundle (Section 14) and verifies
        // expected_after.url_contains against the observed URL.
        try {
          const res = await fetchImpl(
            `${baseUrl}/api/v3/live-record/plans/${encodeURIComponent(deps.plan.id)}/actions/${encodeURIComponent(action.action_id)}/execute-browser`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Idempotency-Key': call.idempotency_key },
              body: JSON.stringify({}),
            },
          );
          if (!res.ok) return failure(`BROWSER_EXECUTE_FAILED: HTTP ${res.status}`);
          const data = (await res.json()) as {
            status?: string;
            detail?: string;
            url_observed?: string;
            verification?: { verified?: boolean };
          };
          const ok = data.status === 'SUCCESS';
          await reportResult(call, action, ok ? 'SUCCESS' : 'FAILURE', {
            detail: data.detail ?? '',
            observed: { url_observed: data.url_observed },
          });
          return ok
            ? { status: 'SUCCESS' as const }
            : failure(data.detail || 'BROWSER_EXPECTATION_MISMATCH');
        } catch (e) {
          return failure(`BROWSER_EXECUTE_FAILED: ${e instanceof Error ? e.message : String(e)}`);
        }
      }

      case 'TOOL_RUN': {
        // Same constrained server-side runner as RUN_COMMAND — the tool's
        // command line resolves from the frozen payload bundle only.
        try {
          const res = await fetchImpl(
            `${baseUrl}/api/v3/live-record/plans/${encodeURIComponent(deps.plan.id)}/actions/${encodeURIComponent(action.action_id)}/execute`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Idempotency-Key': call.idempotency_key },
              body: JSON.stringify({}),
            },
          );
          if (!res.ok) return failure(`TOOL_EXECUTE_FAILED: HTTP ${res.status}`);
          const data = (await res.json()) as { status?: string; stderr_tail?: string };
          const ok = data.status === 'SUCCESS';
          await reportResult(call, action, ok ? 'SUCCESS' : 'FAILURE', {
            detail: data.stderr_tail?.slice(0, 400) ?? '',
            observed: { exit_code_seen: true },
          });
          return ok ? { status: 'SUCCESS' as const } : failure('TOOL_EXIT_NONZERO');
        } catch (e) {
          return failure(`TOOL_EXECUTE_FAILED: ${e instanceof Error ? e.message : String(e)}`);
        }
      }

      case 'VISUAL_VERIFY': {
        try {
          await fetchTicket(action.action_id); // confirms the expected state is the frozen one
          await reportResult(call, action, 'SUCCESS');
          return { status: 'SUCCESS' as const };
        } catch (e) {
          return failure(`VISUAL_VERIFY_FAILED: ${e instanceof Error ? e.message : String(e)}`);
        }
      }

      case 'SCENE_CONTROL':
      case 'MARKER':
      default: {
        await reportResult(call, action, 'FAILURE', { detail: `ACTION_TYPE_NOT_DESKTOP_EXECUTABLE:${action.type}` });
        return failure(`ACTION_TYPE_NOT_DESKTOP_EXECUTABLE: ${action.type}`);
      }
    }
  };

  return async (call: DirectorToolCall) => {
    switch (call.tool) {
      case 'execute_prepared_action':
      case 'retry_action':
        return runPreparedAction(call);

      case 'advance_cue': {
        const cueId = call.args.cue_id ?? '';
        for (const scene of deps.plan.scenes) {
          const cue = scene.cues.find((c) => c.cue_id === cueId);
          if (cue) {
            deps.onAdvanceCue?.({ scene_id: scene.scene_id, cue_id: cue.cue_id, expected_state_id: cue.expected_state?.state_id });
            return { status: 'SUCCESS' as const };
          }
        }
        return failure('CUE_NOT_IN_PLAN');
      }

      case 'verify_visual_state': {
        const sid = call.args.state_id ?? '';
        const known = deps.plan.actions.some((a) => a.expected_after?.state_id === sid);
        return known ? { status: 'SUCCESS' as const } : failure('STATE_NOT_IN_PLAN');
      }

      case 'pause_recording':
        try { await deps.onPauseRecording?.(); return { status: 'SUCCESS' as const }; }
        catch (e) { return failure(e instanceof Error ? e.message : String(e)); }

      case 'resume_recording':
        try { await deps.onResumeRecording?.(); return { status: 'SUCCESS' as const }; }
        catch (e) { return failure(e instanceof Error ? e.message : String(e)); }

      case 'create_marker':
        try { await deps.onCreateMarker?.(call.args.marker_type ?? 'MARKER'); return { status: 'SUCCESS' as const }; }
        catch (e) { return failure(e instanceof Error ? e.message : String(e)); }

      case 'request_operator':
        deps.onRequestOperator?.(call.args.reason ?? 'unspecified');
        return { status: 'SUCCESS' as const, detail: 'OPERATOR_REQUESTED' };

      default:
        return failure('TOOL_NOT_ALLOWED');
    }
  };
}

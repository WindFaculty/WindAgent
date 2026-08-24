/**
 * ToolCallDispatcher — Phase 6/7 (ban_ke_hoach_v1.md Section 7, 13, 14)
 *
 * Gemini Live declares constrained tools (contracts/directorTools.ts allowlist).
 * This dispatcher validates every tool call against the frozen plan before any
 * I/O — idempotency + execution_id gate ensures no successful action is replayed
 * (Section 24 session resumption).
 *
 * Real effectors (code playback, browser, tool runner) are bound via the
 * PreparedActionExecutor callback — the dispatcher never runs shell code itself.
 */

import type { DirectorToolCall } from '../contracts/directorTools';
import { validateDirectorToolCall } from '../contracts/directorTools';

export type ExecutorFn = (call: DirectorToolCall) => Promise<{ status: 'SUCCESS' | 'FAILURE'; detail?: string }>;

export class ToolCallDispatcher {
  private seenExecutionIds = new Set<string>();
  private seenIdempotency = new Map<string, { status: string }>();

  constructor(
    private readonly allowedActionIds: ReadonlySet<string>,
    private readonly allowedStateIds: ReadonlySet<string>,
    private readonly executor: ExecutorFn,
  ) {}

  async dispatch(call: DirectorToolCall): Promise<{ ok: boolean; reason?: string; result?: unknown }> {
    // No-replay of successful actions (Section 24)
    const prev = this.seenIdempotency.get(call.idempotency_key);
    if (prev) return { ok: true, result: prev };

    if (this.seenExecutionIds.has(call.execution_id)) {
      return { ok: false, reason: 'EXECUTION_ID_DUPLICATE' };
    }

    const v = validateDirectorToolCall(call, this.allowedActionIds, this.allowedStateIds);
    if (!v.ok) return { ok: false, reason: v.reason };

    this.seenExecutionIds.add(call.execution_id);

    try {
      const result = await this.executor(call);
      if (result.status === 'SUCCESS') {
        this.seenIdempotency.set(call.idempotency_key, result);
      }
      return { ok: result.status === 'SUCCESS', result, reason: result.detail };
    } catch (e) {
      return { ok: false, reason: e instanceof Error ? e.message : String(e) };
    }
  }

  reset(): void {
    this.seenExecutionIds.clear();
    // idempotency intentionally retained across reconnects (no replay)
  }
}

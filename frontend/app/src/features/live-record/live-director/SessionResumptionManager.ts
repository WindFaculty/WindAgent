/**
 * SessionResumptionManager — Phase 6 (ban_ke_hoach_v1.md Section 24)
 *
 * Google Live supports sessionResumption; ephemeral tokens have a bounded
 * lifetime so long sessions must handle reconnect/resume. Flow:
 *
 *   Live socket lost
 *     → freeze tool executor
 *     → retain current cue
 *     → resume session
 *     → send latest state + screenshot
 *     → continue
 *
 * Gemini must NOT replay already-successful actions — every action carries
 * execution_id + idempotency_key and the dispatcher enforces it.
 */

import type { SessionResumptionPolicy, LiveDirectorConnectionState } from './types';
import { DEFAULT_RESUMPTION_POLICY } from './types';

export class SessionResumptionManager {
  private attempts = 0;
  private state: LiveDirectorConnectionState = 'DISCONNECTED';
  /** Latest server-issued resumption handle (sessionResumptionUpdate.newHandle). */
  private storedHandle: string | null = null;

  constructor(private readonly policy: SessionResumptionPolicy = DEFAULT_RESUMPTION_POLICY) {}

  get connectionState(): LiveDirectorConnectionState { return this.state; }
  get attemptCount(): number { return this.attempts; }

  /** Persist the newest session handle so reconnects can BidiResume. */
  storeHandle(newHandle: string): void {
    if (!newHandle) return;
    this.storedHandle = newHandle;
  }

  getHandle(): string | null {
    return this.storedHandle;
  }

  onDisconnect(): { shouldResume: boolean; delayMs: number } {
    if (!this.policy.enabled) {
      this.state = 'DEGRADED';
      return { shouldResume: false, delayMs: 0 };
    }
    if (this.attempts >= this.policy.max_attempts) {
      this.state = 'DEGRADED';
      return { shouldResume: false, delayMs: 0 };
    }
    this.state = 'RESUMING';
    this.attempts += 1;
    const delay = this.policy.backoff_ms * Math.pow(2, this.attempts - 1);
    return { shouldResume: true, delayMs: delay };
  }

  onReconnected(): void {
    this.state = 'CONNECTED';
  }

  onResumed(): void {
    this.state = 'CONNECTED';
    // Do NOT reset attempts here — cap applies across the whole take.
  }

  onFailed(): void {
    this.state = 'DEGRADED';
  }

  resetForNewTake(): void {
    this.attempts = 0;
    this.state = 'DISCONNECTED';
    this.storedHandle = null; // a new take starts a brand-new Live session
  }
}

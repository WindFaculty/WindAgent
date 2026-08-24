/**
 * LiveDirectorClient — Phase D (ban_ke_hoach_v1.md Section 11)
 *
 * Desktop TypeScript owns the BidiGenerateContent WebSocket client (Desktop →
 * Gemini direct via ephemeral token). Backend only issues ephemeral tokens; it
 * never proxies the Live session.
 *
 * Wire protocol (google.ai.generativelanguage.v1beta BidiGenerateContent):
 *   → setup {model, systemInstruction, tools.functionDeclarations,
 *            sessionResumption.handle?}          — first message after open
 *   ← setupComplete
 *   ← sessionResumptionUpdate {newHandle}        → SessionResumptionManager
 *   ← serverContent.modelTurn.parts[].text       → session log
 *   ← toolCall {functionCalls:[{id,name,args}]}  → ToolCallDispatcher
 *   → toolResponse {functionResponses:[{id,response}]}
 *   → realtimeInput {mediaChunks:[{mimeType:"image/jpeg",data}]}
 *   ← goAway                                     → proactive resume
 *
 * Auth: browsers cannot set WebSocket headers, so the short-lived ephemeral
 * token rides the URL as `access_token` (Google's documented mechanism for
 * BidiGenerateContent). The token is single-session and expires in minutes;
 * it is never logged and never persisted (Principle: no GET/persist/log).
 *
 * Two pipelines:
 *   Recording path: 60 FPS → NVENC (native sidecar, not here)
 *   AI observation: 1–2 FPS downscaled 1280×720 JPEG → Gemini (FrameSampler)
 */

import type { LiveDirectorClientConfig, SessionResumptionPolicy } from './types';
import { DEFAULT_RESUMPTION_POLICY } from './types';
import { FrameSampler } from './FrameSampler';
import { SessionResumptionManager } from './SessionResumptionManager';
import { LiveDirectorSession } from './LiveDirectorSession';
import { ToolCallDispatcher } from './ToolCallDispatcher';
import { CueContextBuilder } from './CueContextBuilder';
import type { LiveExecutionPlan } from '../domain/types';
import type { DirectorToolCall } from '../contracts/directorTools';
import { DIRECTOR_TOOL_DECLARATIONS } from '../contracts/directorTools';
import { createWebSocket } from '@windagent/realtime';

type WebSocketFactory = (url: string, protocols?: string | string[]) => WebSocket;

/** One function call as delivered inside a BidiGenerateContent toolCall. */
export interface BidiFunctionCall {
  readonly id?: string;
  readonly name?: string;
  readonly args?: Record<string, unknown>;
}

const BIDI_ENDPOINT =
  'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent';

/**
 * Refresh the ephemeral token when it is this close to expiry (Section 24/§35:
 * takes outlive the ~30-minute TTL, so reconnects re-mint before resuming).
 */
const TOKEN_REFRESH_MARGIN_MS = 60_000;

export interface LiveDirectorClientDeps {
  readonly plan: LiveExecutionPlan;
  readonly config: LiveDirectorClientConfig;
  readonly websocketFactory?: WebSocketFactory;
  readonly executor: (call: DirectorToolCall) => Promise<{ status: 'SUCCESS' | 'FAILURE'; detail?: string }>;
  /** Re-mint an ephemeral token for this session (API token-refresh endpoint). */
  readonly refreshToken?: () => Promise<string | null>;
  readonly resumptionPolicy?: SessionResumptionPolicy;
}

export class LiveDirectorClient {
  readonly sampler: FrameSampler;
  readonly resumption: SessionResumptionManager;
  readonly session: LiveDirectorSession;
  readonly dispatcher: ToolCallDispatcher;
  readonly cueBuilder: CueContextBuilder;

  private ws: WebSocket | null = null;
  private setupSent = false;
  private lastModelTurn: string | null = null;
  private activeToken: string;
  private readonly factory: WebSocketFactory;

  constructor(private readonly deps: LiveDirectorClientDeps) {
    this.sampler = new FrameSampler();
    this.resumption = new SessionResumptionManager(deps.resumptionPolicy ?? DEFAULT_RESUMPTION_POLICY);
    const firstScene = deps.plan.scenes[0];
    const firstCue = firstScene?.cues[0];
    this.session = new LiveDirectorSession(deps.config, {
      scene_id: firstScene?.scene_id ?? 'scene-01',
      cue_id: firstCue?.cue_id ?? 'cue-01',
      expected_state_id: firstCue?.expected_state?.state_id,
    });
    this.cueBuilder = new CueContextBuilder(deps.plan);
    this.dispatcher = new ToolCallDispatcher(
      new Set(deps.plan.actions.map((a) => a.action_id)),
      new Set(
        deps.plan.actions.map((a) => a.expected_after?.state_id).filter((x): x is string => !!x),
      ),
      deps.executor,
    );
    this.factory = deps.websocketFactory ?? createWebSocket;
    this.activeToken = deps.config.ephemeral_token;
  }

  get allowedToolNames(): readonly string[] {
    return DIRECTOR_TOOL_DECLARATIONS.map((d) => d.name);
  }

  /** Canonical endpoint (no auth material) — kept stable for contract tests. */
  buildLiveUrl(): string {
    return BIDI_ENDPOINT;
  }

  /** Swap in a freshly minted ephemeral token (never logged). */
  updateEphemeralToken(token: string): void {
    if (!token) return;
    this.activeToken = token;
  }

  /** Endpoint with the single-session ephemeral token. Never log this value. */
  private authenticatedUrl(): string {
    return `${BIDI_ENDPOINT}?access_token=${encodeURIComponent(this.activeToken)}`;
  }

  /**
   * Token refresh before resume (§24/§35): when the current ephemeral token is
   * expired or about to expire, mint a fresh one bound to the same session and
   * frozen plan_hash so the resumed take never rides a dead credential.
   */
  private async ensureFreshToken(): Promise<void> {
    if (!this.deps.refreshToken) return;
    const expiresAt = Date.parse(this.deps.config.expires_at);
    const needsRefresh = Number.isNaN(expiresAt) || expiresAt - Date.now() < TOKEN_REFRESH_MARGIN_MS;
    if (!needsRefresh) return;
    try {
      const fresh = await this.deps.refreshToken();
      if (fresh) this.updateEphemeralToken(fresh);
    } catch {
      // Refresh failure is non-fatal here — reconnect proceeds with the
      // current token and Google's own auth rejection drives DEGRADED.
    }
  }

  /** Connect — sends the frozen setup immediately after the socket opens. */
  connect(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
    this.setupSent = false;
    this.session.setState('CONNECTING');
    const ws = this.factory(this.authenticatedUrl());
    this.ws = ws;
    this.bindEvents(ws);
  }

  disconnect(): void {
    try { this.ws?.close(); } catch { /* ignore */ }
    this.ws = null;
    this.session.setState('DISCONNECTED');
  }

  /**
   * Drain the sampler's staged frame into the Live socket at ≤2 FPS
   * (FrameSampler owns the rate gate). Returns true when a frame was sent.
   */
  sendFrame(nowMs = Date.now()): boolean {
    if (!this.isSocketOpen()) return false;
    const frame = this.sampler.consume(nowMs);
    if (!frame) return false;
    const base64 = frame.dataUrl.slice(frame.dataUrl.indexOf(',') + 1);
    return this.sendJson({
      realtimeInput: {
        mediaChunks: [{ mimeType: 'image/jpeg', data: base64 }],
      },
    });
  }

  /** Current context packet sent with each Gemini turn (Section 12). */
  currentContext() {
    return this.cueBuilder.buildContext({
      current: this.session.current,
      lastToolResult: (this.session.snapshot() as unknown as { lastToolResult?: unknown }).lastToolResult,
      elapsedSec: this.session.elapsedSec,
      allowedTools: this.allowedToolNames as unknown as readonly string[],
    });
  }

  get latestModelTurn(): string | null {
    return this.lastModelTurn;
  }

  // ─── Internals ─────────────────────────────────────────────────────────────

  private isSocketOpen(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  private sendJson(value: unknown): boolean {
    if (!this.isSocketOpen()) return false;
    try {
      this.ws!.send(JSON.stringify(value));
      return true;
    } catch {
      return false;
    }
  }

  /** Frozen session configuration — sent exactly once per connection. */
  private sendSetup(): void {
    if (this.setupSent) return;
    this.setupSent = true;
    const ctx = this.currentContext();
    const handle = this.resumption.getHandle();
    this.sendJson({
      setup: {
        model: `models/${this.deps.config.model_id}`,
        systemInstruction: { parts: [{ text: ctx.system_instruction }] },
        tools: { functionDeclarations: DIRECTOR_TOOL_DECLARATIONS },
        ...(handle ? { sessionResumption: { handle } } : {}),
      },
    });
  }

  private bindEvents(ws: WebSocket): void {
    ws.addEventListener('open', () => {
      this.sendSetup();
    });
    ws.addEventListener('close', () => {
      void this.handleClose();
    });
    ws.addEventListener('message', (ev) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(typeof ev.data === 'string' ? ev.data : '{}') as Record<string, unknown>;
      } catch {
        return; // ignore malformed frames
      }
      this.handleServerMessage(msg);
    });
    ws.addEventListener('error', () => {
      this.resumption.onFailed();
      this.session.setState('DEGRADED');
    });
  }

  /** Disconnect flow: refresh the token if needed, then resume with backoff. */
  private async handleClose(): Promise<void> {
    const { shouldResume, delayMs } = this.resumption.onDisconnect();
    this.session.setState(shouldResume ? 'RESUMING' : 'DEGRADED');
    if (!shouldResume) return;
    await this.ensureFreshToken();
    setTimeout(() => this.connect(), delayMs);
  }

  private handleServerMessage(msg: Record<string, unknown>): void {
    // setupComplete — server accepted the frozen config; session is live.
    if ('setupComplete' in msg) {
      this.session.markStarted();
      this.resumption.onReconnected();
      return;
    }

    // sessionResumptionUpdate.newHandle → persist for reconnects.
    const resumptionUpdate = msg['sessionResumptionUpdate'] as { newHandle?: string } | undefined;
    if (resumptionUpdate?.newHandle) {
      this.resumption.storeHandle(resumptionUpdate.newHandle);
    }

    // goAway — server is closing soon; resume proactively to keep the take.
    if ('goAway' in msg && this.ws) {
      try { this.ws.close(); } catch { /* close flow handles resumption */ }
      return;
    }

    // serverContent.modelTurn — director narration/observations for the log.
    const serverContent = msg['serverContent'] as {
      modelTurn?: { parts?: ReadonlyArray<{ text?: string }> };
    } | undefined;
    const turnText = serverContent?.modelTurn?.parts
      ?.map((p) => p.text ?? '')
      .join('')
      .trim();
    if (turnText) this.lastModelTurn = turnText;

    // toolCall.functionCalls[] — gated dispatch, one response per call id.
    const toolCall = msg['toolCall'] as { functionCalls?: BidiFunctionCall[] } | undefined;
    if (Array.isArray(toolCall?.functionCalls)) {
      for (const fc of toolCall.functionCalls) void this.handleFunctionCall(fc);
    }
  }

  private async handleFunctionCall(fc: BidiFunctionCall): Promise<void> {
    const name = typeof fc.name === 'string' ? fc.name : '';
    const rawArgs = (fc.args ?? {}) as Record<string, unknown>;
    const args: Record<string, string> = {};
    for (const [k, v] of Object.entries(rawArgs)) {
      if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
        args[k] = String(v);
      }
    }

    // Idempotency keys bind to the plan action itself so replays of the same
    // action collapse even across reconnects; execution ids stay per-attempt.
    const actionId = args['action_id'];
    const plannedAction = actionId
      ? this.deps.plan.actions.find((a) => a.action_id === actionId)
      : undefined;
    const call: DirectorToolCall = {
      tool: name as DirectorToolCall['tool'],
      args,
      idempotency_key: plannedAction?.idempotency_key ?? `idem_${fc.id ?? `${name}_${Date.now()}`}`,
      execution_id: fc.id ? `exec_${fc.id}` : `exec_${name}_${Date.now()}`,
    };

    const res = await this.dispatcher.dispatch(call);
    this.session.setToolResult({ tool: call.tool, ok: res.ok, reason: res.reason });

    // Google shape: one functionResponses entry per functionCall id.
    this.sendJson({
      toolResponse: {
        functionResponses: [
          {
            ...(fc.id ? { id: fc.id } : {}),
            response: {
              output: {
                status: res.ok ? 'SUCCESS' : 'FAILURE',
                detail: res.reason ?? '',
              },
            },
          },
        ],
      },
    });
  }
}

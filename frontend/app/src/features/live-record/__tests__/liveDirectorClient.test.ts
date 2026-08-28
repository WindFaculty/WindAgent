/**
 * Wire-shape tests for LiveDirectorClient (Phase 6, ban_ke_hoach_v1.md §11/§24).
 *
 * Exercises the BidiGenerateContent contract against a fake WebSocket:
 *   - frozen setup message (model / functionDeclarations / resumption handle);
 *   - toolCall → gated dispatch → one toolResponse per call id;
 *   - sessionResumptionUpdate handle retention across reconnects;
 *   - §24/§35 token refresh before resume when the ephemeral token expired.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { LiveDirectorClient } from '../live-director/LiveDirectorClient';
import type { LiveExecutionPlan } from '../domain/types';
import type { DirectorToolCall } from '../contracts/directorTools';
import { DIRECTOR_TOOL_DECLARATIONS } from '../contracts/directorTools';

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  url: string;
  private listeners: Record<string, Array<(ev?: unknown) => void>> = {};

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, fn: (ev?: unknown) => void): void {
    (this.listeners[type] ??= []).push(fn);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.readyState = FakeWebSocket.CLOSED;
    this.emit('close');
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.emit('open');
  }

  receive(obj: unknown): void {
    this.emit('message', { data: JSON.stringify(obj) });
  }

  lastJson(): Record<string, Record<string, unknown>> {
    return JSON.parse(this.sent[this.sent.length - 1]);
  }

  private emit(type: string, ev?: unknown): void {
    for (const fn of this.listeners[type] ?? []) fn(ev);
  }
}

function makePlan(): LiveExecutionPlan {
  return {
    id: 'plan_ep_r1',
    plan_hash: 'a'.repeat(64),
    episode_id: 'ep_1',
    episode_revision_id: 'rev_1',
    status: 'FROZEN',
    recording_profile: { resolution: '1920x1080', fps: 60, codec: 'H264', segment_minutes: 5 },
    scenes: [
      {
        scene_id: 'scene-01',
        title: 'Open VS Code',
        index: 0,
        cues: [{ cue_id: 'scene-01-cue-01', scene_id: 'scene-01', index: 0 }],
      },
    ],
    actions: [
      {
        action_id: 'code-001',
        type: 'CODE_PLAYBACK',
        scene_id: 'scene-01',
        payload_ref: 'artifact://live-record/code-001',
        idempotency_key: 'idem_code-001',
      },
      {
        action_id: 'browser-001',
        type: 'BROWSER_NAVIGATION',
        scene_id: 'scene-01',
        payload_ref: 'artifact://live-record/browser-001',
        idempotency_key: 'idem_browser-001',
        expected_after: { state_id: 'st_landed' },
      },
    ],
  } as unknown as LiveExecutionPlan;
}

interface DepsOverrides {
  expiresAt?: string;
  refreshToken?: () => Promise<string | null>;
}

function makeClient({ expiresAt, refreshToken }: DepsOverrides = {}) {
  const executorCalls: DirectorToolCall[] = [];
  const client = new LiveDirectorClient({
    plan: makePlan(),
    config: {
      provider_id: 'google',
      model_id: 'gemini-3.1-flash-live-preview',
      ephemeral_token: 'stale-token-value-0000000000000000000000',
      expires_at: expiresAt ?? new Date(Date.now() + 30 * 60 * 1000).toISOString(),
      execution_plan_hash: 'a'.repeat(64),
      session_id: 'ldir_test',
    },
    websocketFactory: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    executor: async (call) => {
      executorCalls.push(call);
      return { status: 'SUCCESS' as const };
    },
    ...(refreshToken ? { refreshToken } : {}),
    resumptionPolicy: {
      enabled: true,
      max_attempts: 3,
      backoff_ms: 0,
      retain_cue: true,
      no_replay_of_success: true,
    },
  });
  return { client, executorCalls };
}

const flush = () => new Promise((r) => setTimeout(r, 10));

describe('LiveDirectorClient wire shapes', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('buildLiveUrl exposes the canonical BidiGenerateContent endpoint without auth material', () => {
    const { client } = makeClient();
    expect(client.buildLiveUrl()).toContain('BidiGenerateContent');
    expect(client.buildLiveUrl()).not.toContain('access_token');
  });

  it('sends the frozen setup exactly once per connection with declarations and no inline payload', () => {
    const { client } = makeClient();
    client.connect();
    const ws = FakeWebSocket.instances[0];
    ws.open();

    const setup = JSON.parse(ws.sent[0])['setup'] as Record<string, unknown>;
    expect(setup['model']).toBe('models/gemini-3.1-flash-live-preview');
    const tools = setup['tools'] as { functionDeclarations: Array<{ name: string }> };
    expect(tools.functionDeclarations.map((d) => d.name)).toEqual(
      DIRECTOR_TOOL_DECLARATIONS.map((d) => d.name),
    );
    expect(setup['sessionResumption']).toBeUndefined();
    expect(JSON.stringify(setup)).not.toContain('access_token');

    // Re-connect while open must not re-send setup.
    const countBefore = ws.sent.length;
    client.connect();
    expect(ws.sent.length).toBe(countBefore);
  });

  it('routes toolCall functionCalls through the dispatcher and answers one response per call id', async () => {
    const { client, executorCalls } = makeClient();
    client.connect();
    const ws = FakeWebSocket.instances[0];
    ws.open();
    ws.sent.length = 0;

    ws.receive({
      toolCall: {
        functionCalls: [
          { id: 'fc-1', name: 'execute_prepared_action', args: { action_id: 'browser-001' } },
        ],
      },
    });
    await flush();

    expect(executorCalls).toHaveLength(1);
    expect(executorCalls[0].args['action_id']).toBe('browser-001');
    // Idempotency binds to the frozen plan's action key, not the model output.
    expect(executorCalls[0].idempotency_key).toBe('idem_browser-001');

    const response = ws.lastJson()['toolResponse'] as {
      functionResponses: Array<{ id?: string; response: { output: { status: string } } }>;
    };
    expect(response.functionResponses).toHaveLength(1);
    expect(response.functionResponses[0].id).toBe('fc-1');
    expect(response.functionResponses[0].response.output.status).toBe('SUCCESS');
  });

  it('retains sessionResumption handles and resumes through them after disconnect', async () => {
    const { client } = makeClient();
    client.connect();
    const first = FakeWebSocket.instances[0];
    first.open();
    first.receive({ sessionResumptionUpdate: { newHandle: 'handle-A' } });
    expect(client.resumption.getHandle()).toBe('handle-A');

    first.close(); // triggers refresh-check + backoff(0) reconnect
    await flush();

    const second = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    expect(second).not.toBe(first);
    second.open();
    const setup = JSON.parse(second.sent[0])['setup'] as Record<string, unknown>;
    expect(setup['sessionResumption']).toEqual({ handle: 'handle-A' });
  });

  it('re-mints the ephemeral token before resuming an expired session (Section 24/§35)', async () => {
    const refreshToken = vi.fn().mockResolvedValue('fresh-token-value-00000000000000000000000');
    const { client } = makeClient({
      expiresAt: new Date(Date.now() - 1000).toISOString(), // already expired
      refreshToken,
    });
    client.connect();
    FakeWebSocket.instances[0].close();
    await flush();

    expect(refreshToken).toHaveBeenCalledTimes(1);
    const reconnected = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    expect(reconnected.url).toContain(`access_token=${encodeURIComponent('fresh-token-value-00000000000000000000000')}`);
    expect(reconnected.url).not.toContain('stale-token');
  });

  it('does not call token refresh when the current token is still fresh', async () => {
    const refreshToken = vi.fn().mockResolvedValue(null);
    const { client } = makeClient({
      expiresAt: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
      refreshToken,
    });
    client.connect();
    FakeWebSocket.instances[0].close();
    await flush();

    expect(refreshToken).not.toHaveBeenCalled();
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2); // resumed anyway
  });
});

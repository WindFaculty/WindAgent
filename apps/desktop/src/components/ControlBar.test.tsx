/** Phase 10 — Control bar tests (per ban_ke_hoach.md §Phase 10.1).
 *
 * Covers two things in one file because they're tiny and related:
 *  - <ControlBar> renders 4 buttons with correct enable/disable rules.
 *  - apiClient.controlSession hits the right URL with POST (smoke
 *    test against a stubbed global.fetch).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ControlBar } from "../components/ControlBar";
import type { RunnerSnapshot } from "../state/sessionStore";
import { controlSession, retryStep } from "../api/client";

const idle: RunnerSnapshot = { kind: "idle" };
const running: RunnerSnapshot = {
  kind: "running",
  state: {
    session_id: "sess-1",
    workflow_id: "wf-1",
    paused: false,
    stop_requested: false,
    current_step_index: 0,
    last_failed_step_id: null,
    task_done: false,
    final_status: null,
  },
};

describe("<ControlBar>", () => {
  afterEach(cleanup);

  it("disables every button when there is no session", () => {
    render(
      <ControlBar
        runner={idle}
        hasSession={false}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText("Pause")).toBeDisabled();
    expect(screen.getByText("Resume")).toBeDisabled();
    expect(screen.getByText("Stop")).toBeDisabled();
    expect(screen.getByText("Retry")).toBeDisabled();
  });

  it("Pause / Stop enabled while running; Resume disabled; Retry disabled without a failed step", () => {
    render(
      <ControlBar
        runner={running}
        hasSession={true}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText("Pause")).toBeEnabled();
    expect(screen.getByText("Stop")).toBeEnabled();
    expect(screen.getByText("Resume")).toBeDisabled();
    expect(screen.getByText("Retry")).toBeDisabled();
  });

  it("invokes the right callback for each button", () => {
    const onPause = vi.fn();
    const onResume = vi.fn();
    const onStop = vi.fn();
    const onRetry = vi.fn();
    render(
      <ControlBar
        runner={running}
        hasSession={true}
        busy={false}
        onPause={onPause}
        onResume={onResume}
        onStop={onStop}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByText("Pause"));
    fireEvent.click(screen.getByText("Stop"));
    expect(onPause).toHaveBeenCalledTimes(1);
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(onResume).not.toHaveBeenCalled();
    expect(onRetry).not.toHaveBeenCalled();
  });
});

describe("apiClient — control endpoints", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("controlSession POSTs to /api/sessions/{id}/{action}", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await controlSession("sess-1", "pause");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sessions/sess-1/pause");
    expect(init).toMatchObject({ method: "POST" });
  });

  it("retryStep POSTs to /api/workflow/{stepId}/retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await retryStep("step-7");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/workflow/step-7/retry");
    expect(init).toMatchObject({ method: "POST" });
  });

  it("controlSession throws with the API error message on non-2xx", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "session not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    await expect(controlSession("missing", "stop")).rejects.toThrow(
      /session not found/,
    );
  });
});

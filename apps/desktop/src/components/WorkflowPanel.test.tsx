/** Phase 10 — WorkflowPanel render test (per ban_ke_hoach.md §Phase 10.1).
 *
 * Smoke test: render the empty state, then a populated workflow, then
 * verify step names + status badges are present.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { WorkflowPanel } from "../components/WorkflowPanel";
import type { Workflow } from "../api/types";

describe("<WorkflowPanel>", () => {
  it("shows the empty hint when workflow is null", () => {
    render(<WorkflowPanel workflow={null} />);
    expect(screen.getByText(/Chưa có workflow/i)).toBeInTheDocument();
  });

  it("shows the empty-workflow hint when steps are empty", () => {
    const wf: Workflow = {
      workflow_id: "wf-1",
      session_id: "sess-1",
      created_at: "2026-06-19T12:00:00Z",
      status: "pending",
      steps: [],
    };
    render(<WorkflowPanel workflow={wf} />);
    expect(screen.getByText(/Workflow rỗng/i)).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
  });

  it("renders every step name + status badge", () => {
    const wf: Workflow = {
      workflow_id: "wf-1",
      session_id: "sess-1",
      created_at: "2026-06-19T12:00:00Z",
      status: "running",
      steps: [
        {
          id: "s1",
          order: 1,
          name: "Open Notepad",
          tool_name: "open_app",
          params: { app: "notepad" },
          status: "success",
        },
        {
          id: "s2",
          order: 2,
          name: "Type Hello",
          tool_name: "type_text",
          params: { text: "Hello" },
          status: "running",
        },
      ],
    };
    render(<WorkflowPanel workflow={wf} />);
    expect(screen.getByText("Open Notepad")).toBeInTheDocument();
    expect(screen.getByText("Type Hello")).toBeInTheDocument();
    // Both the workflow badge and step #2 show "running" — assert presence
    // by querying the step list directly so we don't depend on count.
    const stepList = screen.getByRole("list");
    expect(stepList.textContent).toContain("running");
    expect(stepList.textContent).toContain("success");
  });
});

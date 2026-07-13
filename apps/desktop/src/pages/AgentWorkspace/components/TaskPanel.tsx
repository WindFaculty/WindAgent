import type { Workflow } from "../../../api/types";

interface Props {
  workflow: Workflow | null;
}

// Map a workflow step status to the legacy task-step visual status.
function toStepView(status: string): "success" | "pending" | "running" {
  switch (status) {
    case "running":
      return "running";
    case "success":
      return "success";
    case "failed":
      return "pending"; // failed shows as not-done, with red badge below
    case "cancelled":
    case "skipped":
    case "pending":
    default:
      return "pending";
  }
}

export function TaskPanel({ workflow }: Props) {
  const taskSteps = (workflow?.steps ?? []).map((s) => ({
    id: s.id,
    name: s.name,
    status: s.status,
    view: toStepView(s.status),
  }));

  return (
    <section className="dashboard-panel">
      <header className="panel-header">
        <div className="panel-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          Current Task
        </div>
      </header>
      <div className="panel-body" style={{ overflowY: "auto" }}>
        {!workflow ? (
          <div className="empty-state" style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            textAlign: "center",
            padding: "40px",
            color: "var(--text-muted)",
            gap: "12px",
          }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ opacity: 0.4 }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h3 style={{ fontSize: "1.1rem", fontWeight: "600", color: "var(--text-main)" }}>No Task Plan</h3>
            <p style={{ fontSize: "0.82rem", maxWidth: "280px" }}>The agent's todo list will appear here once a run starts.</p>
          </div>
        ) : (
          <>
            <div className="current-task-info">
              <div className="current-task-name">{workflow.objective || "Active Task"}</div>
              <div className="current-task-desc">
                {taskSteps.length} task{taskSteps.length === 1 ? "" : "s"} ·{" "}
                {taskSteps.filter((s) => s.status === "success").length} completed
              </div>
            </div>

            <div className="task-steps-list">
              {taskSteps.map((step) => (
                <div
                  key={step.id}
                  className={`task-step ${step.view === "running" ? "active" : ""} ${
                    step.view === "pending" ? "pending" : ""
                  }`}
                >
                  <div className="task-step-left">
                    <div className={`step-chk ${step.view}`}>
                      {step.status === "success" && (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                      {step.view === "running" && (
                        <div className="check-spinner" style={{ width: "10px", height: "10px" }} />
                      )}
                      {(step.view === "pending") && (
                        <span style={{ width: "4px", height: "4px", background: "var(--text-dim)", borderRadius: "50%" }} />
                      )}
                    </div>
                    <span className="step-label">{step.name}</span>
                  </div>

                  <div className="step-meta-right">
                    <span
                      className={`step-badge ${step.view}`}
                      style={
                        step.status === "failed"
                          ? { background: "rgba(239,68,68,0.15)", color: "#ef4444", borderColor: "rgba(239,68,68,0.3)" }
                          : step.status === "cancelled" || step.status === "skipped"
                          ? { background: "rgba(148,163,184,0.12)", color: "var(--text-dim)" }
                          : undefined
                      }
                    >
                      {step.status === "running"
                        ? "In Progress"
                        : step.status === "success"
                        ? "Completed"
                        : step.status === "failed"
                        ? "Failed"
                        : step.status === "cancelled"
                        ? "Cancelled"
                        : step.status === "skipped"
                        ? "Skipped"
                        : "Pending"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

import type { Workflow } from "../api/types";
import { WorkflowStepItem } from "./WorkflowStepItem";

interface Props {
  workflow: Workflow | null;
}

export function WorkflowPanel({ workflow }: Props) {
  if (!workflow) {
    return (
      <section className="panel workflow-panel">
        <header>
          <h2>Workflow</h2>
        </header>
        <p className="muted">Chưa có workflow.</p>
      </section>
    );
  }
  return (
    <section className="panel workflow-panel">
      <header>
        <h2>Workflow</h2>
        <span className="badge">{workflow.status}</span>
      </header>
      {workflow.steps.length === 0 ? (
        <p className="muted">Workflow rỗng — model không match được intent.</p>
      ) : (
        <ol className="step-list">
          {workflow.steps.map((s) => (
            <WorkflowStepItem key={s.id} step={s} />
          ))}
        </ol>
      )}
    </section>
  );
}
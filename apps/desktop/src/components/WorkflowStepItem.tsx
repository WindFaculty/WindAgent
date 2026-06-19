import type { WorkflowStep } from "../api/types";

const STATUS_ICON: Record<string, string> = {
  pending: "○",
  running: "▶",
  success: "✓",
  failed: "✗",
  skipped: "⤼",
  cancelled: "⊘",
};

interface Props {
  step: WorkflowStep;
}

export function WorkflowStepItem({ step }: Props) {
  const icon = STATUS_ICON[step.status] ?? "?";
  return (
    <li className={`step step-${step.status}`}>
      <span className="step-icon">{icon}</span>
      <span className="step-order">{step.order}</span>
      <span className="step-name">{step.name}</span>
      <code className="step-tool">{step.tool_name}</code>
      <span className="step-status">{step.status}</span>
    </li>
  );
}
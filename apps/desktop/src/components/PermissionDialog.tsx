import type { PermissionRequestPayload } from "../api/types";

interface Props {
  request: PermissionRequestPayload;
  onDecide: (requestId: string, decision: "granted" | "denied") => void;
}

function formatParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params);
  if (entries.length === 0) return "(no params)";
  // Truncate long strings (e.g. type_text) to keep dialog readable.
  return entries
    .map(([k, v]) => {
      const s = typeof v === "string" ? v : JSON.stringify(v);
      const trimmed = s.length > 80 ? s.slice(0, 77) + "..." : s;
      return `${k} = ${trimmed}`;
    })
    .join("\n");
}

export function PermissionDialog({ request, onDecide }: Props) {
  return (
    <div className="permission-dialog" role="dialog" aria-modal="true">
      <h3>Permission required</h3>
      <p>
        <strong>{request.summary}</strong>
      </p>
      <p>
        Tool: <code>{request.tool_name}</code> · Risk:{" "}
        <span className={`badge badge-${request.risk_level}`}>{request.risk_level}</span>
      </p>
      <pre>{formatParams(request.params)}</pre>
      <div className="permission-actions">
        <button
          className="btn-danger"
          onClick={() => onDecide(request.request_id, "denied")}
        >
          Cancel
        </button>
        <button
          className="btn-primary"
          onClick={() => onDecide(request.request_id, "granted")}
          autoFocus
        >
          Confirm
        </button>
      </div>
    </div>
  );
}
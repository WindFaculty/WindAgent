import { Card } from "./Card.tsx";
import { Badge } from "./Badge.tsx";

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
}

export interface GraphEdge {
  from: string;
  to: string;
}

export function GraphViewer({
  nodes,
  edges,
  onNodeClick,
  activeNodeId,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
  activeNodeId?: string;
}) {
  const statusBadge = {
    pending: <Badge level="neutral">Pending</Badge>,
    running: <Badge level="info" dot>Running</Badge>,
    completed: <Badge level="success">Passed</Badge>,
    failed: <Badge level="danger">Failed</Badge>,
    skipped: <Badge level="neutral">Skipped</Badge>,
  };

  return (
    <Card variant="glass" padding="md" style={{ width: "100%", overflowX: "auto" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "24px",
          minWidth: "600px",
          padding: "16px 8px",
        }}
      >
        {nodes.map((node, index) => {
          const isSelected = node.id === activeNodeId;
          const hasOutgoing = edges.some((e) => e.from === node.id);

          return (
            <div key={node.id} style={{ display: "flex", alignItems: "center", gap: "24px" }}>
              <div
                onClick={() => onNodeClick?.(node)}
                style={{
                  padding: "12px 16px",
                  borderRadius: "var(--windagent-radius-md)",
                  background: isSelected
                    ? "var(--windagent-color-surface-active)"
                    : "var(--windagent-color-surface)",
                  border: isSelected
                    ? "2px solid var(--windagent-color-accent)"
                    : "1px solid var(--windagent-border-default)",
                  boxShadow: isSelected ? "var(--windagent-shadow-glow)" : "var(--windagent-shadow-sm)",
                  cursor: onNodeClick ? "pointer" : "default",
                  minWidth: "160px",
                  transition: "all var(--windagent-transition-fast)",
                }}
              >
                <div
                  style={{
                    fontSize: "0.75rem",
                    color: "var(--windagent-color-text-dim)",
                    textTransform: "uppercase",
                    marginBottom: "4px",
                  }}
                >
                  {node.type}
                </div>
                <div
                  style={{
                    fontSize: "0.9rem",
                    fontWeight: 600,
                    color: "var(--windagent-color-text)",
                    marginBottom: "8px",
                  }}
                >
                  {node.label}
                </div>
                <div>{statusBadge[node.status]}</div>
              </div>

              {(hasOutgoing || index < nodes.length - 1) && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    color: "var(--windagent-color-accent)",
                    fontWeight: "bold",
                  }}
                >
                  <span style={{ fontSize: "1.2rem" }}>➔</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

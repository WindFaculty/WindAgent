import React from "react";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render?: (row: T) => React.ReactNode;
  width?: string;
  align?: "left" | "center" | "right";
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField: keyof T | ((row: T) => string);
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyField,
  onRowClick,
  emptyMessage = "No records found",
}: DataTableProps<T>) {
  const getKey = (row: T): string => {
    if (typeof keyField === "function") return keyField(row);
    const val = (row as Record<string, unknown>)[keyField as string];
    return String(val);
  };

  return (
    <div
      style={{
        width: "100%",
        overflowX: "auto",
        border: "1px solid var(--windagent-border-subtle)",
        borderRadius: "var(--windagent-radius-md)",
      }}
    >
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.875rem",
          textAlign: "left",
        }}
      >
        <thead>
          <tr
            style={{
              background: "var(--windagent-color-bg-subtle)",
              borderBottom: "1px solid var(--windagent-border-default)",
            }}
          >
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  padding: "10px 14px",
                  fontWeight: 600,
                  color: "var(--windagent-color-text-muted)",
                  fontSize: "0.75rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  width: col.width,
                  textAlign: col.align ?? "left",
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  padding: "var(--windagent-space-6)",
                  textAlign: "center",
                  color: "var(--windagent-color-text-dim)",
                }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row) => (
              <tr
                key={getKey(row)}
                onClick={() => onRowClick?.(row)}
                style={{
                  borderBottom: "1px solid var(--windagent-border-subtle)",
                  cursor: onRowClick ? "pointer" : "default",
                  transition: "background var(--windagent-transition-fast)",
                }}
                onMouseEnter={(e) => {
                  if (onRowClick) e.currentTarget.style.background = "var(--windagent-color-surface-hover)";
                }}
                onMouseLeave={(e) => {
                  if (onRowClick) e.currentTarget.style.background = "transparent";
                }}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={{
                      padding: "12px 14px",
                      color: "var(--windagent-color-text)",
                      textAlign: col.align ?? "left",
                    }}
                  >
                    {col.render ? col.render(row) : ((row as Record<string, unknown>)[col.key] as React.ReactNode)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

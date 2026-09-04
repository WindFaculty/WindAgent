import { useState } from "react";

export interface CodeBlockProps {
  code: string;
  language?: string;
  maxHeight?: string;
  showLineNumbers?: boolean;
}

export function CodeBlock({
  code,
  language = "typescript",
  maxHeight = "360px",
  showLineNumbers = true,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lines = code.trim().split("\n");

  return (
    <div
      style={{
        position: "relative",
        background: "var(--windagent-color-bg-subtle)",
        border: "1px solid var(--windagent-border-subtle)",
        borderRadius: "var(--windagent-radius-md)",
        overflow: "hidden",
        fontFamily: "var(--windagent-font-mono)",
        fontSize: "0.85rem",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "6px 12px",
          background: "var(--windagent-color-surface)",
          borderBottom: "1px solid var(--windagent-border-subtle)",
          color: "var(--windagent-color-text-dim)",
          fontSize: "0.75rem",
        }}
      >
        <span>{language.toUpperCase()}</span>
        <button
          type="button"
          onClick={handleCopy}
          style={{
            background: "transparent",
            border: "none",
            color: copied ? "var(--windagent-color-success)" : "var(--windagent-color-text-muted)",
            cursor: "pointer",
            fontSize: "0.75rem",
            padding: "2px 6px",
            borderRadius: "var(--windagent-radius-sm)",
          }}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <div
        style={{
          maxHeight,
          overflowY: "auto",
          padding: "12px",
          display: "flex",
          lineHeight: 1.6,
        }}
      >
        {showLineNumbers && (
          <div
            style={{
              userSelect: "none",
              color: "var(--windagent-color-text-dim)",
              textAlign: "right",
              paddingRight: "16px",
              marginRight: "16px",
              borderRight: "1px solid var(--windagent-border-subtle)",
            }}
          >
            {lines.map((_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>
        )}
        <pre style={{ margin: 0, color: "var(--windagent-color-text)", overflowX: "auto", flex: 1 }}>
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}

export function JsonViewer({ data, maxHeight = "300px" }: { data: unknown; maxHeight?: string }) {
  const jsonStr = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return <CodeBlock code={jsonStr} language="json" maxHeight={maxHeight} showLineNumbers={false} />;
}

import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "glass" | "outline" | "highlight";
  padding?: "none" | "sm" | "md" | "lg";
}

export function Card({
  variant = "default",
  padding = "md",
  children,
  style,
  className = "",
  ...props
}: CardProps) {
  const paddingMap = {
    none: "0",
    sm: "var(--windagent-space-2) var(--windagent-space-3)",
    md: "var(--windagent-space-4)",
    lg: "var(--windagent-space-6)",
  };

  const variantStyles: Record<string, React.CSSProperties> = {
    default: {
      background: "var(--windagent-color-surface)",
      border: "1px solid var(--windagent-border-subtle)",
    },
    glass: {
      background: "var(--windagent-color-glass)",
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
      border: "1px solid var(--windagent-color-glass-border)",
    },
    outline: {
      background: "transparent",
      border: "1px solid var(--windagent-border-default)",
    },
    highlight: {
      background: "var(--windagent-color-surface)",
      border: "1px solid var(--windagent-color-accent)",
      boxShadow: "var(--windagent-shadow-glow)",
    },
  };

  return (
    <div
      style={{
        borderRadius: "var(--windagent-radius-lg)",
        padding: paddingMap[padding],
        transition: "border-color var(--windagent-transition-normal), box-shadow var(--windagent-transition-normal)",
        ...variantStyles[variant],
        ...style,
      }}
      className={`windagent-card ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: "var(--windagent-space-3)",
        gap: "var(--windagent-space-2)",
      }}
    >
      <div>
        <h3
          style={{
            fontSize: "1rem",
            fontWeight: 600,
            color: "var(--windagent-color-text)",
            margin: 0,
          }}
        >
          {title}
        </h3>
        {subtitle && (
          <p
            style={{
              fontSize: "0.85rem",
              color: "var(--windagent-color-text-muted)",
              marginTop: "2px",
              margin: 0,
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}

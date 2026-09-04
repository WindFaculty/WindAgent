import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger" | "brand";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: React.ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  disabled,
  style,
  ...props
}: ButtonProps) {
  const sizeMap = {
    sm: { padding: "4px 10px", fontSize: "0.8rem", gap: "6px" },
    md: { padding: "8px 16px", fontSize: "0.875rem", gap: "8px" },
    lg: { padding: "12px 24px", fontSize: "1rem", gap: "10px" },
  };

  const variantStyles: Record<string, React.CSSProperties> = {
    primary: {
      background: "var(--windagent-color-accent)",
      color: "#000000",
      border: "none",
      fontWeight: 600,
    },
    brand: {
      background: "var(--windagent-color-brand-gradient)",
      color: "#ffffff",
      border: "none",
      fontWeight: 600,
      boxShadow: "0 2px 10px rgba(121, 40, 202, 0.4)",
    },
    secondary: {
      background: "var(--windagent-color-surface-hover)",
      color: "var(--windagent-color-text)",
      border: "1px solid var(--windagent-border-default)",
    },
    outline: {
      background: "transparent",
      color: "var(--windagent-color-text-secondary)",
      border: "1px solid var(--windagent-border-default)",
    },
    ghost: {
      background: "transparent",
      color: "var(--windagent-color-text-secondary)",
      border: "none",
    },
    danger: {
      background: "var(--windagent-color-danger-bg)",
      color: "var(--windagent-color-danger)",
      border: "1px solid var(--windagent-color-danger)",
    },
  };

  return (
    <button
      disabled={disabled || loading}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "var(--windagent-radius-md)",
        cursor: disabled || loading ? "not-allowed" : "pointer",
        opacity: disabled || loading ? 0.6 : 1,
        transition: "all var(--windagent-transition-fast)",
        fontFamily: "var(--windagent-font-sans)",
        userSelect: "none",
        ...sizeMap[size],
        ...variantStyles[variant],
        ...style,
      }}
      {...props}
    >
      {loading ? (
        <span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>⟳</span>
      ) : (
        icon
      )}
      {children}
    </button>
  );
}

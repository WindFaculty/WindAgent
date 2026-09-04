import React, { useEffect } from "react";
import { Card } from "./Card.tsx";
import { Button } from "./Button.tsx";

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: string;
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  maxWidth = "540px",
}: ModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "grid",
        placeItems: "center",
        backgroundColor: "rgba(0, 0, 0, 0.7)",
        backdropFilter: "blur(6px)",
        padding: "var(--windagent-space-4)",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <Card
        variant="glass"
        style={{
          width: "100%",
          maxWidth,
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--windagent-shadow-lg)",
          border: "1px solid var(--windagent-border-strong)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingBottom: "var(--windagent-space-3)",
            borderBottom: "1px solid var(--windagent-border-subtle)",
          }}
        >
          <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 600, color: "var(--windagent-color-text)" }}>
            {title}
          </h3>
          <Button variant="ghost" size="sm" onClick={onClose} style={{ padding: "4px 8px" }}>
            ✕
          </Button>
        </div>

        <div
          style={{
            overflowY: "auto",
            padding: "var(--windagent-space-4) 0",
            flex: 1,
          }}
        >
          {children}
        </div>

        {footer && (
          <div
            style={{
              paddingTop: "var(--windagent-space-3)",
              borderTop: "1px solid var(--windagent-border-subtle)",
              display: "flex",
              justifyContent: "flex-end",
              gap: "var(--windagent-space-2)",
            }}
          >
            {footer}
          </div>
        )}
      </Card>
    </div>
  );
}

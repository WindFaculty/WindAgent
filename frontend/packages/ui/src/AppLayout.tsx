import React from "react";

export function AppLayout({
  sidebar,
  header,
  children,
}: {
  sidebar: React.ReactNode;
  header: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        backgroundColor: "var(--windagent-color-bg)",
        color: "var(--windagent-color-text)",
        fontFamily: "var(--windagent-font-sans)",
      }}
    >
      {sidebar}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {header}
        <main
          style={{
            flex: 1,
            padding: "var(--windagent-space-6)",
            overflowY: "auto",
            maxWidth: "1600px",
            width: "100%",
            margin: "0 auto",
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

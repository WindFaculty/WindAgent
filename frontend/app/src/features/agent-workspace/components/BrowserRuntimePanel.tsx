import React from 'react';

interface BrowserRuntimePanelProps {
  browserSessionId?: string | null;
  screenshotUrl?: string | null;
  currentUrl?: string | null;
  title?: string | null;
}

export const BrowserRuntimePanel: React.FC<BrowserRuntimePanelProps> = ({
  browserSessionId,
  screenshotUrl,
  currentUrl,
  title,
}) => {
  if (!browserSessionId) {
    return (
      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '12px',
          padding: '16px',
          color: 'var(--text-muted, #9ca3af)',
          fontSize: '0.85rem',
        }}
      >
        No active browser runtime session for this agent workspace.
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
          Browser Runtime ({browserSessionId})
        </h4>
        <span style={{ fontSize: '0.7rem', color: '#10b981', fontWeight: 600 }}>EVENT-DRIVEN</span>
      </div>

      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)', overflowWrap: 'anywhere' }}>
        {title || currentUrl || 'No page loaded'}
      </div>

      {screenshotUrl ? (
        <img
          src={screenshotUrl}
          alt={`Browser session ${browserSessionId}`}
          style={{ width: '100%', borderRadius: '8px', border: '1px solid var(--border-color, #1f2937)' }}
        />
      ) : (
        <div
          style={{
            height: '120px',
            background: 'var(--bg-card, #1f2937)',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted, #9ca3af)',
            fontSize: '0.8rem',
          }}
        >
          No screenshot available
        </div>
      )}
    </div>
  );
};

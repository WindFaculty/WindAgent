import React from 'react';
import type { ConversationResource } from '@windagent/api-contracts';

interface CoordinatorPanelProps {
  conversation: ConversationResource;
}

export const CoordinatorPanel: React.FC<CoordinatorPanelProps> = ({ conversation }) => {
  return (
    <div
      style={{
        background: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
          {conversation.title || 'Multi-Agent Workspace'}
        </h3>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            borderRadius: '9999px',
            background: conversation.status === 'ACTIVE' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(156, 163, 175, 0.15)',
            color: conversation.status === 'ACTIVE' ? '#10b981' : '#9ca3af',
            fontWeight: 600,
          }}
        >
          {conversation.status}
        </span>
      </div>

      <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted, #9ca3af)', lineHeight: 1.5 }}>
        {conversation.objective || 'No active objective set for this conversation.'}
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px', fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>
        <div>
          <span style={{ textTransform: 'uppercase', fontSize: '0.7rem', display: 'block', opacity: 0.8 }}>Orchestrator</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{conversation.orchestrator_instance_id || 'System Coordinator'}</span>
        </div>
        <div>
          <span style={{ textTransform: 'uppercase', fontSize: '0.7rem', display: 'block', opacity: 0.8 }}>Plan Version</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{conversation.plan_version_id || 'v1.0'}</span>
        </div>
        <div>
          <span style={{ textTransform: 'uppercase', fontSize: '0.7rem', display: 'block', opacity: 0.8 }}>Version</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>v{conversation.version}</span>
        </div>
      </div>
    </div>
  );
};

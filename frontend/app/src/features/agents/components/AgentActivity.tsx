import React from 'react';
import { useAgentActivity } from '../hooks/useAgents';

interface AgentActivityProps {
  definitionId?: string | null;
}

export const AgentActivity: React.FC<AgentActivityProps> = ({ definitionId }) => {
  const { data: activity = [], isLoading } = useAgentActivity(definitionId || '');

  if (!definitionId) {
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
        Select an agent definition to view its execution history and activity logs.
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
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
          Activity Log ({definitionId})
        </h4>
        <span style={{ fontSize: '0.7rem', color: '#10b981' }}>TRUTHFUL LOG</span>
      </div>

      {isLoading ? (
        <div style={{ padding: '12px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          Loading activity logs...
        </div>
      ) : activity.length === 0 ? (
        <div style={{ padding: '12px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          No recent activity logged for this agent.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {activity.map((item) => (
            <div
              key={item.id}
              style={{
                background: 'var(--bg-card, #1f2937)',
                border: '1px solid var(--border-color, #1f2937)',
                borderRadius: '6px',
                padding: '10px',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#38bdf8' }}>
                  {item.action_type}
                </span>
                <span style={{ fontSize: '0.7rem', color: '#6b7280' }}>
                  {new Date(item.timestamp).toLocaleString()}
                </span>
              </div>
              <span style={{ fontSize: '0.8rem', color: '#e5e7eb' }}>
                {item.message}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

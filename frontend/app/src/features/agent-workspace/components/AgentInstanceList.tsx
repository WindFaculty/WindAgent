import React from 'react';
import type { AgentInstanceResource } from '@windagent/api-contracts';

interface AgentInstanceListProps {
  agents: AgentInstanceResource[];
  selectedAgentId?: string | null;
  onSelectAgent: (agentId: string) => void;
  onStopAgent: (agentId: string) => void;
}

export const AgentInstanceList: React.FC<AgentInstanceListProps> = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  onStopAgent,
}) => {
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
          Active Agent Instances ({agents.length})
        </h4>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {agents.length === 0 ? (
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>No agents running in this workspace.</p>
        ) : (
          agents.map((agent) => {
            const isSelected = agent.id === selectedAgentId;
            const isRunning = agent.status === 'RUNNING';
            return (
              <div
                key={agent.id}
                onClick={() => onSelectAgent(agent.id)}
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  border: `1px solid ${isSelected ? 'var(--color-primary, #3b82f6)' : 'var(--border-color, #1f2937)'}`,
                  background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'var(--bg-card, #1f2937)',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  transition: 'border-color 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary, #f9fafb)' }}>
                      {agent.id}
                    </span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        background: isRunning ? 'rgba(16, 185, 129, 0.2)' : 'rgba(156, 163, 175, 0.2)',
                        color: isRunning ? '#10b981' : '#9ca3af',
                        fontWeight: 600,
                      }}
                    >
                      {agent.status}
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
                    Model: {agent.canonical_model_id || 'unassigned'}
                    {agent.current_tool ? ` · Tool: ${agent.current_tool}` : ''}
                  </span>
                </div>

                {isRunning && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onStopAgent(agent.id);
                    }}
                    style={{
                      background: 'rgba(239, 68, 68, 0.15)',
                      color: '#ef4444',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                      fontWeight: 600,
                    }}
                  >
                    Stop
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

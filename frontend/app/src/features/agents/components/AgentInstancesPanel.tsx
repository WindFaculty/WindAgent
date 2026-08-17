import React from 'react';
import {
  useAgentInstances,
  useStartAgentInstance,
  useStopAgentInstance,
  useRestartAgentInstance,
} from '../hooks/useAgents';

export const AgentInstancesPanel: React.FC = () => {
  const { data: instances = [], isLoading, isError } = useAgentInstances();
  const startMutation = useStartAgentInstance();
  const stopMutation = useStopAgentInstance();
  const restartMutation = useRestartAgentInstance();

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
          Runtime Agent Instances ({instances.length})
        </h4>
      </div>

      {isLoading ? (
        <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          Loading agent instances...
        </div>
      ) : isError ? (
        <div style={{ padding: '16px', color: '#ef4444', fontSize: '0.85rem' }}>
          Failed to load instances
        </div>
      ) : instances.length === 0 ? (
        <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          No active runtime instances found.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {instances.map((inst) => {
            const isRunning = inst.status === 'RUNNING';
            return (
              <div
                key={inst.id}
                style={{
                  background: 'var(--bg-card, #1f2937)',
                  border: '1px solid var(--border-color, #1f2937)',
                  borderRadius: '8px',
                  padding: '12px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f9fafb' }}>
                      {inst.id}
                    </span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        padding: '1px 6px',
                        borderRadius: '4px',
                        background: isRunning ? 'rgba(16, 185, 129, 0.2)' : 'rgba(156, 163, 175, 0.2)',
                        color: isRunning ? '#10b981' : '#9ca3af',
                      }}
                    >
                      {inst.status}
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
                    Definition: {inst.definition_id || '—'} · Model: {inst.canonical_model_id || 'default'}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '6px' }}>
                  {isRunning ? (
                    <>
                      <button
                        type="button"
                        onClick={() => restartMutation.mutate(inst.id)}
                        disabled={restartMutation.isPending}
                        style={{
                          background: 'rgba(59, 130, 246, 0.15)',
                          color: '#3b82f6',
                          border: '1px solid rgba(59, 130, 246, 0.3)',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        Restart
                      </button>
                      <button
                        type="button"
                        onClick={() => stopMutation.mutate(inst.id)}
                        disabled={stopMutation.isPending}
                        style={{
                          background: 'rgba(239, 68, 68, 0.15)',
                          color: '#ef4444',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        Stop
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startMutation.mutate(inst.id)}
                      disabled={startMutation.isPending}
                      style={{
                        background: 'rgba(16, 185, 129, 0.15)',
                        color: '#10b981',
                        border: '1px solid rgba(16, 185, 129, 0.3)',
                        borderRadius: '4px',
                        padding: '4px 8px',
                        fontSize: '0.75rem',
                        cursor: 'pointer',
                        fontWeight: 600,
                      }}
                    >
                      Start
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

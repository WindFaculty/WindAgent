import React from 'react';
import { useAgentMetrics } from '../hooks/useAgents';

export const AgentRuntimeMetrics: React.FC = () => {
  const { data: metrics, isLoading, isError } = useAgentMetrics();

  if (isLoading) {
    return (
      <div style={{ padding: '12px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
        Loading agent runtime metrics...
      </div>
    );
  }

  if (isError || !metrics) {
    return (
      <div style={{ padding: '12px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
        Runtime metrics: Not available
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: '12px',
        width: '100%',
      }}
    >
      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '8px',
          padding: '12px',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Total Definitions
        </span>
        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)', marginTop: '4px' }}>
          {metrics.total}
        </div>
      </div>

      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '8px',
          padding: '12px',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Running Instances
        </span>
        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#10b981', marginTop: '4px' }}>
          {metrics.running}
        </div>
      </div>

      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '8px',
          padding: '12px',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Idle Instances
        </span>
        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#60a5fa', marginTop: '4px' }}>
          {metrics.idle}
        </div>
      </div>

      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '8px',
          padding: '12px',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Offline
        </span>
        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#9ca3af', marginTop: '4px' }}>
          {metrics.offline}
        </div>
      </div>

      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '8px',
          padding: '12px',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Active Tasks
        </span>
        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#eab308', marginTop: '4px' }}>
          {metrics.tasks_running}
        </div>
      </div>
    </div>
  );
};

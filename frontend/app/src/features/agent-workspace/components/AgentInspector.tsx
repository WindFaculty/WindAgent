import React from 'react';
import type { AgentInstanceResource } from '@windagent/api-contracts';

interface AgentInspectorProps {
  agent: AgentInstanceResource | null | undefined;
}

export const AgentInspector: React.FC<AgentInspectorProps> = ({ agent }) => {
  if (!agent) {
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
        Select an agent instance from the list to inspect runtime bindings and memory state.
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
          Agent Inspector: {agent.id}
        </h4>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            borderRadius: '4px',
            background: agent.status === 'RUNNING' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(156, 163, 175, 0.2)',
            color: agent.status === 'RUNNING' ? '#10b981' : '#9ca3af',
            fontWeight: 600,
          }}
        >
          {agent.status}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', fontSize: '0.8rem' }}>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Definition ID</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.definition_id || agent.agent_definition_id || '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Canonical Model</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.canonical_model_id || '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Route Lock ID</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.route_lock_id || '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Provider Binding</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.provider_binding_id || '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Assigned Task</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.assigned_task_id || 'None'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Current Tool</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.current_tool || 'Idle / Listening'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Started At</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>{agent.started_at ? new Date(agent.started_at).toLocaleString() : '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase' }}>Version</span>
          <span style={{ color: 'var(--text-primary, #f9fafb)', fontWeight: 500 }}>v{agent.version}</span>
        </div>
      </div>

      {agent.runtime_metadata && Object.keys(agent.runtime_metadata).length > 0 && (
        <div style={{ marginTop: '4px' }}>
          <span style={{ color: 'var(--text-muted, #9ca3af)', display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '4px' }}>
            Runtime Metadata
          </span>
          <pre
            style={{
              margin: 0,
              background: '#030712',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '0.75rem',
              color: '#60a5fa',
              overflowX: 'auto',
            }}
          >
            {JSON.stringify(agent.runtime_metadata, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

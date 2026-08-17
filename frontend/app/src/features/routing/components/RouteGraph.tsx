import React from 'react';
import type { RoutingGraphData } from '@windagent/api-contracts';

interface RouteGraphProps {
  graph?: RoutingGraphData;
  isLoading?: boolean;
}

export const RouteGraph: React.FC<RouteGraphProps> = ({ graph, isLoading }) => {
  if (isLoading || !graph) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted, #9ca3af)' }}>
        Loading routing topology graph...
      </div>
    );
  }

  const roleNodes = graph.nodes.filter((n) => n.type === 'role');
  const ruleNodes = graph.nodes.filter((n) => n.type === 'rule');
  const modelNodes = graph.nodes.filter((n) => n.type === 'model');

  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '10px',
        backgroundColor: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}
    >
      <div>
        <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
          Routing Topology Graph
        </h3>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>
          Visual mapping of Agent Roles → Evaluation Rules → Canonical Target Models.
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '24px',
          padding: '20px',
          backgroundColor: 'var(--bg-subpanel, #1e293b)',
          borderRadius: '8px',
          border: '1px solid var(--border-color, #334155)',
        }}
      >
        {/* Column 1: Roles */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <h4 style={{ margin: 0, fontSize: '0.8rem', color: '#c084fc', textTransform: 'uppercase', fontWeight: 700 }}>
            1. Agent Roles
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {roleNodes.map((n) => (
              <div
                key={n.id}
                style={{
                  padding: '10px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(139, 92, 246, 0.12)',
                  border: '1px solid rgba(139, 92, 246, 0.3)',
                  color: '#f3e8ff',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                }}
              >
                {n.label}
              </div>
            ))}
          </div>
        </div>

        {/* Column 2: Rules */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <h4 style={{ margin: 0, fontSize: '0.8rem', color: '#60a5fa', textTransform: 'uppercase', fontWeight: 700 }}>
            2. Policy Rules
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {ruleNodes.map((n) => (
              <div
                key={n.id}
                style={{
                  padding: '10px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(59, 130, 246, 0.12)',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  color: '#dbeafe',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                }}
              >
                {n.label}
              </div>
            ))}
          </div>
        </div>

        {/* Column 3: Canonical Models */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <h4 style={{ margin: 0, fontSize: '0.8rem', color: '#4ade80', textTransform: 'uppercase', fontWeight: 700 }}>
            3. Canonical Models
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {modelNodes.map((n) => (
              <div
                key={n.id}
                style={{
                  padding: '10px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(34, 197, 94, 0.12)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                  color: '#dcfce7',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                }}
              >
                {n.label}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

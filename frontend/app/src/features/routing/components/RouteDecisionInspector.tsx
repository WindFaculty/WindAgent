import React from 'react';
import type { RouteDecisionResource } from '@windagent/api-contracts';

interface RouteDecisionInspectorProps {
  decision: RouteDecisionResource;
}

export const RouteDecisionInspector: React.FC<RouteDecisionInspectorProps> = ({ decision }) => {
  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '10px',
        backgroundColor: 'rgba(59, 130, 246, 0.06)',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(34, 197, 94, 0.15)',
              color: '#4ade80',
              textTransform: 'uppercase',
            }}
          >
            ✓ Route Resolved
          </span>
          <h4 style={{ margin: '6px 0 0 0', fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
            Selected Model: <span style={{ color: '#38bdf8' }}>{decision.canonical_model_id}</span>
          </h4>
        </div>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)' }}>
          Lock ID: <code>{decision.route_lock_id}</code>
        </span>
      </div>

      {/* Decision Summary Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
          padding: '14px',
          backgroundColor: 'var(--bg-panel, #111827)',
          borderRadius: '8px',
          border: '1px solid var(--border-color, #1f2937)',
        }}
      >
        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Target Role</span>
          <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>{decision.requested_role}</span>
        </div>
        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Matched Rule</span>
          <span style={{ fontSize: '0.95rem', fontWeight: 600, color: '#60a5fa' }}>{decision.rule_name}</span>
        </div>
        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Selected Gateway</span>
          <span style={{ fontSize: '0.95rem', fontWeight: 600, color: '#4ade80' }}>{decision.selected_provider}</span>
        </div>
      </div>

      {/* Explanation Text */}
      <div>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Decision Rationale & Predicate Match
        </span>
        <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-secondary, #d1d5db)', lineHeight: 1.4 }}>
          {decision.reason}
        </p>
      </div>

      {/* Fallback Chain */}
      {decision.fallback_chain && decision.fallback_chain.length > 0 && (
        <div>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
            Fallback Failover Chain
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            <code style={{ fontSize: '0.78rem', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa' }}>
              {decision.canonical_model_id} (Primary)
            </code>
            {decision.fallback_chain.map((fb, idx) => (
              <React.Fragment key={fb}>
                <span style={{ color: 'var(--text-muted, #9ca3af)', fontSize: '0.8rem' }}>→</span>
                <code style={{ fontSize: '0.78rem', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24' }}>
                  {fb} (Fallback {idx + 1})
                </code>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

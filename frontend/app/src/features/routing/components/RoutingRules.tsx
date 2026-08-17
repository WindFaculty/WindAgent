import React from 'react';
import type { RoutingRuleResource } from '@windagent/api-contracts';

interface RoutingRulesProps {
  rules: RoutingRuleResource[];
  onSelectRule?: (rule: RoutingRuleResource) => void;
  onEditRule?: (rule: RoutingRuleResource) => void;
  onToggleEnabled?: (rule: RoutingRuleResource) => void;
  onCreateRule?: () => void;
}

export const RoutingRules: React.FC<RoutingRulesProps> = ({
  rules,
  onEditRule,
  onToggleEnabled,
  onCreateRule,
}) => {
  const getPriorityLabel = (priority: number) => {
    if (priority <= 0) return { text: 'Critical', bg: 'rgba(239, 68, 68, 0.15)', color: '#f87171' };
    if (priority <= 10) return { text: 'High', bg: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24' };
    if (priority <= 50) return { text: 'Normal', bg: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa' };
    return { text: 'Low', bg: 'rgba(156, 163, 175, 0.15)', color: '#9ca3af' };
  };

  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '10px',
        backgroundColor: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
            Routing Rules ({rules.length})
          </h3>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>
            Evaluated in ascending priority order (lower number = higher priority).
          </span>
        </div>
        {onCreateRule && (
          <button
            type="button"
            onClick={onCreateRule}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: 'var(--color-primary, #2563eb)',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.82rem',
              fontWeight: 600,
            }}
          >
            + Create Rule
          </button>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {rules.map((rule) => {
          const pInfo = getPriorityLabel(rule.priority);
          return (
            <div
              key={rule.id}
              style={{
                padding: '14px 16px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-subpanel, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '16px',
                opacity: rule.enabled ? 1 : 0.6,
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: '1 1 auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: pInfo.bg,
                      color: pInfo.color,
                      textTransform: 'uppercase',
                    }}
                  >
                    {pInfo.text} (P{rule.priority})
                  </span>
                  <span style={{ fontWeight: 700, color: 'var(--text-primary, #f9fafb)', fontSize: '0.95rem' }}>
                    {rule.name}
                  </span>
                  <code style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)' }}>{rule.id} (v{rule.version})</code>
                </div>

                <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary, #d1d5db)' }}>
                  {rule.description}
                </p>

                {/* Target Models */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem' }}>
                  <span style={{ color: 'var(--text-muted, #9ca3af)' }}>Primary:</span>
                  <code style={{ color: '#38bdf8', fontWeight: 600 }}>{rule.canonical_model_id}</code>
                  {rule.fallback_model_id && (
                    <>
                      <span style={{ color: 'var(--text-muted, #9ca3af)' }}>→ Fallback:</span>
                      <code style={{ color: '#fbbf24' }}>{rule.fallback_model_id}</code>
                    </>
                  )}
                </div>

                {/* Tags & Triggers */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '2px' }}>
                  {rule.agent_types.map((at) => (
                    <span
                      key={at}
                      style={{
                        fontSize: '0.7rem',
                        padding: '1px 6px',
                        borderRadius: '3px',
                        backgroundColor: 'rgba(139, 92, 246, 0.15)',
                        color: '#c084fc',
                      }}
                    >
                      Role: {at}
                    </span>
                  ))}
                  {rule.required_capabilities.map((rc) => (
                    <span
                      key={rc}
                      style={{
                        fontSize: '0.7rem',
                        padding: '1px 6px',
                        borderRadius: '3px',
                        backgroundColor: 'rgba(59, 130, 246, 0.15)',
                        color: '#60a5fa',
                      }}
                    >
                      Req: {rc}
                    </span>
                  ))}
                </div>
              </div>

              {/* Actions & Metrics */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px', flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {onToggleEnabled && (
                    <button
                      type="button"
                      onClick={() => onToggleEnabled(rule)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor: rule.enabled ? 'rgba(34, 197, 94, 0.15)' : 'rgba(156, 163, 175, 0.15)',
                        color: rule.enabled ? '#4ade80' : '#9ca3af',
                        border: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      {rule.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  )}
                  {onEditRule && (
                    <button
                      type="button"
                      onClick={() => onEditRule(rule)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor: 'var(--btn-secondary-bg, #374151)',
                        color: 'var(--text-primary, #f9fafb)',
                        border: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      Edit
                    </button>
                  )}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)' }}>
                  Success: <strong style={{ color: '#4ade80' }}>{rule.success_rate}%</strong> | Latency: <strong>{rule.avg_latency_ms}ms</strong>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

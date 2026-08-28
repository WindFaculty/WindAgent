import React from 'react';
import { Code2, ListOrdered, Zap, Shield, MoreVertical, Plus } from 'lucide-react';

export interface ModelRuleItem {
  id: string;
  name: string;
  providerModel: string;
  type: 'coding' | 'planning' | 'fast' | 'privacy' | 'custom';
  isPrimary: boolean;
}

/**
 * No hardcoded demo rules — routing rules are server authority.
 * Rules are loaded from GET /api/v3/providers/rules (model rules) and GET /api/v3/routing/rules.
 * Kept as empty array for backwards-compat imports.
 */
export const DEFAULT_MODEL_RULES: ModelRuleItem[] = [];

interface ModelRuleAssignmentPanelProps {
  rules?: ModelRuleItem[];
  onAddRule: () => void;
  onEditRule?: (rule: ModelRuleItem) => void;
}

export const ModelRuleAssignmentPanel: React.FC<ModelRuleAssignmentPanelProps> = ({
  rules = [],
  onAddRule,
  onEditRule,
}) => {
  const getRuleIcon = (type: ModelRuleItem['type']) => {
    switch (type) {
      case 'coding':
        return (
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(139, 92, 246, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#a78bfa',
              flexShrink: 0,
            }}
          >
            <Code2 size={16} />
          </div>
        );
      case 'planning':
        return (
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(59, 130, 246, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#60a5fa',
              flexShrink: 0,
            }}
          >
            <ListOrdered size={16} />
          </div>
        );
      case 'fast':
        return (
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(249, 115, 22, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fb923c',
              flexShrink: 0,
            }}
          >
            <Zap size={16} />
          </div>
        );
      case 'privacy':
      default:
        return (
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#34d399',
              flexShrink: 0,
            }}
          >
            <Shield size={16} />
          </div>
        );
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'rgba(11, 19, 38, 0.85)',
        borderRadius: '14px',
        border: '1px solid rgba(51, 65, 85, 0.45)',
        backdropFilter: 'blur(16px)',
        overflow: 'hidden',
        padding: '16px 18px',
        gap: '14px',
      }}
    >
      {/* Header */}
      <div>
        <h2
          style={{
            margin: 0,
            fontSize: '0.98rem',
            fontWeight: 700,
            color: 'var(--text-main, #f8fafc)',
            letterSpacing: '-0.01em',
          }}
        >
          Model Rule Assignment
        </h2>
        <p style={{ margin: '2px 0 0 0', fontSize: '0.72rem', color: '#64748b' }}>
          Map tasks to providers and models
        </p>
      </div>

      {/* Rules List — real DB data only, no demo fallback */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {rules.length === 0 && (
          <div style={{ padding: '16px', textAlign: 'center', color: '#64748b', fontSize: '0.78rem', border: '1px dashed rgba(51,65,85,0.5)', borderRadius: '8px' }}>
            No routing rules yet. Rules are stored in the durable model_routing_rules_v3 authority — add one via “Add Rule”.
          </div>
        )}
        {rules.map((rule) => (
          <div
            key={rule.id}
            onClick={() => onEditRule?.(rule)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 12px',
              borderRadius: '10px',
              backgroundColor: 'rgba(17, 24, 39, 0.65)',
              border: '1px solid rgba(51, 65, 85, 0.35)',
              cursor: 'pointer',
              transition: 'border-color 0.15s ease, transform 0.12s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(77, 142, 255, 0.4)';
              e.currentTarget.style.transform = 'translateX(2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(51, 65, 85, 0.35)';
              e.currentTarget.style.transform = 'translateX(0)';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
              {getRuleIcon(rule.type)}
              <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '0.80rem', fontWeight: 700, color: '#f8fafc' }}>
                    {rule.name}
                  </span>
                  {rule.isPrimary && (
                    <span
                      style={{
                        fontSize: '0.62rem',
                        fontWeight: 600,
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(139, 92, 246, 0.18)',
                        color: '#c4b5fd',
                      }}
                    >
                      Primary
                    </span>
                  )}
                </div>
                <span
                  style={{
                    fontSize: '0.70rem',
                    color: '#94a3b8',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    marginTop: '2px',
                  }}
                  title={rule.providerModel}
                >
                  {rule.providerModel}
                </span>
              </div>
            </div>

            <button
              type="button"
              style={{
                background: 'transparent',
                border: 'none',
                color: '#64748b',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <MoreVertical size={14} />
            </button>
          </div>
        ))}
      </div>

      {/* Add Rule Button */}
      <button
        type="button"
        onClick={onAddRule}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '6px',
          padding: '8px',
          borderRadius: '8px',
          backgroundColor: 'rgba(255, 255, 255, 0.03)',
          border: '1px dashed rgba(51, 65, 85, 0.6)',
          color: '#60a5fa',
          fontSize: '0.75rem',
          fontWeight: 600,
          cursor: 'pointer',
          transition: 'background-color 0.15s ease, border-color 0.15s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.08)';
          e.currentTarget.style.borderColor = '#3b82f6';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.03)';
          e.currentTarget.style.borderColor = 'rgba(51, 65, 85, 0.6)';
        }}
      >
        <Plus size={13} />
        <span>Add Rule</span>
      </button>
    </div>
  );
};

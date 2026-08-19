import React from 'react';
import { Code2, ListOrdered, Zap, Shield, MoreVertical, Plus } from 'lucide-react';

export interface ModelRuleItem {
  id: string;
  name: string;
  providerModel: string;
  type: 'coding' | 'planning' | 'fast' | 'privacy' | 'custom';
  isPrimary: boolean;
}

interface ModelRuleAssignmentPanelProps {
  rules: ModelRuleItem[];
  onAddRule: () => void;
  onEditRule?: (rule: ModelRuleItem) => void;
}

export const ModelRuleAssignmentPanel: React.FC<ModelRuleAssignmentPanelProps> = ({
  rules,
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
        border: '1px solid rgba(66, 71, 84, 0.4)',
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
            fontSize: '0.95rem',
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

      {/* Rules List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
              border: '1px solid rgba(66, 71, 84, 0.3)',
              cursor: 'pointer',
              transition: 'border-color 0.15s ease, transform 0.12s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(77, 142, 255, 0.4)';
              e.currentTarget.style.transform = 'translateX(2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(66, 71, 84, 0.3)';
              e.currentTarget.style.transform = 'translateX(0)';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
              {getRuleIcon(rule.type)}
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '0.78rem' }}>
                  {rule.name}
                </div>
                <div
                  style={{
                    fontSize: '0.68rem',
                    color: '#94a3b8',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {rule.providerModel}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
              {rule.isPrimary && (
                <span
                  style={{
                    fontSize: '0.68rem',
                    padding: '2px 7px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(139, 92, 246, 0.18)',
                    color: '#c4b5fd',
                    fontWeight: 600,
                  }}
                >
                  Primary
                </span>
              )}
              <button
                type="button"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '2px',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                <MoreVertical size={13} />
              </button>
            </div>
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
          backgroundColor: 'transparent',
          border: '1px dashed rgba(66, 71, 84, 0.6)',
          color: '#94a3b8',
          fontSize: '0.76rem',
          fontWeight: 600,
          cursor: 'pointer',
          transition: 'all 0.15s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#3b82f6';
          e.currentTarget.style.color = '#60a5fa';
          e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'rgba(66, 71, 84, 0.6)';
          e.currentTarget.style.color = '#94a3b8';
          e.currentTarget.style.backgroundColor = 'transparent';
        }}
      >
        <Plus size={13} />
        <span>Add Rule</span>
      </button>
    </div>
  );
};

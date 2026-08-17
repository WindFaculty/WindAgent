import React from 'react';
import type { ModelDefinitionResource } from '@windagent/api-contracts';
import { ModelCapabilities } from './ModelCapabilities';
import { ModelAvailability } from './ModelAvailability';

interface ModelDetailProps {
  model: ModelDefinitionResource;
  onClose: () => void;
}

export const ModelDetail: React.FC<ModelDetailProps> = ({ model, onClose }) => {
  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M tokens`;
    if (num >= 1000) return `${Math.round(num / 1000)}k tokens`;
    return `${num} tokens`;
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '720px',
          maxHeight: '90vh',
          overflowY: 'auto',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '12px',
          padding: '24px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(59, 130, 246, 0.15)',
                  color: '#60a5fa',
                }}
              >
                {model.vendor}
              </span>
              <ModelAvailability bindings={model.bindings} isActive={model.is_active} />
            </div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
              {model.name}
            </h2>
            <code style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>{model.id}</code>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted, #9ca3af)',
              cursor: 'pointer',
              fontSize: '1.2rem',
              padding: '4px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Description */}
        <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-secondary, #d1d5db)', lineHeight: 1.5 }}>
          {model.description}
        </p>

        {/* Capabilities */}
        <div>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
            Capabilities & Modalities
          </h4>
          <ModelCapabilities capabilities={model.capabilities} isLocal={model.is_local} />
        </div>

        {/* Spec Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '12px',
            padding: '16px',
            backgroundColor: 'var(--bg-subpanel, #1e293b)',
            borderRadius: '8px',
            border: '1px solid var(--border-color, #334155)',
          }}
        >
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Context Window</span>
            <span style={{ fontSize: '1rem', fontWeight: 700, color: '#38bdf8' }}>{formatTokens(model.context_window)}</span>
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Max Output</span>
            <span style={{ fontSize: '1rem', fontWeight: 700, color: '#38bdf8' }}>{formatTokens(model.max_output_tokens)}</span>
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Pricing (1M Tokens)</span>
            <span style={{ fontSize: '1rem', fontWeight: 700, color: '#4ade80' }}>
              {model.pricing ? `$${model.pricing.input_per_million} / $${model.pricing.output_per_million}` : 'Free / Local'}
            </span>
          </div>
        </div>

        {/* Benchmarks */}
        {model.benchmarks && Object.keys(model.benchmarks).length > 0 && (
          <div>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
              Benchmark Scores
            </h4>
            <div style={{ display: 'flex', gap: '12px' }}>
              {Object.entries(model.benchmarks).map(([bench, score]) => (
                <div
                  key={bench}
                  style={{
                    padding: '8px 12px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    border: '1px solid rgba(139, 92, 246, 0.25)',
                  }}
                >
                  <span style={{ fontSize: '0.75rem', color: '#c084fc', display: 'block' }}>{bench}</span>
                  <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#f3e8ff' }}>{score}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bound Physical Endpoints */}
        <div>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
            Bound Endpoints ({model.bindings.length})
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {model.bindings.map((b) => (
              <div
                key={b.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-subpanel, #1e293b)',
                  border: '1px solid var(--border-color, #334155)',
                  fontSize: '0.82rem',
                }}
              >
                <div>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>{b.provider_id.toUpperCase()}</span>
                  <span style={{ color: 'var(--text-muted, #9ca3af)', marginLeft: '8px' }}>({b.endpoint_id})</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <code style={{ fontSize: '0.78rem', color: '#94a3b8' }}>{b.provider_model_id}</code>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: b.is_active ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                      color: b.is_active ? '#4ade80' : '#f87171',
                      textTransform: 'uppercase',
                    }}
                  >
                    {b.equivalence_level}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '12px', borderTop: '1px solid var(--border-color, #1f2937)' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: 'var(--btn-secondary-bg, #374151)',
              color: 'var(--text-primary, #f9fafb)',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

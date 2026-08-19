import React, { useState } from 'react';
import type { RouteDecisionResource } from '@windagent/api-contracts';
import {
  CheckCircle2,
  Shield,
  Zap,
  ArrowRight,
  Copy,
  Check,
  Code2,
  Lock,
} from 'lucide-react';

interface RouteDecisionInspectorProps {
  decision: RouteDecisionResource;
}

export const RouteDecisionInspector: React.FC<RouteDecisionInspectorProps> = ({ decision }) => {
  const [copiedLock, setCopiedLock] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

  const handleCopyLock = () => {
    navigator.clipboard.writeText(decision.route_lock_id);
    setCopiedLock(true);
    setTimeout(() => setCopiedLock(false), 2000);
  };

  const getProviderTheme = (provider: string) => {
    const p = provider.toLowerCase();
    if (p.includes('anthropic')) return { color: '#fb923c', bg: 'rgba(251, 146, 60, 0.12)', border: 'rgba(251, 146, 60, 0.3)' };
    if (p.includes('google')) return { color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.12)', border: 'rgba(96, 165, 250, 0.3)' };
    if (p.includes('openai')) return { color: '#2dd4bf', bg: 'rgba(45, 212, 191, 0.12)', border: 'rgba(45, 212, 191, 0.3)' };
    if (p.includes('deepseek')) return { color: '#c084fc', bg: 'rgba(192, 132, 252, 0.12)', border: 'rgba(192, 132, 252, 0.3)' };
    if (p.includes('ollama') || p.includes('local')) return { color: '#4edea3', bg: 'rgba(78, 222, 163, 0.12)', border: 'rgba(78, 222, 163, 0.3)' };
    return { color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.12)', border: 'rgba(56, 189, 248, 0.3)' };
  };

  const pTheme = getProviderTheme(decision.selected_provider);

  return (
    <div
      style={{
        borderRadius: '14px',
        backgroundColor: 'rgba(19, 27, 46, 0.85)',
        border: '1px solid rgba(78, 222, 163, 0.35)',
        boxShadow: '0 8px 32px -4px rgba(0, 0, 0, 0.4), 0 0 20px -4px rgba(78, 222, 163, 0.15)',
        backdropFilter: 'blur(16px)',
        padding: '22px',
        display: 'flex',
        flexDirection: 'column',
        gap: '18px',
      }}
    >
      {/* Top Banner: Status + Model Resolved */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 800,
                padding: '3px 8px',
                borderRadius: '6px',
                backgroundColor: 'rgba(78, 222, 163, 0.15)',
                color: '#4edea3',
                border: '1px solid rgba(78, 222, 163, 0.3)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              <CheckCircle2 size={12} /> Route Resolved & Locked
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim, #8c909f)' }}>
              Evaluated at {new Date(decision.evaluated_at || Date.now()).toLocaleTimeString()}
            </span>
          </div>

          <h3 style={{ margin: '8px 0 0 0', fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main, #dae2fd)' }}>
            Target Model: <span style={{ color: pTheme.color }}>{decision.canonical_model_id}</span>
          </h3>
        </div>

        {/* Lock ID & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              backgroundColor: 'rgba(11, 19, 38, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.4)',
              fontSize: '0.75rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              color: 'var(--text-muted, #c2c6d6)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            <Lock size={12} color="#818cf8" />
            <span>{decision.route_lock_id}</span>
            <button
              type="button"
              onClick={handleCopyLock}
              style={{
                background: 'transparent',
                border: 'none',
                color: copiedLock ? '#4edea3' : 'var(--text-dim, #8c909f)',
                cursor: 'pointer',
                padding: 0,
              }}
              title="Copy Route Lock ID"
            >
              {copiedLock ? <Check size={12} /> : <Copy size={12} />}
            </button>
          </div>

          <button
            type="button"
            onClick={() => setShowRawJson(!showRawJson)}
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              backgroundColor: showRawJson ? 'rgba(77, 142, 255, 0.25)' : 'rgba(34, 42, 61, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              color: 'var(--text-main, #dae2fd)',
              fontSize: '0.75rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <Code2 size={12} /> {showRawJson ? 'Hide JSON' : 'Raw Trace'}
          </button>
        </div>
      </div>

      {/* 4-Stat Metric Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: '12px',
          padding: '14px 16px',
          backgroundColor: 'rgba(11, 19, 38, 0.75)',
          borderRadius: '10px',
          border: '1px solid rgba(66, 71, 84, 0.35)',
        }}
      >
        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 600, display: 'block' }}>
            Requested Role
          </span>
          <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#c084fc' }}>
            {decision.requested_role}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 600, display: 'block' }}>
            Matched Policy Rule
          </span>
          <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#60a5fa' }}>
            {decision.rule_name}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 600, display: 'block' }}>
            AI Gateway Provider
          </span>
          <span style={{ fontSize: '0.92rem', fontWeight: 700, color: pTheme.color }}>
            {decision.selected_provider}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 600, display: 'block' }}>
            Endpoint Status
          </span>
          <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#4edea3', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#4edea3' }} />
            Active Online
          </span>
        </div>
      </div>

      {/* Step-by-Step Decision Trace Timeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
          Decision Pipeline Execution Trace
        </span>
        <div
          style={{
            padding: '14px 16px',
            backgroundColor: 'rgba(11, 19, 38, 0.6)',
            borderRadius: '10px',
            border: '1px solid rgba(66, 71, 84, 0.3)',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', fontSize: '0.84rem' }}>
            <div style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: 'rgba(77, 142, 255, 0.15)', color: '#60a5fa', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: '0.72rem', fontWeight: 700 }}>
              1
            </div>
            <div>
              <strong style={{ color: 'var(--text-main, #dae2fd)' }}>Intent & Predicate Matching: </strong>
              <span style={{ color: 'var(--text-muted, #c2c6d6)' }}>
                Rule <code>{decision.rule_name}</code> ({decision.rule_id}) matched role &ldquo;{decision.requested_role}&rdquo;.
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', fontSize: '0.84rem' }}>
            <div style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: 'rgba(78, 222, 163, 0.15)', color: '#4edea3', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: '0.72rem', fontWeight: 700 }}>
              2
            </div>
            <div>
              <strong style={{ color: 'var(--text-main, #dae2fd)' }}>Rationale: </strong>
              <span style={{ color: 'var(--text-muted, #c2c6d6)' }}>{decision.reason}</span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', fontSize: '0.84rem' }}>
            <div style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: 'rgba(192, 132, 252, 0.15)', color: '#c084fc', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: '0.72rem', fontWeight: 700 }}>
              3
            </div>
            <div>
              <strong style={{ color: 'var(--text-main, #dae2fd)' }}>Gateway Allocation: </strong>
              <span style={{ color: 'var(--text-muted, #c2c6d6)' }}>
                Bound execution lock to <code>{decision.canonical_model_id}</code> via provider <code>{decision.selected_provider}</code>.
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Fallback Failover Chain */}
      {decision.fallback_chain && decision.fallback_chain.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
            Configured Fallback Failover Chain
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                backgroundColor: 'rgba(77, 142, 255, 0.15)',
                border: '1px solid rgba(77, 142, 255, 0.35)',
                color: '#adc6ff',
                fontSize: '0.8rem',
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
              }}
            >
              <Zap size={12} color="#60a5fa" />
              {decision.canonical_model_id} (Primary Target)
            </div>

            {decision.fallback_chain.map((fb, idx) => (
              <React.Fragment key={fb}>
                <ArrowRight size={14} color="var(--text-dim, #8c909f)" />
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 10px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(251, 191, 36, 0.12)',
                    border: '1px solid rgba(251, 191, 36, 0.35)',
                    color: '#fef08a',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  <Shield size={12} color="#fbbf24" />
                  {fb} (Fallback #{idx + 1})
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {/* Raw JSON Trace Viewer */}
      {showRawJson && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 600 }}>
            Raw RouteDecision JSON
          </span>
          <pre
            style={{
              padding: '14px',
              borderRadius: '8px',
              backgroundColor: 'rgba(6, 14, 32, 0.95)',
              border: '1px solid rgba(66, 71, 84, 0.4)',
              color: '#4edea3',
              fontSize: '0.78rem',
              fontFamily: 'var(--font-mono)',
              overflowX: 'auto',
              maxHeight: '200px',
              margin: 0,
            }}
          >
            {JSON.stringify(decision, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

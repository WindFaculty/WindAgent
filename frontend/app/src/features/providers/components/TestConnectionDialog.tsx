import React, { useState } from 'react';
import type { ProviderConnectionTestResult } from '@windagent/api-contracts';
import { useTestProviderConnection } from '../hooks/useProviders';

interface TestConnectionDialogProps {
  providerId: string;
  providerName: string;
  endpointId?: string;
  onClose: () => void;
}

export const TestConnectionDialog: React.FC<TestConnectionDialogProps> = ({
  providerId,
  providerName,
  endpointId,
  onClose,
}) => {
  const testMutation = useTestProviderConnection();
  const [result, setResult] = useState<ProviderConnectionTestResult | null>(null);

  const handleRunTest = async () => {
    try {
      const res = await testMutation.mutateAsync({ providerId, endpointId });
      setResult(res);
    } catch {
      // handled by mutation error state
    }
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
          maxWidth: '560px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '12px',
          padding: '24px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          flexDirection: 'column',
          gap: '18px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
              Test Provider Connection
            </h3>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted, #9ca3af)' }}>
              Target: <strong style={{ color: '#60a5fa' }}>{providerName}</strong> {endpointId && `(${endpointId})`}
            </span>
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
            }}
          >
            ✕
          </button>
        </div>

        <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary, #d1d5db)', lineHeight: 1.4 }}>
          Executes a server-side handshake, credential verification, and model discovery check against the provider gateway.
        </p>

        {/* Result Box */}
        {result && (
          <div
            style={{
              padding: '16px',
              borderRadius: '8px',
              backgroundColor: result.reachable ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
              border: `1px solid ${result.reachable ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span
                style={{
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  color: result.reachable ? '#4ade80' : '#f87171',
                  textTransform: 'uppercase',
                }}
              >
                {result.reachable ? '✓ Handshake Successful' : '✗ Handshake Failed'}
              </span>
              <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#38bdf8' }}>
                {result.latency_ms} ms
              </span>
            </div>

            <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-primary, #f9fafb)' }}>
              {result.message}
            </p>

            {result.model_discovery && result.model_discovery.length > 0 && (
              <div>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)', display: 'block', marginBottom: '4px' }}>
                  Discovered Models ({result.model_discovery.length}):
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {result.model_discovery.map((m) => (
                    <code
                      key={m}
                      style={{
                        fontSize: '0.72rem',
                        padding: '2px 6px',
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        borderRadius: '4px',
                        color: '#cbd5e1',
                      }}
                    >
                      {m}
                    </code>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {testMutation.isError && (
          <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#f87171', fontSize: '0.82rem' }}>
            Connection test request failed. Verify backend service health.
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color, #1f2937)' }}>
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
          <button
            type="button"
            onClick={handleRunTest}
            disabled={testMutation.isPending}
            style={{
              padding: '8px 18px',
              borderRadius: '6px',
              backgroundColor: 'var(--color-primary, #2563eb)',
              color: '#ffffff',
              border: 'none',
              cursor: testMutation.isPending ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600,
              opacity: testMutation.isPending ? 0.7 : 1,
            }}
          >
            {testMutation.isPending ? 'Pinging Gateway...' : 'Execute Test'}
          </button>
        </div>
      </div>
    </div>
  );
};

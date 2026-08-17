import React from 'react';
import type { ProviderEndpointResource } from '@windagent/api-contracts';
import { EndpointHealth } from './EndpointHealth';
import { CredentialStatus } from './CredentialStatus';

interface EndpointListProps {
  endpoints: ProviderEndpointResource[];
  onTestEndpoint?: (endpointId: string) => void;
}

export const EndpointList: React.FC<EndpointListProps> = ({ endpoints, onTestEndpoint }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {endpoints.map((ep) => (
        <div
          key={ep.id}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 16px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-subpanel, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary, #f9fafb)', fontSize: '0.9rem' }}>
                {ep.name}
              </span>
              <code style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)' }}>{ep.id}</code>
            </div>
            <code style={{ fontSize: '0.78rem', color: '#38bdf8' }}>{ep.base_url}</code>
            <CredentialStatus hasCredentials={ep.is_configured} credentialRef={ep.credential_reference} />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <EndpointHealth status={ep.status} latencyMs={ep.latency_ms} />
            {onTestEndpoint && (
              <button
                type="button"
                onClick={() => onTestEndpoint(ep.id)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(59, 130, 246, 0.12)',
                  color: '#60a5fa',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  cursor: 'pointer',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                }}
              >
                Test
              </button>
            )}
          </div>
        </div>
      ))}
      {endpoints.length === 0 && (
        <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          No endpoints configured for this provider.
        </div>
      )}
    </div>
  );
};

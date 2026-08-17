import React, { useState } from 'react';
import type { ProviderResource } from '@windagent/api-contracts';
import { EndpointList } from './EndpointList';
import { EndpointHealth } from './EndpointHealth';
import { TestConnectionDialog } from './TestConnectionDialog';

interface ProviderDetailProps {
  provider: ProviderResource;
}

export const ProviderDetail: React.FC<ProviderDetailProps> = ({ provider }) => {
  const [testingEndpointId, setTestingEndpointId] = useState<string | null>(null);
  const [showTestModal, setShowTestModal] = useState(false);

  return (
    <article
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
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '2px 6px',
                borderRadius: '4px',
                backgroundColor: 'rgba(59, 130, 246, 0.12)',
                color: '#60a5fa',
              }}
            >
              {provider.type}
            </span>
            <EndpointHealth status={provider.status} />
          </div>
          <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
            {provider.display_name}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
            <code style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>{provider.id}</code>
            {provider.website_url && (
              <a
                href={provider.website_url}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '0.75rem', color: '#38bdf8', textDecoration: 'none' }}
              >
                Docs / Website ↗
              </a>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            setTestingEndpointId(undefined as any);
            setShowTestModal(true);
          }}
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
          Test Gateway
        </button>
      </div>

      {/* Capabilities */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {provider.capabilities.map((cap) => (
          <span
            key={cap}
            style={{
              fontSize: '0.72rem',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              color: '#cbd5e1',
            }}
          >
            {cap}
          </span>
        ))}
      </div>

      {/* Physical Endpoints Section */}
      <div>
        <h4 style={{ margin: '0 0 8px 0', fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)', textTransform: 'uppercase' }}>
          Configured Endpoints ({provider.endpoints.length})
        </h4>
        <EndpointList
          endpoints={provider.endpoints}
          onTestEndpoint={(epId) => {
            setTestingEndpointId(epId);
            setShowTestModal(true);
          }}
        />
      </div>

      {/* Test Connection Dialog */}
      {showTestModal && (
        <TestConnectionDialog
          providerId={provider.id}
          providerName={provider.display_name}
          endpointId={testingEndpointId || undefined}
          onClose={() => setShowTestModal(false)}
        />
      )}
    </article>
  );
};

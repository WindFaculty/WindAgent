import React from 'react';
import { useProviders, useProvidersHealth } from '../hooks/useProviders';
import { ProviderDetail } from '../components/ProviderDetail';

export const ProvidersPage: React.FC = () => {
  const { data: providers = [], isLoading, error } = useProviders();
  const { data: healthMap } = useProvidersHealth();

  return (
    <div
      style={{
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        maxWidth: '1600px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, sans-serif)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
            Provider Gateways & Endpoints
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Manage upstream AI providers, inspect physical API endpoints, check network latency, and execute handshake tests.
          </p>
        </div>
      </div>

      {/* Global Health Banner */}
      {healthMap && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '12px',
          }}
        >
          {Object.entries(healthMap).map(([pId, h]) => (
            <div
              key={pId}
              style={{
                padding: '12px 16px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-panel, #111827)',
                border: '1px solid var(--border-color, #1f2937)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)', textTransform: 'capitalize' }}>
                  {pId}
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>
                  {h.endpoints_healthy}/{h.endpoints_total} endpoints online
                </span>
              </div>
              <span
                style={{
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  color: h.status === 'healthy' ? '#4ade80' : '#fbbf24',
                }}
              >
                {h.avg_latency_ms} ms
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Provider List */}
      {isLoading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted, #9ca3af)' }}>
          Loading provider registry...
        </div>
      ) : error ? (
        <div style={{ padding: '20px', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#f87171', borderRadius: '8px' }}>
          Failed to load providers.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {providers.map((provider) => (
            <ProviderDetail key={provider.id} provider={provider} />
          ))}
          {providers.length === 0 && (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted, #9ca3af)' }}>
              No providers registered.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

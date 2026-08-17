import React from 'react';
import type { ProviderStatus } from '@windagent/api-contracts';

interface EndpointHealthProps {
  status: ProviderStatus | string;
  latencyMs?: number;
}

export const EndpointHealth: React.FC<EndpointHealthProps> = ({ status, latencyMs }) => {
  const isHealthy = status === 'healthy' || status === 'ok';
  const isDegraded = status === 'degraded';

  const color = isHealthy ? '#4ade80' : isDegraded ? '#fbbf24' : '#f87171';
  const bg = isHealthy ? 'rgba(34, 197, 94, 0.12)' : isDegraded ? 'rgba(245, 158, 11, 0.12)' : 'rgba(239, 68, 68, 0.12)';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '5px',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.72rem',
          fontWeight: 700,
          backgroundColor: bg,
          color: color,
          border: `1px solid ${color}33`,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: color,
          }}
        />
        {status}
      </span>
      {latencyMs !== undefined && (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', fontWeight: 600 }}>
          {latencyMs}ms
        </span>
      )}
    </div>
  );
};

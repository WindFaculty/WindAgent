import React from 'react';
import type { ModelEndpointBinding } from '@windagent/api-contracts';

interface ModelAvailabilityProps {
  bindings: ModelEndpointBinding[];
  isActive: boolean;
}

export const ModelAvailability: React.FC<ModelAvailabilityProps> = ({ bindings, isActive }) => {
  const activeCount = bindings.filter((b) => b.is_active).length;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: isActive ? '#22c55e' : '#ef4444',
          boxShadow: isActive ? '0 0 8px #22c55e' : 'none',
        }}
      />
      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)' }}>
        {isActive ? `${activeCount} Endpoint${activeCount > 1 ? 's' : ''} Ready` : 'Offline'}
      </span>
    </div>
  );
};

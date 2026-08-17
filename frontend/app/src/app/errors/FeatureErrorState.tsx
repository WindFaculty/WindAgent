/**
 * FeatureErrorState — Component to display localized API and Capability errors.
 */

import React from 'react';
import type { ApiProblem } from '@windagent/api-contracts';

export interface FeatureErrorStateProps {
  title?: string;
  problem?: ApiProblem | null;
  error?: Error | null;
  onRetry?: () => void;
}

export const FeatureErrorState: React.FC<FeatureErrorStateProps> = ({
  title = 'Failed to load content',
  problem,
  error,
  onRetry,
}) => {
  const detail = problem?.detail || error?.message || 'An unexpected error occurred while communicating with the service.';
  const code = problem?.code || 'UNKNOWN_ERROR';
  const correlationId = problem?.correlation_id;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 16px',
        color: 'var(--studio-text, #f1f5f9)',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          maxWidth: '420px',
          backgroundColor: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px',
          padding: '20px',
        }}
      >
        <h4 style={{ margin: '0 0 6px 0', fontSize: '15px', color: '#f87171' }}>{title}</h4>
        <p style={{ margin: '0 0 10px 0', fontSize: '13px', color: '#cbd5e1', lineHeight: 1.4 }}>{detail}</p>
        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '14px' }}>
          Code: <code>{code}</code>
          {correlationId && (
            <span>
              {' '}| Trace: <code>{correlationId}</code>
            </span>
          )}
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            style={{
              backgroundColor: '#ef4444',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              padding: '6px 14px',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Retry Request
          </button>
        )}
      </div>
    </div>
  );
};

import React from 'react';

export interface BackendStatusProps {
  backendOnline: boolean | null;
  hermesOnline: boolean | null;
}

export const BackendStatus: React.FC<BackendStatusProps> = ({
  backendOnline,
  hermesOnline,
}) => {
  return (
    <div className="status-badges">
      <span className="badge-localhost">Localhost</span>

      {backendOnline === false ? (
        <span
          className="badge-localhost"
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            color: '#ef4444',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: '6px',
              height: '6px',
              backgroundColor: '#ef4444',
              borderRadius: '50%',
              boxShadow: '0 0 8px #ef4444',
              marginRight: '6px',
            }}
          />
          Backend: Offline
        </span>
      ) : (
        <span className="badge-connected">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
          </svg>
          Connected
        </span>
      )}

      {hermesOnline === null ? (
        <span className="badge-local-first" style={{ opacity: 0.6 }}>
          Hermes: Checking...
        </span>
      ) : hermesOnline ? (
        <span
          className="badge-localhost"
          style={{
            background: 'rgba(59, 130, 246, 0.08)',
            border: '1px solid rgba(59, 130, 246, 0.2)',
            color: '#3b82f6',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: '6px',
              height: '6px',
              backgroundColor: '#3b82f6',
              borderRadius: '50%',
              boxShadow: '0 0 8px #3b82f6',
              marginRight: '6px',
            }}
          />
          Hermes: Connected
        </span>
      ) : (
        <span
          className="badge-localhost"
          style={{
            background: 'rgba(148, 163, 184, 0.1)',
            border: '1px solid rgba(148, 163, 184, 0.3)',
            color: '#94a3b8',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: '6px',
              height: '6px',
              backgroundColor: '#94a3b8',
              borderRadius: '50%',
              marginRight: '6px',
            }}
          />
          Hermes: Offline
        </span>
      )}

      <span className="badge-local-first">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          style={{ marginRight: '2px' }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.5"
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
          />
        </svg>
        Local First
      </span>
    </div>
  );
};

export default BackendStatus;

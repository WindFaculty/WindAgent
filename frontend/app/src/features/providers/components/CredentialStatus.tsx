import React from 'react';

interface CredentialStatusProps {
  hasCredentials: boolean;
  credentialRef?: string;
}

export const CredentialStatus: React.FC<CredentialStatusProps> = ({ hasCredentials, credentialRef }) => {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.72rem',
          fontWeight: 600,
          backgroundColor: hasCredentials ? 'rgba(34, 197, 94, 0.12)' : 'rgba(239, 68, 68, 0.12)',
          color: hasCredentials ? '#4ade80' : '#f87171',
          border: hasCredentials ? '1px solid rgba(34, 197, 94, 0.25)' : '1px solid rgba(239, 68, 68, 0.25)',
        }}
      >
        <span style={{ fontSize: '0.75rem' }}>{hasCredentials ? '✓' : '✗'}</span>
        {hasCredentials ? 'Configured' : 'Missing Credentials'}
      </span>
      {credentialRef && (
        <code style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)', opacity: 0.8 }}>
          {credentialRef}
        </code>
      )}
    </div>
  );
};

/**
 * Desktop Endpoints Page — delegates fully to @windagent/app canonical ProvidersPage.
 * ZERO legacy provider endpoint calls.
 * All state backed by canonical /api/v3/providers authority.
 */
import React from 'react';
import { ProvidersPage as CanonicalProvidersPage } from '@windagent/app/src/features/providers';

export const Endpoints: React.FC = () => {
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <CanonicalProvidersPage />
    </div>
  );
};

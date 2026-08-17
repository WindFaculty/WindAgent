/**
 * Desktop Models Page — delegates fully to @windagent/app canonical ModelsPage.
 * ZERO legacy provider endpoint calls.
 * All state backed by canonical /api/v3/models authority.
 */
import React from 'react';
import { ModelsPage as CanonicalModelsPage } from '@windagent/app/src/features/models';

export interface ModelsProps {
  setActiveTab?: (tab: string) => void;
}

export const Models: React.FC<ModelsProps> = () => {
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <CanonicalModelsPage />
    </div>
  );
};

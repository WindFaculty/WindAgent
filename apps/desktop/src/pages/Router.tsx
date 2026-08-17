/**
 * Desktop Router Page — delegates fully to @windagent/app canonical RoutingPage.
 * ZERO coupled WebAudio synthesizer or game/easter-egg code.
 * ZERO legacy routing rule direct calls.
 * All state backed by canonical /api/v3/routing authority.
 */
import React from 'react';
import { RoutingPage as CanonicalRoutingPage } from '@windagent/app/src/features/routing';

export const Router: React.FC = () => {
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <CanonicalRoutingPage />
    </div>
  );
};

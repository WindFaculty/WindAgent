/**
 * Desktop Agents Page — delegates fully to @windagent/app canonical AgentsPage.
 * ZERO 5-second polling intervals. ZERO hardcoded uptime/latency/success metrics.
 * All state backed by /api/v3/agent-definitions, /api/v3/agent-instances, /api/v3/agents/metrics.
 */
import React from 'react';
import { AgentsPage as CanonicalAgentsPage } from '@windagent/app/src/features/agents';

export interface AgentsProps {
  setActiveTab?: (tab: string) => void;
}

export const Agents: React.FC<AgentsProps> = () => {
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <CanonicalAgentsPage />
    </div>
  );
};

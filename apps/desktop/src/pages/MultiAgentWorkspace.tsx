/**
 * Desktop MultiAgentWorkspace — delegates fully to @windagent/app canonical AgentWorkspacePage.
 * ZERO 2-second browser polling loops. ZERO fake states.
 * All state backed by /api/v3/conversations/{id} + WebSocket realtime stream.
 */
import React from 'react';
import { AgentWorkspacePage as CanonicalAgentWorkspacePage } from '@windagent/app/src/features/agent-workspace';

export interface MultiAgentWorkspaceProps {
  conversationId?: string;
}

export const MultiAgentWorkspace: React.FC<MultiAgentWorkspaceProps> = ({
  conversationId = 'conv-default-01',
}) => {
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <CanonicalAgentWorkspacePage conversationId={conversationId} />
    </div>
  );
};

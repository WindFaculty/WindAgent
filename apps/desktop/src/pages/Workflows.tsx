/**
 * Desktop Workflows Page — delegates fully to @windagent/app canonical WorkflowsPage.
 * ZERO mock datasets (kronos, release mock objects).
 * All state backed by /api/v3/workflows and /api/v3/workflow-runs with derived progress.
 */
import React from 'react';
import { WorkflowsPage as CanonicalWorkflowsPage } from '@windagent/app/src/features/workflows';

export const Workflows: React.FC = () => {
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <CanonicalWorkflowsPage />
    </div>
  );
};

import React, { useState } from 'react';
import { useWorkflowRuns, useTriggerWorkflowRun } from '../hooks/useWorkflows';
import type { WorkflowDefinitionResource, WorkflowRunResource } from '@windagent/api-contracts';

interface WorkflowRunsPanelProps {
  workflows: WorkflowDefinitionResource[];
  selectedRunId?: string | null;
  onSelectRun: (run: WorkflowRunResource) => void;
}

export const WorkflowRunsPanel: React.FC<WorkflowRunsPanelProps> = ({
  workflows,
  selectedRunId,
  onSelectRun,
}) => {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>('');
  const { data: runs = [], isLoading, isError } = useWorkflowRuns();
  const triggerMutation = useTriggerWorkflowRun();

  const handleTrigger = async (wfId: string) => {
    if (!wfId) return;
    try {
      const newRun = await triggerMutation.mutateAsync({ workflow_id: wfId });
      onSelectRun(newRun);
    } catch (e) {
      console.error('Trigger workflow failed:', e);
    }
  };

  return (
    <div
      style={{
        background: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
          Workflow Execution Runs ({runs.length})
        </h4>
      </div>

      <div style={{ display: 'flex', gap: '8px' }}>
        <select
          value={selectedWorkflowId}
          onChange={(e) => setSelectedWorkflowId(e.target.value)}
          style={{
            flex: 1,
            background: 'var(--bg-card, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            borderRadius: '6px',
            padding: '6px 10px',
            color: '#f9fafb',
            fontSize: '0.8rem',
          }}
        >
          <option value="">Select workflow to trigger...</option>
          {workflows.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={!selectedWorkflowId || triggerMutation.isPending}
          onClick={() => handleTrigger(selectedWorkflowId)}
          style={{
            background: 'var(--color-primary, #3b82f6)',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            padding: '6px 12px',
            fontSize: '0.75rem',
            fontWeight: 600,
            cursor: !selectedWorkflowId ? 'not-allowed' : 'pointer',
            opacity: !selectedWorkflowId ? 0.6 : 1,
          }}
        >
          {triggerMutation.isPending ? 'Triggering...' : 'Trigger Run'}
        </button>
      </div>

      {isLoading ? (
        <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          Loading workflow runs...
        </div>
      ) : isError ? (
        <div style={{ padding: '16px', color: '#ef4444', fontSize: '0.85rem' }}>
          Failed to load workflow runs
        </div>
      ) : runs.length === 0 ? (
        <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          No workflow runs recorded.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {runs.map((run) => {
            const isSelected = run.id === selectedRunId;
            const isRunning = run.status === 'RUNNING';
            const isCompleted = run.status === 'COMPLETED';
            const isFailed = run.status === 'FAILED';

            let statusColor = '#9ca3af';
            let statusBg = 'rgba(156, 163, 175, 0.15)';
            if (isRunning) {
              statusColor = '#eab308';
              statusBg = 'rgba(234, 179, 8, 0.15)';
            } else if (isCompleted) {
              statusColor = '#10b981';
              statusBg = 'rgba(16, 185, 129, 0.15)';
            } else if (isFailed) {
              statusColor = '#ef4444';
              statusBg = 'rgba(239, 68, 68, 0.15)';
            }

            return (
              <div
                key={run.id}
                onClick={() => onSelectRun(run)}
                style={{
                  background: isSelected ? 'rgba(59, 130, 246, 0.1)' : 'var(--bg-card, #1f2937)',
                  border: `1px solid ${isSelected ? 'var(--color-primary, #3b82f6)' : 'var(--border-color, #1f2937)'}`,
                  borderRadius: '8px',
                  padding: '12px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f9fafb' }}>
                    {run.workflow_name}
                  </span>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      padding: '1px 6px',
                      borderRadius: '4px',
                      background: statusBg,
                      color: statusColor,
                    }}
                  >
                    {run.status}
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
                  <span>Run ID: <code>{run.id}</code></span>
                  <span>Progress: <strong style={{ color: '#f9fafb' }}>{run.progress_percent}%</strong></span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

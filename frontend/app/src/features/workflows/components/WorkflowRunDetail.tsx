import React from 'react';
import {
  useWorkflowRun,
  useCancelWorkflowRun,
  useRetryWorkflowRun,
  usePauseWorkflowRun,
  useResumeWorkflowRun,
} from '../hooks/useWorkflows';

interface WorkflowRunDetailProps {
  runId?: string | null;
}

export const WorkflowRunDetail: React.FC<WorkflowRunDetailProps> = ({ runId }) => {
  const { data: run, isLoading, isError } = useWorkflowRun(runId || '');
  const cancelMutation = useCancelWorkflowRun();
  const retryMutation = useRetryWorkflowRun();
  const pauseMutation = usePauseWorkflowRun();
  const resumeMutation = useResumeWorkflowRun();

  if (!runId) {
    return (
      <div
        style={{
          background: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '12px',
          padding: '16px',
          color: 'var(--text-muted, #9ca3af)',
          fontSize: '0.85rem',
        }}
      >
        Select a workflow run to view step execution progress and control execution lifecycle.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
        Loading workflow run {runId}...
      </div>
    );
  }

  if (isError || !run) {
    return (
      <div style={{ padding: '16px', color: '#ef4444', fontSize: '0.85rem' }}>
        Failed to load run details.
      </div>
    );
  }

  const isRunning = run.status === 'RUNNING';
  const isPaused = run.status === 'PAUSED';
  const isFailed = run.status === 'FAILED';
  const isCancelled = run.status === 'CANCELLED';

  return (
    <div
      style={{
        background: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h4 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
            {run.workflow_name}
          </h4>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
            Run ID: <code>{run.id}</code> · Triggered by: <strong>{run.triggered_by}</strong>
          </span>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          {isRunning && (
            <>
              <button
                type="button"
                onClick={() => pauseMutation.mutate(run.id)}
                disabled={pauseMutation.isPending}
                style={{
                  background: 'rgba(234, 179, 8, 0.15)',
                  color: '#eab308',
                  border: '1px solid rgba(234, 179, 8, 0.3)',
                  borderRadius: '4px',
                  padding: '4px 8px',
                  fontSize: '0.75rem',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                Pause
              </button>
              <button
                type="button"
                onClick={() => cancelMutation.mutate(run.id)}
                disabled={cancelMutation.isPending}
                style={{
                  background: 'rgba(239, 68, 68, 0.15)',
                  color: '#ef4444',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '4px',
                  padding: '4px 8px',
                  fontSize: '0.75rem',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                Cancel
              </button>
            </>
          )}

          {isPaused && (
            <button
              type="button"
              onClick={() => resumeMutation.mutate(run.id)}
              disabled={resumeMutation.isPending}
              style={{
                background: 'rgba(16, 185, 129, 0.15)',
                color: '#10b981',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                borderRadius: '4px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Resume
            </button>
          )}

          {(isFailed || isCancelled) && (
            <button
              type="button"
              onClick={() => retryMutation.mutate(run.id)}
              disabled={retryMutation.isPending}
              style={{
                background: 'rgba(59, 130, 246, 0.15)',
                color: '#3b82f6',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                borderRadius: '4px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Retry Run
            </button>
          )}
        </div>
      </div>

      {/* Derived Progress Bar */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
          <span>Execution Progress</span>
          <span style={{ fontWeight: 600, color: '#f9fafb' }}>{run.progress_percent}%</span>
        </div>
        <div style={{ width: '100%', height: '8px', background: '#374151', borderRadius: '9999px', overflow: 'hidden' }}>
          <div
            style={{
              width: `${run.progress_percent}%`,
              height: '100%',
              background: isFailed ? '#ef4444' : '#3b82f6',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Steps List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#9ca3af' }}>Step Execution Details:</span>
        {run.steps.map((step, idx) => {
          let stepBg = '#1f2937';
          let stepColor = '#9ca3af';
          if (step.status === 'COMPLETED') {
            stepColor = '#10b981';
            stepBg = 'rgba(16, 185, 129, 0.1)';
          } else if (step.status === 'RUNNING') {
            stepColor = '#eab308';
            stepBg = 'rgba(234, 179, 8, 0.1)';
          } else if (step.status === 'FAILED') {
            stepColor = '#ef4444';
            stepBg = 'rgba(239, 68, 68, 0.1)';
          }

          return (
            <div
              key={step.id}
              style={{
                background: stepBg,
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                padding: '10px 12px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280' }}>
                  #{idx + 1}
                </span>
                <span style={{ fontSize: '0.85rem', color: '#f9fafb', fontWeight: 500 }}>
                  {step.step_name}
                </span>
              </div>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: 'rgba(0,0,0,0.2)',
                  color: stepColor,
                }}
              >
                {step.status}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

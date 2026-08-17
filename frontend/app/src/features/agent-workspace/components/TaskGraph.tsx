import React from 'react';
import type { TaskResource, TaskState } from '@windagent/api-contracts';

interface TaskGraphProps {
  tasks: TaskResource[];
  onCancelTask: (taskId: string) => void;
  onRetryTask: (taskId: string) => void;
}

const STATE_COLORS: Record<TaskState, { bg: string; text: string; border: string }> = {
  PENDING: { bg: 'rgba(156, 163, 175, 0.1)', text: '#9ca3af', border: '#4b5563' },
  READY: { bg: 'rgba(59, 130, 246, 0.1)', text: '#3b82f6', border: '#1d4ed8' },
  RUNNING: { bg: 'rgba(234, 179, 8, 0.1)', text: '#eab308', border: '#a16207' },
  BLOCKED: { bg: 'rgba(249, 115, 22, 0.1)', text: '#f97316', border: '#c2410c' },
  SUCCEEDED: { bg: 'rgba(16, 185, 129, 0.1)', text: '#10b981', border: '#047857' },
  FAILED: { bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444', border: '#b91c1c' },
  CANCELLED: { bg: 'rgba(107, 114, 128, 0.1)', text: '#6b7280', border: '#374151' },
};

export const TaskGraph: React.FC<TaskGraphProps> = ({ tasks, onCancelTask, onRetryTask }) => {
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
          Task Execution Graph ({tasks.length})
        </h4>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {tasks.length === 0 ? (
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>No tasks in graph.</p>
        ) : (
          tasks.map((task) => {
            const stateStyle = STATE_COLORS[task.state as TaskState] || STATE_COLORS.PENDING;
            const canCancel = task.state === 'RUNNING' || task.state === 'READY' || task.state === 'PENDING';
            const canRetry = task.state === 'FAILED' || task.state === 'CANCELLED';

            return (
              <div
                key={task.id}
                style={{
                  background: 'var(--bg-card, #1f2937)',
                  border: `1px solid ${stateStyle.border}`,
                  borderRadius: '8px',
                  padding: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary, #f9fafb)' }}>
                        {task.id}
                      </span>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          background: stateStyle.bg,
                          color: stateStyle.text,
                        }}
                      >
                        {task.state}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-primary, #e5e7eb)' }}>
                      {task.objective}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '6px' }}>
                    {canCancel && (
                      <button
                        type="button"
                        onClick={() => onCancelTask(task.id)}
                        style={{
                          background: 'rgba(239, 68, 68, 0.15)',
                          color: '#ef4444',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          borderRadius: '4px',
                          padding: '3px 8px',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        Cancel
                      </button>
                    )}
                    {canRetry && (
                      <button
                        type="button"
                        onClick={() => onRetryTask(task.id)}
                        style={{
                          background: 'rgba(59, 130, 246, 0.15)',
                          color: '#3b82f6',
                          border: '1px solid rgba(59, 130, 246, 0.3)',
                          borderRadius: '4px',
                          padding: '3px 8px',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
                  {task.assigned_agent_instance_id && (
                    <span>Assigned: <strong style={{ color: '#e5e7eb' }}>{task.assigned_agent_instance_id}</strong></span>
                  )}
                  {task.dependencies.length > 0 && (
                    <span>Depends on: <strong style={{ color: '#e5e7eb' }}>{task.dependencies.join(', ')}</strong></span>
                  )}
                  {task.concurrency_group && (
                    <span>Group: <strong style={{ color: '#e5e7eb' }}>{task.concurrency_group}</strong></span>
                  )}
                  <span>Attempts: <strong style={{ color: '#e5e7eb' }}>{task.attempts}</strong></span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

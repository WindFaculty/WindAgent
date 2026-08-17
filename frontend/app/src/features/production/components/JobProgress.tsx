/**
 * Phase 10 — JobProgress Component
 * Renders job state badge, progress bar, and attempt indicator.
 */
import React from 'react';
import type { ProductionJobResource, JobState } from '@windagent/api-contracts';

const STATE_COLORS: Record<JobState, string> = {
  PENDING: '#94a3b8',
  QUEUED: '#f59e0b',
  RUNNING: '#38bdf8',
  SUCCEEDED: '#22c55e',
  FAILED: '#ef4444',
  CANCELLED: '#6b7280',
  BLOCKED: '#f97316',
};

const STATE_LABELS: Record<JobState, string> = {
  PENDING: 'Chờ xử lý',
  QUEUED: 'Trong hàng đợi',
  RUNNING: 'Đang chạy...',
  SUCCEEDED: 'Thành công',
  FAILED: 'Thất bại',
  CANCELLED: 'Đã hủy',
  BLOCKED: 'Bị chặn',
};

interface JobProgressProps {
  job: ProductionJobResource;
}

export const JobProgress: React.FC<JobProgressProps> = ({ job }) => {
  const color = STATE_COLORS[job.state as JobState] ?? '#94a3b8';
  const label = STATE_LABELS[job.state as JobState] ?? job.state;

  return (
    <div className="job-progress">
      <div className="job-progress__header">
        <span
          className="job-progress__badge"
          style={{
            color,
            backgroundColor: `${color}22`,
            border: `1px solid ${color}44`,
          }}
        >
          {job.state === 'RUNNING' && <span className="job-progress__spinner" />}
          {label}
        </span>

        <span className="job-progress__id">#{job.job_id}</span>
        {job.attempt > 1 && (
          <span className="job-progress__attempt">Lần thử: {job.attempt}/{job.max_attempts}</span>
        )}
      </div>

      {(job.state === 'RUNNING' || job.state === 'QUEUED') && (
        <div className="job-progress__bar-wrapper">
          <div
            className="job-progress__bar"
            style={{ width: `${Math.max(5, job.progress_percent)}%`, backgroundColor: color }}
          />
          <span className="job-progress__percent">{job.progress_percent}%</span>
        </div>
      )}
    </div>
  );
};

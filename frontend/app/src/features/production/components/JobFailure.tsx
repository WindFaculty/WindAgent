/**
 * Phase 10 — JobFailure Component
 * Truthful failure & blocker UX displaying error code, stage, retryability, and suggestions.
 */
import React from 'react';
import type { ProductionJobResource } from '@windagent/api-contracts';

interface JobFailureProps {
  job: ProductionJobResource;
  onRetry?: () => void;
  isRetrying?: boolean;
}

const ERROR_DESCRIPTIONS: Record<string, { title: string; hint: string }> = {
  RENDER_OUT_OF_MEMORY: {
    title: 'Hết bộ nhớ đồ họa (VRAM)',
    hint: 'Cân nhắc giảm độ phân giải texture hoặc chia nhỏ cảnh render.',
  },
  MISSING_ASSET_DEPENDENCY: {
    title: 'Thiếu tài nguyên liên kết',
    hint: 'Kiểm tra lại character model hoặc texture bindings cho phân cảnh này.',
  },
  AUDIO_GENERATION_FAILED: {
    title: 'Lỗi tạo âm thanh',
    hint: 'Kiểm tra dịch vụ TTS hoặc giới hạn ký tự kịch bản.',
  },
  ANIMATION_TIMEOUT: {
    title: 'Hết thời gian tạo chuyển động',
    hint: 'Phân cảnh quá dài hoặc physics simulation quá phức tạp.',
  },
};

export const JobFailure: React.FC<JobFailureProps> = ({ job, onRetry, isRetrying }) => {
  if (job.state !== 'FAILED' && job.state !== 'BLOCKED') return null;

  const errInfo = job.error_code ? ERROR_DESCRIPTIONS[job.error_code] : null;

  return (
    <div className="job-failure">
      <div className="job-failure__header">
        <span className="job-failure__icon">⚠️</span>
        <div className="job-failure__info">
          <h4>{errInfo?.title ?? (job.state === 'BLOCKED' ? 'Tiến trình bị chặn' : 'Xử lý thất bại')}</h4>
          {job.error_code && <code className="job-failure__code">{job.error_code}</code>}
        </div>
      </div>

      <p className="job-failure__hint">
        {errInfo?.hint ?? 'Đã xảy ra lỗi trong quá trình thực thi engine. Vui lòng kiểm tra lại thiết lập và thử lại.'}
      </p>

      <div className="job-failure__footer">
        <span className="job-failure__stage">Giai đoạn: {job.failure_stage ?? job.job_type}</span>
        {job.retryable && onRetry && (
          <button
            className="btn btn--secondary btn--sm"
            onClick={onRetry}
            disabled={isRetrying || job.attempt >= job.max_attempts}
          >
            {isRetrying ? '⏳ Đang thử lại...' : `🔄 Thử lại (${job.attempt}/${job.max_attempts})`}
          </button>
        )}
      </div>
    </div>
  );
};

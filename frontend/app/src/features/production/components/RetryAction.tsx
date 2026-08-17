/**
 * Phase 10 — RetryAction Component
 */
import React from 'react';

interface RetryActionProps {
  onRetry: () => void;
  isPending: boolean;
  attempt?: number;
  maxAttempts?: number;
  disabled?: boolean;
}

export const RetryAction: React.FC<RetryActionProps> = ({
  onRetry,
  isPending,
  attempt = 1,
  maxAttempts = 3,
  disabled = false,
}) => {
  const canRetry = attempt < maxAttempts && !disabled;

  return (
    <button
      className="btn btn--secondary btn--sm retry-action"
      onClick={onRetry}
      disabled={!canRetry || isPending}
      title={canRetry ? `Thử lại (Lần ${attempt + 1}/${maxAttempts})` : 'Đã đạt giới hạn số lần thử lại'}
    >
      {isPending ? '⏳ Đang thử lại...' : `🔄 Thử lại (${attempt}/${maxAttempts})`}
    </button>
  );
};

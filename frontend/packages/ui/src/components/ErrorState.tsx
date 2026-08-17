import React from 'react';
import { EmptyState } from './EmptyState';
import { Button } from './Button';

export interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Đã xảy ra lỗi',
  message,
  onRetry,
  className = '',
}) => {
  return (
    <EmptyState
      title={title}
      description={message}
      className={className}
      action={
        onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Thử lại
          </Button>
        )
      }
    />
  );
};

export default ErrorState;

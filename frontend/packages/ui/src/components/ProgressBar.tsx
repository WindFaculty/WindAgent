import React from 'react';

export interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number; // 0 to 100
  max?: number;
  indeterminate?: boolean;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value = 0,
  max = 100,
  indeterminate = false,
  className = '',
  ...props
}) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div
      className={`ui-progress-track ${className}`.trim()}
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : value}
      aria-valuemin={0}
      aria-valuemax={max}
      {...props}
    >
      <div
        className={`ui-progress-fill ${indeterminate ? 'ui-progress-fill--indeterminate' : ''}`.trim()}
        style={{ width: indeterminate ? undefined : `${percentage}%` }}
      />
    </div>
  );
};

export default ProgressBar;

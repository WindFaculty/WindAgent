import React from 'react';

export interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number; // 0 to 100
  indeterminate?: boolean;
  color?: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value = 0,
  indeterminate = false,
  color,
  className = '',
  ...props
}) => {
  const fillStyle: React.CSSProperties = {
    ...(color ? { backgroundColor: color } : {}),
    ...(!indeterminate ? { width: `${Math.min(100, Math.max(0, value))}%` } : {}),
  };

  return (
    <div className={`ui-progress-track ${className}`.trim()} role="progressbar" aria-valuenow={indeterminate ? undefined : value} {...props}>
      <div
        className={`ui-progress-fill ${indeterminate ? 'ui-progress-fill--indeterminate' : ''}`.trim()}
        style={fillStyle}
      />
    </div>
  );
};

export default ProgressBar;

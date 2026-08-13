import React from 'react';
import { Badge, BadgeProps } from './Badge';

export type StudioStatus = 'RUNNING' | 'WAITING' | 'SUCCESS' | 'FAILED' | 'LOCKED' | 'PENDING' | 'IDLE';

export interface StatusBadgeProps extends Omit<BadgeProps, 'variant'> {
  status: StudioStatus | string;
  pulse?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  pulse,
  className = '',
  children,
  ...props
}) => {
  const normStatus = status.toUpperCase();

  let variant: BadgeProps['variant'] = 'default';
  let isPulsing = pulse ?? false;

  switch (normStatus) {
    case 'RUNNING':
    case 'IN_PROGRESS':
    case 'PENDING':
      variant = 'primary';
      if (pulse === undefined) isPulsing = true;
      break;
    case 'WAITING':
    case 'REQUIRES_APPROVAL':
    case 'REVISION_REQUESTED':
      variant = 'warning';
      if (pulse === undefined) isPulsing = true;
      break;
    case 'SUCCESS':
    case 'COMPLETED':
    case 'APPROVED':
    case 'READY_FOR_PRODUCTION':
      variant = 'success';
      break;
    case 'FAILED':
    case 'REJECTED':
    case 'ERROR':
      variant = 'danger';
      break;
    case 'LOCKED':
      variant = 'accent';
      break;
    default:
      variant = 'default';
      break;
  }

  const dotClass = `ui-status-dot ${isPulsing ? 'ui-status-dot--pulse' : ''}`.trim();

  return (
    <Badge
      variant={variant}
      icon={<span className={dotClass} />}
      className={`ui-status-badge ${className}`.trim()}
      {...props}
    >
      {children || status}
    </Badge>
  );
};

export default StatusBadge;

import React from 'react';

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = '',
  ...props
}) => {
  return (
    <div className={`ui-empty-state ${className}`.trim()} {...props}>
      {icon && <div className="ui-empty-state__icon">{icon}</div>}
      <div className="ui-empty-state__title">{title}</div>
      {description && <div className="ui-empty-state__description">{description}</div>}
      {action && <div className="ui-empty-state__action">{action}</div>}
    </div>
  );
};

export default EmptyState;

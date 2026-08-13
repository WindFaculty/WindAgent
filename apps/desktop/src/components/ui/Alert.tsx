import React from 'react';

export type AlertType = 'info' | 'success' | 'warning' | 'danger';

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  type?: AlertType;
  title?: string;
  icon?: React.ReactNode;
}

export const Alert: React.FC<AlertProps> = ({
  children,
  type = 'info',
  title,
  icon,
  className = '',
  ...props
}) => {
  return (
    <div className={`ui-alert ui-alert--${type} ${className}`.trim()} role="alert" {...props}>
      {icon && <span className="ui-alert__icon">{icon}</span>}
      <div>
        {title && <div style={{ fontWeight: 600, marginBottom: 2 }}>{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
};

export default Alert;

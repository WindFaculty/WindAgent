import React from 'react';

export type AlertType = 'info' | 'success' | 'warning' | 'danger';

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  type?: AlertType;
  title?: string;
  icon?: React.ReactNode;
}

export const Alert: React.FC<AlertProps> = ({
  type = 'info',
  title,
  icon,
  children,
  className = '',
  ...props
}) => {
  return (
    <div
      className={`ui-alert ui-alert--${type} ${className}`.trim()}
      role="alert"
      {...props}
    >
      {icon && <div className="ui-alert__icon" style={{ marginTop: 2 }}>{icon}</div>}
      <div className="ui-alert__content" style={{ flex: 1 }}>
        {title && <div style={{ fontWeight: 600, marginBottom: 2 }}>{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
};

export default Alert;

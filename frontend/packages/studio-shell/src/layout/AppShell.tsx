import React from 'react';

export interface AppShellProps extends React.HTMLAttributes<HTMLDivElement> {
  header?: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  header,
  className = '',
  ...props
}) => {
  return (
    <div className={`app-container ${className}`.trim()} {...props}>
      {header}
      {children}
    </div>
  );
};

export default AppShell;

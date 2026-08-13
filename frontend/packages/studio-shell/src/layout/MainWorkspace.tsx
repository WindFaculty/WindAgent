import React from 'react';

export interface MainWorkspaceProps extends React.HTMLAttributes<HTMLDivElement> {
  sidebar?: React.ReactNode;
}

export const MainWorkspace: React.FC<MainWorkspaceProps> = ({
  children,
  sidebar,
  className = '',
  ...props
}) => {
  return (
    <div className={`workspace-wrapper ${className}`.trim()} {...props}>
      {sidebar}
      <div className="main-content">{children}</div>
    </div>
  );
};

export default MainWorkspace;

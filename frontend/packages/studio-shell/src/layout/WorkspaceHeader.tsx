import React from 'react';

export interface WorkspaceHeaderProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title: React.ReactNode;
  breadcrumb?: React.ReactNode;
  actions?: React.ReactNode;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  title,
  breadcrumb,
  actions,
  className = '',
  ...props
}) => {
  return (
    <div className={`workspace-header ${className}`.trim()} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }} {...props}>
      <div>
        {breadcrumb && <div style={{ fontSize: '0.8rem', color: 'var(--studio-text-muted)', marginBottom: '4px' }}>{breadcrumb}</div>}
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>{title}</h2>
      </div>
      {actions && <div>{actions}</div>}
    </div>
  );
};

export default WorkspaceHeader;

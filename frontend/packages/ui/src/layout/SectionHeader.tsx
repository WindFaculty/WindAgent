import React from 'react';

export interface SectionHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  subtitle,
  action,
  className = '',
  ...props
}) => {
  return (
    <div className={`ui-section-header ${className}`.trim()} {...props}>
      <div>
        <div className="ui-section-header__title">{title}</div>
        {subtitle && <div className="ui-section-header__subtitle">{subtitle}</div>}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
};

export default SectionHeader;

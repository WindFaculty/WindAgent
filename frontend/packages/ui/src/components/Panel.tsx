import React from 'react';

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  header?: React.ReactNode;
  footer?: React.ReactNode;
}

export const Panel: React.FC<PanelProps> = ({
  children,
  header,
  footer,
  className = '',
  ...props
}) => {
  return (
    <div className={`ui-panel ${className}`.trim()} {...props}>
      {header && <div className="ui-panel__header">{header}</div>}
      <div className="ui-panel__content">{children}</div>
      {footer && <div className="ui-panel__footer">{footer}</div>}
    </div>
  );
};

export default Panel;

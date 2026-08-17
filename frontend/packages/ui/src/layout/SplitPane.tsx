import React from 'react';

export interface SplitPaneProps {
  left: React.ReactNode;
  right: React.ReactNode;
  leftWidth?: string | number;
  className?: string;
}

export const SplitPane: React.FC<SplitPaneProps> = ({
  left,
  right,
  leftWidth = '50%',
  className = '',
}) => {
  return (
    <div className={`ui-split-pane ${className}`.trim()}>
      <div style={{ width: leftWidth, height: '100%', overflow: 'auto', borderRight: '1px solid var(--studio-border)' }}>
        {left}
      </div>
      <div style={{ flex: 1, height: '100%', overflow: 'auto' }}>
        {right}
      </div>
    </div>
  );
};

export default SplitPane;

import React from 'react';

export interface GridProps extends React.HTMLAttributes<HTMLDivElement> {
  columns?: number | string;
  gap?: number | string;
  minWidth?: number | string;
}

export const Grid: React.FC<GridProps> = ({
  children,
  columns,
  gap = 16,
  minWidth,
  className = '',
  style,
  ...props
}) => {
  const gridTemplateColumns = minWidth
    ? `repeat(auto-fill, minmax(${typeof minWidth === 'number' ? `${minWidth}px` : minWidth}, 1fr))`
    : typeof columns === 'number'
    ? `repeat(${columns}, minmax(0, 1fr))`
    : columns;

  return (
    <div
      className={`ui-grid ${className}`.trim()}
      style={{
        gridTemplateColumns,
        gap,
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
};

export default Grid;

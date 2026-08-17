import React from 'react';

export interface StackProps extends React.HTMLAttributes<HTMLDivElement> {
  direction?: 'horizontal' | 'vertical';
  gap?: number | string;
  align?: React.CSSProperties['alignItems'];
  justify?: React.CSSProperties['justifyContent'];
  wrap?: boolean;
}

export const Stack: React.FC<StackProps> = ({
  children,
  direction = 'vertical',
  gap = 16,
  align,
  justify,
  wrap = false,
  className = '',
  style,
  ...props
}) => {
  return (
    <div
      className={`ui-stack ui-stack--${direction} ${className}`.trim()}
      style={{
        gap,
        alignItems: align,
        justifyContent: justify,
        flexWrap: wrap ? 'wrap' : 'nowrap',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
};

export default Stack;

import React from 'react';

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: string | number;
  height?: string | number;
  circle?: boolean;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width,
  height,
  circle = false,
  className = '',
  style,
  ...props
}) => {
  const customStyle: React.CSSProperties = {
    width: width ?? '100%',
    height: height ?? '1rem',
    borderRadius: circle ? '50%' : undefined,
    ...style,
  };

  return (
    <div
      className={`ui-skeleton ${className}`.trim()}
      style={customStyle}
      aria-hidden="true"
      {...props}
    />
  );
};

export default Skeleton;

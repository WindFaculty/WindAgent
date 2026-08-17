import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
  elevation?: 'flat' | 'raised' | 'overlay' | string;
}

export const Card: React.FC<CardProps> = ({
  children,
  interactive = false,
  elevation = 'raised',
  className = '',
  tabIndex,
  onKeyDown,
  ...props
}) => {
  const classNames = [
    'ui-card',
    elevation ? `ui-card--${elevation}` : '',
    interactive ? 'ui-card--interactive' : '',
    className,
  ].filter(Boolean).join(' ');


  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (interactive && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      props.onClick?.(e as unknown as React.MouseEvent<HTMLDivElement>);
    }
    onKeyDown?.(e);
  };

  return (
    <div
      className={classNames}
      tabIndex={interactive ? (tabIndex ?? 0) : tabIndex}
      onKeyDown={handleKeyDown}
      {...props}
    >
      {children}
    </div>
  );
};

export default Card;

import React from 'react';
import { Button, ButtonProps } from './Button';

export interface IconButtonProps extends Omit<ButtonProps, 'leftIcon' | 'rightIcon'> {
  'aria-label': string;
  icon: React.ReactNode;
}

export const IconButton: React.FC<IconButtonProps> = ({
  icon,
  className = '',
  'aria-label': ariaLabel,
  ...props
}) => {
  return (
    <Button
      className={`ui-icon-button ${className}`.trim()}
      aria-label={ariaLabel}
      title={props.title || ariaLabel}
      {...props}
    >
      {icon}
    </Button>
  );
};

export default IconButton;

import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export const Input: React.FC<InputProps> = ({
  className = '',
  error,
  ...props
}) => {
  return (
    <input
      className={`ui-input ${error ? 'ui-input--error' : ''} ${className}`.trim()}
      {...props}
    />
  );
};

export default Input;

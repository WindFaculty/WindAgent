import React from 'react';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export const Textarea: React.FC<TextareaProps> = ({
  className = '',
  error,
  rows = 3,
  ...props
}) => {
  return (
    <textarea
      rows={rows}
      className={`ui-textarea ${error ? 'ui-textarea--error' : ''} ${className}`.trim()}
      {...props}
    />
  );
};

export default Textarea;

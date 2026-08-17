import React from 'react';

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: React.ReactNode;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || (typeof label === 'string' ? `cb-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined);

  return (
    <label className={`ui-checkbox-container ${className}`.trim()} htmlFor={inputId}>
      <input
        type="checkbox"
        id={inputId}
        className="ui-checkbox"
        {...props}
      />
      {label && <span>{label}</span>}
    </label>
  );
};

export default Checkbox;

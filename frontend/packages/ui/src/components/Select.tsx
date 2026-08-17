import React from 'react';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  error?: boolean;
}

export const Select: React.FC<SelectProps> = ({
  options,
  className = '',
  error,
  children,
  ...props
}) => {
  return (
    <select
      className={`ui-select ${error ? 'ui-select--error' : ''} ${className}`.trim()}
      {...props}
    >
      {options ? options.map((opt) => (
        <option key={opt.value} value={opt.value} disabled={opt.disabled}>
          {opt.label}
        </option>
      )) : children}
    </select>
  );
};

export default Select;

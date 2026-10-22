import { useId } from 'react';
import type { BlueSelectProps } from './types';

export function BlueSelect({
  label,
  options,
  placeholder,
  helperText,
  error,
  className = '',
  id,
  ...rest
}: BlueSelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  const hasError = Boolean(error);

  return (
    <div className={`blue-select ${hasError ? 'blue-select--error' : ''} ${className}`.trim()}>
      {label ? (
        <label className="blue-select__label" htmlFor={selectId}>
          {label}
        </label>
      ) : null}
      <select id={selectId} className="blue-select__field" aria-invalid={hasError} {...rest}>
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <p className="blue-select__error" role="alert">
          {error}
        </p>
      ) : helperText ? (
        <p className="blue-select__helper">{helperText}</p>
      ) : null}
    </div>
  );
}

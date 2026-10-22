import { useId } from 'react';
import type { BlueInputProps } from './types';

export function BlueInput({
  label,
  helperText,
  error,
  className = '',
  id,
  ...rest
}: BlueInputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hasError = Boolean(error);

  return (
    <div className={`blue-input ${hasError ? 'blue-input--error' : ''} ${className}`.trim()}>
      {label ? (
        <label className="blue-input__label" htmlFor={inputId}>
          {label}
        </label>
      ) : null}
      <input id={inputId} className="blue-input__field" aria-invalid={hasError} {...rest} />
      {error ? (
        <p className="blue-input__error" role="alert">
          {error}
        </p>
      ) : helperText ? (
        <p className="blue-input__helper">{helperText}</p>
      ) : null}
    </div>
  );
}

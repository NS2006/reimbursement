import { useId } from 'react';
import type { BlueTextareaProps } from './types';

// Multi-line text input with label, helper and error text (BLUE BTextarea).
export function BlueTextarea({
  label,
  helperText,
  error,
  className = '',
  id,
  rows = 3,
  ...rest
}: BlueTextareaProps) {
  const autoId = useId();
  const textareaId = id ?? autoId;
  const hasError = Boolean(error);

  return (
    <div className={`blue-textarea ${hasError ? 'blue-textarea--error' : ''} ${className}`.trim()}>
      {label ? (
        <label className="blue-textarea__label" htmlFor={textareaId}>
          {label}
        </label>
      ) : null}
      <textarea id={textareaId} className="blue-textarea__field" rows={rows} aria-invalid={hasError} {...rest} />
      {error ? (
        <p className="blue-textarea__error" role="alert">
          {error}
        </p>
      ) : helperText ? (
        <p className="blue-textarea__helper">{helperText}</p>
      ) : null}
    </div>
  );
}

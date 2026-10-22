import type { BlueButtonProps } from './types';

export function BlueButton({
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  disabled,
  className = '',
  children,
  ...rest
}: BlueButtonProps) {
  const classes = [
    'blue-button',
    `blue-button--${variant}`,
    `blue-button--${size}`,
    fullWidth ? 'blue-button--block' : '',
    loading ? 'blue-button--loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button className={classes} disabled={disabled || loading} type="button" {...rest}>
      {loading ? <span className="blue-button__spinner" aria-hidden="true" /> : null}
      <span className="blue-button__label">{children}</span>
    </button>
  );
}

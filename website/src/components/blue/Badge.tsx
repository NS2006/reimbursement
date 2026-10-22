import type { BlueBadgeProps } from './types';

export function BlueBadge({
  variant = 'default',
  dot = false,
  children,
  className = '',
}: BlueBadgeProps) {
  return (
    <span className={`blue-badge blue-badge--${variant} ${className}`.trim()}>
      {dot ? <span className="blue-badge__dot" aria-hidden="true" /> : null}
      <span className="blue-badge__label">{children}</span>
    </span>
  );
}

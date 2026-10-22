import type { BlueEmptyStateProps } from './types';

// Shown where data would be when there is none (BLUE BEmptyState), with an optional way out.
export function BlueEmptyState({ title, children, action, className = '' }: BlueEmptyStateProps) {
  return (
    <div className={`blue-empty-state ${className}`.trim()}>
      <p className="blue-empty-state__title">{title}</p>
      {children ? <div className="blue-empty-state__description">{children}</div> : null}
      {action ? <div className="blue-empty-state__action">{action}</div> : null}
    </div>
  );
}

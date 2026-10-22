import { t } from '../../app/i18n';
import type { BlueTagProps } from './types';

// A label chip (BLUE BTag), for example a field name; with onRemove it gets a remove (×) button.
export function BlueTag({
  variant = 'default',
  onRemove,
  removeLabel = t('blue.remove'),
  title,
  children,
  className = '',
}: BlueTagProps) {
  return (
    <span className={`blue-tag blue-tag--${variant} ${className}`.trim()} title={title}>
      <span className="blue-tag__label">{children}</span>
      {onRemove ? (
        <button type="button" className="blue-tag__remove" aria-label={removeLabel} onClick={onRemove}>
          ×
        </button>
      ) : null}
    </span>
  );
}

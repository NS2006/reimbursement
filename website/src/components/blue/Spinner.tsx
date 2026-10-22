import { t } from '../../app/i18n';
import type { BlueSpinnerProps } from './types';

export function BlueSpinner({ size = 'md', label, className = '' }: BlueSpinnerProps) {
  return (
    <span className={`blue-spinner blue-spinner--${size} ${className}`.trim()} role="status">
      <span className="blue-spinner__circle" aria-hidden="true" />
      {label ? <span>{label}</span> : <span className="blue-visually-hidden">{t('blue.loading')}</span>}
    </span>
  );
}

import { t } from '../../app/i18n';
import type { BlueAlertProps } from './types';

export function BlueAlert({
  variant = 'info',
  title,
  onDismiss,
  children,
  className = '',
}: BlueAlertProps) {
  return (
    <div className={`blue-alert blue-alert--${variant} ${className}`.trim()} role="alert">
      <div className="blue-alert__content">
        {title ? <p className="blue-alert__title">{title}</p> : null}
        <div className="blue-alert__message">{children}</div>
      </div>
      {onDismiss ? (
        <button
          type="button"
          className="blue-alert__dismiss"
          onClick={onDismiss}
          aria-label={t('blue.dismissAlert')}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}

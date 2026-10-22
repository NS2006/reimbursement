import { t } from '../../app/i18n';
import type { BlueBreadcrumbProps } from './types';

// Where the current page sits (BLUE BBreadcrumb). Items with an href are links; the last item is the current page.
export function BlueBreadcrumb({ items, onNavigate, className = '' }: BlueBreadcrumbProps) {
  return (
    <nav className={`blue-breadcrumb ${className}`.trim()} aria-label={t('blue.breadcrumb')}>
      <ol className="blue-breadcrumb__items">
        {items.map((item, index) => {
          const current = index === items.length - 1;
          return (
            <li key={item.key} className="blue-breadcrumb__item">
              {item.href && !current ? (
                <a
                  href={item.href}
                  className="blue-breadcrumb__link"
                  onClick={onNavigate ? (event) => onNavigate(item, event) : undefined}
                >
                  {item.label}
                </a>
              ) : (
                <span className="blue-breadcrumb__current" aria-current={current ? 'page' : undefined}>
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

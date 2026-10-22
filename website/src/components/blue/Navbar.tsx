import { t } from '../../app/i18n';
import type { BlueNavbarProps } from './types';

// Top bar of the app (BLUE BNavbar): logo, main links, optional middle content and actions on the right.
// It only shows links; what a click does (e.g. change the page without a reload) is up to onNavigate.
export function BlueNavbar({
  logo,
  items = [],
  activeKey,
  onNavigate,
  actions,
  children,
  ariaLabel = t('blue.mainNav'),
  className = '',
}: BlueNavbarProps) {
  return (
    <header className={`blue-navbar ${className}`.trim()}>
      {logo ? <div className="blue-navbar__logo">{logo}</div> : null}
      {items.length > 0 ? (
        <nav className="blue-navbar__nav" aria-label={ariaLabel}>
          <ul className="blue-navbar__items">
            {items.map((item) => {
              const active = item.key === activeKey;
              return (
                <li key={item.key}>
                  <a
                    href={item.href}
                    className={`blue-navbar__link ${active ? 'blue-navbar__link--active' : ''}`.trim()}
                    aria-current={active ? 'page' : undefined}
                    onClick={onNavigate ? (event) => onNavigate(item, event) : undefined}
                  >
                    {item.label}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>
      ) : null}
      {children ? <div className="blue-navbar__content">{children}</div> : null}
      {actions ? <div className="blue-navbar__actions">{actions}</div> : null}
    </header>
  );
}

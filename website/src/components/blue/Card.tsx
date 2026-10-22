import type { BlueCardProps } from './types';

export function BlueCard({
  title,
  header,
  footer,
  bordered = true,
  hoverable = false,
  children,
  className = '',
}: BlueCardProps) {
  const classes = [
    'blue-card',
    bordered ? 'blue-card--bordered' : '',
    hoverable ? 'blue-card--hoverable' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section className={classes}>
      {header ?? (title ? <header className="blue-card__header">{title}</header> : null)}
      <div className="blue-card__body">{children}</div>
      {footer ? <footer className="blue-card__footer">{footer}</footer> : null}
    </section>
  );
}

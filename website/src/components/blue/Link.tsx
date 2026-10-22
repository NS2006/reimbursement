import type { BlueLinkProps } from './types';

// An inline link (BLUE BLink). external opens it in a new tab.
export function BlueLink({ external = false, className = '', children, ...rest }: BlueLinkProps) {
  return (
    <a
      className={`blue-link ${className}`.trim()}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      {...rest}
    >
      {children}
    </a>
  );
}

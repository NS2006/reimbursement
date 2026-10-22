import type { BlueAvatarProps } from './types';

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('');
}

// A person's picture, or their initials when there is none (BLUE BAvatar).
export function BlueAvatar({ name, src, size = 'md', className = '' }: BlueAvatarProps) {
  const classes = `blue-avatar blue-avatar--${size} ${className}`.trim();
  if (src) return <img className={classes} src={src} alt={name} />;
  return (
    <span className={classes} aria-hidden="true">
      {initials(name)}
    </span>
  );
}

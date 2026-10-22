import { useRef, type KeyboardEvent } from 'react';
import type { BlueTabsProps } from './types';

// Switch between related views or filters (BLUE BTabs). Arrow keys, Home and End move between tabs.
export function BlueTabs({ items, activeKey, onChange, ariaLabel, controls, className = '' }: BlueTabsProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const enabled = items.filter((item) => !item.disabled);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = enabled.findIndex((item) => item.key === activeKey);
    const next = {
      ArrowRight: enabled[(index + 1) % enabled.length],
      ArrowLeft: enabled[(index - 1 + enabled.length) % enabled.length],
      Home: enabled[0],
      End: enabled[enabled.length - 1],
    }[event.key];
    if (!next) return;
    event.preventDefault();
    onChange(next.key);
    listRef.current?.querySelector<HTMLButtonElement>(`[data-key="${CSS.escape(next.key)}"]`)?.focus();
  }

  return (
    <div
      ref={listRef}
      className={`blue-tabs ${className}`.trim()}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
    >
      {items.map((item) => {
        const active = item.key === activeKey;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            data-key={item.key}
            className={`blue-tabs__tab ${active ? 'blue-tabs__tab--active' : ''}`.trim()}
            aria-selected={active}
            aria-controls={controls}
            tabIndex={active ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.key)}
          >
            <span>{item.label}</span>
            {item.count !== undefined ? <span className="blue-tabs__count">{item.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

import { t } from '../../app/i18n';
import type { BluePaginationProps } from './types';

type PageSlot = number | 'gap-start' | 'gap-end';

/** The first and last page, the current one and its neighbours; a gap ("…") where pages are left out. */
function pageSlots(current: number, pages: number): PageSlot[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  let from = Math.max(2, Math.min(current - 1, pages - 4));
  let to = Math.min(pages - 1, Math.max(current + 1, 5));
  // A gap would hide a single page: show that page instead.
  if (from === 3) from = 2;
  if (to === pages - 2) to = pages - 1;
  const middle = Array.from({ length: to - from + 1 }, (_, index) => from + index);
  return [1, ...(from > 2 ? ['gap-start' as const] : []), ...middle, ...(to < pages - 1 ? ['gap-end' as const] : []), pages];
}

function Chevron({ flip = false }: { flip?: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" style={flip ? { transform: 'scaleX(-1)' } : undefined}>
      <path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Paged navigation for lists and tables (BLUE BPagination): previous / next and the page numbers.
export function BluePagination({
  current,
  total,
  pageSize,
  onChange,
  ariaLabel = t('blue.pages'),
  className = '',
}: BluePaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.min(Math.max(1, current), pages);

  return (
    <nav className={`blue-pagination ${className}`.trim()} aria-label={ariaLabel}>
      <button
        type="button"
        className="blue-pagination__button"
        aria-label={t('blue.previousPage')}
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        <Chevron />
      </button>
      {pageSlots(page, pages).map((slot) =>
        typeof slot === 'number' ? (
          <button
            key={slot}
            type="button"
            className={`blue-pagination__button ${slot === page ? 'blue-pagination__button--current' : ''}`.trim()}
            aria-label={`Page ${slot}`}
            aria-current={slot === page ? 'page' : undefined}
            onClick={() => onChange(slot)}
          >
            {slot}
          </button>
        ) : (
          <span key={slot} className="blue-pagination__gap" aria-hidden="true">
            …
          </span>
        ),
      )}
      <button
        type="button"
        className="blue-pagination__button"
        aria-label={t('blue.nextPage')}
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        <Chevron flip />
      </button>
    </nav>
  );
}

import { t } from '../../app/i18n';
import type { KeyboardEvent, MouseEvent, ReactNode } from 'react';
import type {
  BlueSortDirection,
  BlueTableColumn,
  BlueTableFooterRow,
  BlueTableProps,
  BlueTableSort,
} from './types';

const INTERACTIVE = 'a, button, input, select, textarea, label';

function cellValue<T>(row: T, column: BlueTableColumn<T>, index: number): ReactNode {
  if (column.render) return column.render(row, index);
  const value = (row as Record<string, unknown>)[column.key];
  return value === null || value === undefined || value === '' ? '-' : String(value);
}

function columnLabel<T>(column: BlueTableColumn<T>): string | undefined {
  return column.label ?? (typeof column.header === 'string' ? column.header : undefined);
}

const ARIA_SORT = { asc: 'ascending', desc: 'descending' } as const;

/** Up and down arrows; the one for the current direction is drawn darker. */
function SortIcon({ direction }: { direction?: BlueSortDirection }) {
  return (
    <svg className="blue-table__sort-icon" viewBox="0 0 10 14" width="10" height="14" aria-hidden="true">
      <path d="M5 1 9 5.5H1z" className={direction === 'asc' ? 'blue-table__sort-arrow--on' : undefined} />
      <path d="M5 13 1 8.5h8z" className={direction === 'desc' ? 'blue-table__sort-arrow--on' : undefined} />
    </svg>
  );
}

// Rows and columns of data (BLUE BTable). Each column says how to show its cell; the table scrolls
// sideways on narrow screens instead of squeezing the columns, or becomes one card per row (stackOnMobile).
// Sortable columns get a sort button in their header; the caller keeps the sort and sorts the data.
export function BlueTable<T>({
  columns,
  data,
  rowKey,
  empty,
  onRowClick,
  rowClassName,
  caption,
  dense = false,
  sort,
  onSortChange,
  stackOnMobile = false,
  footer,
  className = '',
}: BlueTableProps<T>) {
  function onClick(row: T, event: MouseEvent<HTMLTableRowElement>) {
    if ((event.target as HTMLElement).closest(INTERACTIVE)) return;
    onRowClick?.(row);
  }

  function onKeyDown(row: T, event: KeyboardEvent<HTMLTableRowElement>) {
    if (event.target !== event.currentTarget || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    onRowClick?.(row);
  }

  function nextSort(column: BlueTableColumn<T>): BlueTableSort {
    if (sort?.key !== column.key) return { key: column.key, direction: column.firstSortDirection ?? 'asc' };
    return { key: column.key, direction: sort.direction === 'asc' ? 'desc' : 'asc' };
  }

  const classes = [
    'blue-table',
    dense ? 'blue-table--dense' : '',
    stackOnMobile ? 'blue-table--stack' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes}>
      <table className="blue-table__table">
        {caption ? <caption className="blue-visually-hidden">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => {
              const onSort = column.sortable ? onSortChange : undefined;
              const direction = sort?.key === column.key ? sort.direction : undefined;
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={`blue-table__head blue-table__cell--${column.align ?? 'left'}`}
                  style={column.width ? { width: column.width } : undefined}
                  aria-sort={direction ? ARIA_SORT[direction] : undefined}
                  data-sortable={onSort ? '' : undefined}
                >
                  {onSort ? (
                    <button
                      type="button"
                      className={`blue-table__sort ${direction ? 'blue-table__sort--active' : ''}`.trim()}
                      onClick={() => onSort(nextSort(column))}
                    >
                      <span>{column.header}</span>
                      <SortIcon direction={direction} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td className="blue-table__empty" colSpan={columns.length}>
                {empty ?? t('blue.nothingToShow')}
              </td>
            </tr>
          ) : (
            data.map((row, index) => {
              const rowClasses = [
                'blue-table__row',
                onRowClick ? 'blue-table__row--clickable' : '',
                rowClassName?.(row) ?? '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <tr
                  key={rowKey(row, index)}
                  className={rowClasses}
                  onClick={onRowClick ? (event) => onClick(row, event) : undefined}
                  onKeyDown={onRowClick ? (event) => onKeyDown(row, event) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                >
                  {columns.map((column) => {
                    const extra =
                      typeof column.cellClassName === 'function' ? column.cellClassName(row) : column.cellClassName;
                    const cellClasses = [
                      'blue-table__cell',
                      `blue-table__cell--${column.align ?? 'left'}`,
                      column.nowrap ? 'blue-table__cell--nowrap' : '',
                      extra ?? '',
                    ]
                      .filter(Boolean)
                      .join(' ');
                    return (
                      <td
                        key={column.key}
                        className={cellClasses}
                        title={column.cellTitle?.(row)}
                        data-label={stackOnMobile ? columnLabel(column) : undefined}
                      >
                        {cellValue(row, column, index)}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
        {footer && footer.length > 0 && data.length > 0 ? (
          <tfoot>
            {footer.map((row) => (
              <FooterRow key={row.key} row={row} columns={columns} stackOnMobile={stackOnMobile} />
            ))}
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

/** A footer row: its label fills the columns before its first value, then one cell per column. In the stacked
 * layout a row with one value shows as one line, "label  value"; a row with more lists each value with its column
 * name under the label. */
function FooterRow<T>({
  row,
  columns,
  stackOnMobile,
}: {
  row: BlueTableFooterRow;
  columns: BlueTableColumn<T>[];
  stackOnMobile: boolean;
}) {
  const span = Math.max(1, columns.findIndex((column) => column.key in row.cells));
  const inline = Object.keys(row.cells).length === 1 && typeof row.label === 'string';
  return (
    <tr className="blue-table__foot">
      <th
        scope="row"
        colSpan={span}
        className={`blue-table__foot-label${inline ? ' blue-table__foot-label--inline' : ''}`}
      >
        {row.label}
      </th>
      {columns.slice(span).map((column) => {
        const filled = column.key in row.cells;
        const classes = [
          'blue-table__cell',
          'blue-table__foot-cell',
          `blue-table__cell--${column.align ?? 'left'}`,
          column.nowrap ? 'blue-table__cell--nowrap' : '',
          row.cellClassName?.[column.key] ?? '',
        ]
          .filter(Boolean)
          .join(' ');
        const label = inline ? (row.label as string) : columnLabel(column);
        return (
          <td key={column.key} className={classes} data-label={stackOnMobile && filled ? label : undefined}>
            {filled ? row.cells[column.key] : null}
          </td>
        );
      })}
    </tr>
  );
}

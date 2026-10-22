import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  MouseEvent,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';

export type BlueSize = 'sm' | 'md' | 'lg';
export type BlueButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger';
export type BlueAlertVariant = 'info' | 'success' | 'warning' | 'error';
export type BlueBadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';

export interface BlueButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BlueButtonVariant;
  size?: BlueSize;
  loading?: boolean;
  fullWidth?: boolean;
  children: ReactNode;
}

export interface BlueInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export interface BlueCardProps {
  title?: string;
  header?: ReactNode;
  footer?: ReactNode;
  bordered?: boolean;
  hoverable?: boolean;
  children: ReactNode;
  className?: string;
}

export interface BlueAlertProps {
  variant?: BlueAlertVariant;
  title?: string;
  onDismiss?: () => void;
  children: ReactNode;
  className?: string;
}

export interface BlueBadgeProps {
  variant?: BlueBadgeVariant;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}

export interface BlueSelectOption {
  value: string;
  label: string;
}

export interface BlueSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: BlueSelectOption[];
  placeholder?: string;
  helperText?: string;
  error?: string;
}

export interface BlueSpinnerProps {
  size?: BlueSize;
  label?: string;
  className?: string;
}

export interface BlueTextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export interface BlueLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Opens in a new tab (target="_blank", rel="noopener noreferrer"). */
  external?: boolean;
  children: ReactNode;
}

export interface BlueAvatarProps {
  /** Shown as initials when there is no picture, and used as the picture's alt text. */
  name: string;
  src?: string;
  size?: BlueSize;
  className?: string;
}

/** A link in a navigation component (navbar, breadcrumb). */
export interface BlueNavItem {
  key: string;
  label: ReactNode;
  /** Leave out for the current page in a breadcrumb (shown as plain text). */
  href?: string;
}

/** Called when a navigation link is clicked, e.g. to change the page without reloading it. */
export type BlueNavigateHandler = (item: BlueNavItem, event: MouseEvent<HTMLAnchorElement>) => void;

export interface BlueNavbarProps {
  /** Left side: the brand or logo (BNavbar "logo" slot). */
  logo?: ReactNode;
  /** Main links, after the logo. */
  items?: BlueNavItem[];
  /** key of the link of the page that is open. */
  activeKey?: string;
  onNavigate?: BlueNavigateHandler;
  /** Right side, e.g. the signed-in user (BNavbar "actions" slot). */
  actions?: ReactNode;
  /** Extra content between the links and the actions (BNavbar default slot). */
  children?: ReactNode;
  ariaLabel?: string;
  className?: string;
}

export interface BlueBreadcrumbProps {
  /** From the top level down; the last item is the current page. */
  items: BlueNavItem[];
  onNavigate?: BlueNavigateHandler;
  className?: string;
}

export interface BlueTabItem {
  key: string;
  label: ReactNode;
  /** Shown as a small number next to the label (e.g. how many rows a filter has). */
  count?: number;
  disabled?: boolean;
}

export interface BlueTabsProps {
  items: BlueTabItem[];
  activeKey: string;
  onChange: (key: string) => void;
  /** What the tabs choose, for screen readers (e.g. "Filter by status"). */
  ariaLabel: string;
  /** id of the element the tabs control, if any. */
  controls?: string;
  className?: string;
}

export interface BlueTableColumn<T> {
  key: string;
  header: ReactNode;
  /** Cell content. Without it the cell shows row[key] (or "-" when empty). */
  render?: (row: T, index: number) => ReactNode;
  align?: 'left' | 'center' | 'right';
  /** Extra class for this column's cells, or per row (e.g. to highlight a value). */
  cellClassName?: string | ((row: T) => string | undefined);
  /** Tooltip for a cell, per row. */
  cellTitle?: (row: T) => string | undefined;
  width?: string;
  nowrap?: boolean;
  /** The column's name as text, when header is not plain text (used as the cell label in the stacked layout). */
  label?: string;
  /** A sort button in the header. The table only reports the click (onSortChange); the caller sorts the data. */
  sortable?: boolean;
  /** Direction of the first click on this column's sort button (default 'asc'; 'desc' suits dates and amounts). */
  firstSortDirection?: BlueSortDirection;
}

/** A row under the data (the table's footer), e.g. a total under an amount column. */
export interface BlueTableFooterRow {
  key: string;
  /** What the row is ("Total"); it fills the columns before the first value. */
  label: ReactNode;
  /** The row's values by column key; the other columns stay empty. */
  cells: Record<string, ReactNode>;
  /** Extra class for a value's cell, by column key (e.g. to highlight it). */
  cellClassName?: Record<string, string | undefined>;
}

export type BlueSortDirection = 'asc' | 'desc';

export interface BlueTableSort {
  key: string;
  direction: BlueSortDirection;
}

export interface BlueTableProps<T> {
  columns: BlueTableColumn<T>[];
  data: T[];
  rowKey: (row: T, index: number) => string | number;
  /** Shown instead of the rows when data is empty. */
  empty?: ReactNode;
  /** Makes rows clickable (and reachable with Tab + Enter). Clicks on links and buttons inside a row are left alone. */
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string | undefined;
  /** Describes the table for screen readers. */
  caption?: string;
  /** Smaller padding, for tables inside cards. */
  dense?: boolean;
  /** The column the data is sorted by, shown in its header. */
  sort?: BlueTableSort;
  /** Called with the new sort when a sortable header is clicked. */
  onSortChange?: (sort: BlueTableSort) => void;
  /** On narrow screens (up to 640px) each row becomes a card with the column names as labels, instead of the
   * table scrolling sideways. The sortable headers stay as a row of sort buttons above the cards. */
  stackOnMobile?: boolean;
  /** Rows under the data, such as totals; not shown while there is no data. */
  footer?: BlueTableFooterRow[];
  className?: string;
}

export interface BluePaginationProps {
  /** The page shown, from 1. */
  current: number;
  /** Number of rows over all pages. */
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
  /** What is paged, for screen readers (e.g. "Report pages"). */
  ariaLabel?: string;
  className?: string;
}

export interface BlueTagProps {
  variant?: BlueBadgeVariant;
  /** Shows a remove (×) button; removeLabel names it for screen readers. */
  onRemove?: () => void;
  removeLabel?: string;
  title?: string;
  children: ReactNode;
  className?: string;
}

export interface BlueEmptyStateProps {
  title: string;
  /** A short explanation under the title. */
  children?: ReactNode;
  /** A button or link to get out of the empty state (BEmptyState "action" slot). */
  action?: ReactNode;
  className?: string;
}

export interface BlueModalProps {
  open: boolean;
  /** Called on Esc, the close button and a click outside the dialog (unless dismissible is false). */
  onClose: () => void;
  title: ReactNode;
  children?: ReactNode;
  /** Buttons at the bottom (BModal "footer" slot). Put data-autofocus on the one to focus first. */
  footer?: ReactNode;
  size?: BlueSize;
  /** false while something runs (e.g. deleting): Esc, the close button and clicks outside do nothing. */
  dismissible?: boolean;
  className?: string;
}

export type BlueToastVariant = 'info' | 'success' | 'warning' | 'error';

export interface BlueToastOptions {
  variant?: BlueToastVariant;
  title: string;
  message?: ReactNode;
  /** Milliseconds before it closes by itself (paused while hovered or focused); 0 keeps it until closed. */
  duration?: number;
  /** A button in the toast, e.g. { label: "Undo", onClick }. The toast closes when it is clicked. */
  action?: { label: string; onClick: () => void };
}

export interface BlueToastApi {
  /** Shows a toast and returns its id. */
  show: (options: BlueToastOptions) => number;
  success: (title: string, message?: ReactNode) => number;
  error: (title: string, message?: ReactNode) => number;
  info: (title: string, message?: ReactNode) => number;
  dismiss: (id: number) => void;
}

export interface BlueToastProviderProps {
  children: ReactNode;
  /** Most toasts on screen at once; the oldest go first. */
  max?: number;
}

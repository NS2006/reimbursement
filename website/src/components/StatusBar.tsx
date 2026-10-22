import { t } from "../app/i18n";
import type { ReviewStatus } from "../types/reimbursement";
import { REVIEW_STATUSES, REVIEW_STATUS_ORDER } from "../utils/reviewStatus";
import "../styles/components/StatusBar.css";

interface StatusBarProps {
  /** How many reports have each review status. */
  counts: Record<ReviewStatus, number>;
  /** md: the overview of a reimbursement type; sm: one row of a list. */
  size?: "sm" | "md";
  className?: string;
}

/** One bar split by review status, each part as wide as its share of the reports (most urgent on the left). */
export function StatusBar({ counts, size = "md", className = "" }: StatusBarProps) {
  const shown = REVIEW_STATUS_ORDER.filter((status) => counts[status] > 0);
  const label = shown.map((status) => `${REVIEW_STATUSES[status].label}: ${counts[status]}`).join(", ") || t("statusBar.empty");
  return (
    <div className={`status-bar status-bar--${size} ${className}`.trim()} role="img" aria-label={label}>
      {shown.map((status) => (
        <span key={status} className={`status-bar__part status-dot--${status}`} style={{ flexGrow: counts[status] }} />
      ))}
    </div>
  );
}

/** The colour of a status in the bar, as a dot (for a legend). */
export function StatusDot({ status }: { status: ReviewStatus }) {
  return <span className={`status-dot status-dot--${status}`} aria-hidden="true" />;
}

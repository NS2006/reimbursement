import { BlueBadge } from "./blue/Badge";
import type { ReviewStatus } from "../types/reimbursement";
import { REVIEW_STATUSES } from "../utils/reviewStatus";
import "../styles/components/ReviewStatusBadge.css";

/** The review status of a report: needs review, processing, approved or rejected. */
export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const { label, badge } = REVIEW_STATUSES[status];
  return (
    <BlueBadge variant={badge} dot className={`review-status-badge review-status-badge--${status}`}>
      {label}
    </BlueBadge>
  );
}

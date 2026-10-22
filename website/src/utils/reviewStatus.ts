import { t } from "../app/i18n";
import type { BlueBadgeVariant } from "../components/blue/types";
import type { ReimbursementSummary, ReviewStatus } from "../types/reimbursement";

// The texts are read in the current language each time (getters), so these maps can be used as they are anywhere.

/** How each review status is shown, and what it means for the reviewer (hint: the short version). */
export const REVIEW_STATUSES: Record<ReviewStatus, { label: string; badge: BlueBadgeVariant; hint: string; meaning: string }> = {
  needs_review: reviewStatus("needs_review", "error"),
  processing: reviewStatus("processing", "default"),
  approved: reviewStatus("approved", "success"),
  rejected: reviewStatus("rejected", "default"),
};

function reviewStatus(status: ReviewStatus, badge: BlueBadgeVariant) {
  return {
    badge,
    get label() {
      return t(`reviewStatus.${status}.label`);
    },
    get hint() {
      return t(`reviewStatus.${status}.hint`);
    },
    get meaning() {
      return t(`reviewStatus.${status}.meaning`);
    },
  };
}

type LabelAndText =
  | "approvedBy.matched"
  | "approvedBy.proceed"
  | "approvedBy.reviewer"
  | "needsReviewReason.differences"
  | "needsReviewReason.failed"
  | "statusParts.needs_review"
  | "statusParts.approved";

/** The label and text under a key of common, read in the current language each time. */
function labelAndText(key: LabelAndText) {
  return {
    get label() {
      return t(`${key}.label`);
    },
    get text() {
      return t(`${key}.text`);
    },
  };
}

/** The statuses in the order a reviewer works through them: what still needs someone first. */
export const REVIEW_STATUS_ORDER: ReviewStatus[] = ["needs_review", "processing", "approved", "rejected"];

/** How an approved report was approved. */
export type ApprovedBy = "matched" | "proceed" | "reviewer";

export const APPROVED_BY: Record<ApprovedBy, { label: string; text: string }> = {
  matched: labelAndText("approvedBy.matched"),
  proceed: labelAndText("approvedBy.proceed"),
  reviewer: labelAndText("approvedBy.reviewer"),
};

export const APPROVED_BY_ORDER: ApprovedBy[] = ["matched", "proceed", "reviewer"];

/** matched / proceed / reviewer for an approved report; null for any other. */
export function approvedBy(report: Pick<ReimbursementSummary, "review_status" | "decision" | "ocr_status">): ApprovedBy | null {
  if (report.review_status !== "approved") return null;
  if (report.decision) return "reviewer";
  return report.ocr_status === "proceed" ? "proceed" : "matched";
}

/** Why a report needs a reviewer: the OCR read the file and found differences it can't explain, or the OCR couldn't
 * read the file at all (Claude timed out, couldn't run or gave no usable answer: nothing to do with the receipt). */
export type NeedsReviewReason = "differences" | "failed";

export const NEEDS_REVIEW_REASONS: Record<NeedsReviewReason, { label: string; text: string }> = {
  differences: labelAndText("needsReviewReason.differences"),
  failed: labelAndText("needsReviewReason.failed"),
};

export const NEEDS_REVIEW_REASON_ORDER: NeedsReviewReason[] = ["differences", "failed"];

/** differences / failed for a report that needs review; null for any other. */
export function needsReviewReason(report: Pick<ReimbursementSummary, "review_status" | "ocr_status">): NeedsReviewReason | null {
  if (report.review_status !== "needs_review") return null;
  return report.ocr_status === "failed" ? "failed" : "differences";
}

/** How a status filter narrows down ("by" in the list's URL): how the approved reports were approved, and why the
 * ones that need review do. */
export type StatusPart = ApprovedBy | NeedsReviewReason;

export interface StatusParts {
  /** The option for every report of the status, e.g. "All approved". */
  all: { label: string; text: string };
  options: { value: StatusPart; label: string; text: string }[];
  /** The part a report of the status is in. */
  of: (report: ReimbursementSummary) => StatusPart | null;
}

export const STATUS_PARTS: Partial<Record<ReviewStatus, StatusParts>> = {
  needs_review: {
    all: labelAndText("statusParts.needs_review"),
    get options() {
      return NEEDS_REVIEW_REASON_ORDER.map((value) => ({ value, ...NEEDS_REVIEW_REASONS[value] }));
    },
    of: needsReviewReason,
  },
  approved: {
    all: labelAndText("statusParts.approved"),
    get options() {
      return APPROVED_BY_ORDER.map((value) => ({ value, ...APPROVED_BY[value] }));
    },
    of: approvedBy,
  },
};

/** The part a report is in, under its own status (null when its status has no parts). */
export function statusPartOf(report: ReimbursementSummary): StatusPart | null {
  return STATUS_PARTS[report.review_status]?.of(report) ?? null;
}

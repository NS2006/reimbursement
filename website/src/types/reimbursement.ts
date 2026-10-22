// What the backend sends for reimbursements (GET /api/reimbursements and /api/reimbursements/<code>).
// Amounts are numbers, dates are "DD-MM-YYYY" text, timestamps ISO 8601 text.
// The general shapes take the type-specific parts (items, OCR lines) as type parameters; BBM fills them in below.

/** What the OCR decided for one photo. */
export type OcrDecision = "matched" | "proceed" | "needs_review";

/** The OCR status of a file, and of a revision from its files: failed (the OCR could not read a file) wins over
 * needs_review, which wins over processing (a file not read yet), and so on. */
export type OcrStatus = OcrDecision | "processing" | "failed";

/** What is left to do with a revision. A reviewer's decision wins; without one, a matched or proceed revision is
 * approved by the OCR (also after a rejection: every revision is compared on its own), a failed one needs review, and
 * the others keep their OCR status. */
export type ReviewStatus = "needs_review" | "processing" | "approved" | "rejected";

/** A reviewer's decision on a revision; "reopened" takes the decision before it back. */
export interface ReviewDecision {
  id: number;
  decision: "approved" | "rejected" | "reopened";
  /** Why; always there for a rejection. */
  reason: string | null;
  user_email: string;
  user_name: string;
  decided_at: string;
}

/** The decision in force: approved or rejected (a reopened decision is no decision). */
export type DecisionInForce = ReviewDecision & { decision: "approved" | "rejected" };

export interface ReimbursementSummary {
  reimbursement_code: string;
  reimbursement_type: string;
  employee_no: string;
  employee_name: string;
  /** Number of the current (highest) revision. */
  revision_no: number;
  grand_total: number;
  received_at: string;
  photo_count: number;
  ocr_status: OcrStatus;
  /** What the OCR read as the total of the photos; null while nothing is read. */
  ocr_grand_total: number | null;
  difference_count: number;
  /** The field_name of each difference (a field appears once per difference), e.g. ["volume_liter", "total_price"]. */
  difference_fields: string[];
  review_status: ReviewStatus;
  /** The reviewer's decision on the current revision; null when none is in force. */
  decision: DecisionInForce | null;
  /** The latest earlier revision with a decision was rejected: shown as a note; the status is worked out as usual. */
  previously_rejected: boolean;
  /** The latest earlier revision that ended approved or rejected (by a reviewer, or approved by the OCR) was
   *  approved: the report was revised after an approval. Shown as a mark; the status is worked out as usual. */
  previously_approved: boolean;
}

/** One page of a report list (GET /api/reimbursements): the backend filters, sorts and pages it. */
export interface ReimbursementPage {
  reimbursements: ReimbursementSummary[];
  /** The page sent: the one asked for, or the last one when the list got shorter. */
  page: number;
  page_size: number;
  page_count: number;
  /** How many reports the whole list holds (every page). */
  matching: number;
}

/** How many reports of one month, review status and part of it there are (GET /api/reimbursements/summary). */
export interface ReimbursementGroup {
  /** The month they were received in, in the reviewer's time zone: "2026-10". */
  period: string;
  status: ReviewStatus;
  /** How they were approved (matched / proceed / reviewer) or why they need review (differences / failed). */
  part: "matched" | "proceed" | "reviewer" | "differences" | "failed" | null;
  reports: number;
  amount: number;
}

export interface ReimbursementTotals {
  groups: ReimbursementGroup[];
  /** The report that needs review the longest (received first); null when none does. */
  oldest_needs_review: string | null;
}

/** Where the OCR reading and the submitted data differ. */
export interface OcrDifference {
  id: number;
  /** The OCR line it was found on (null when the OCR has no such line). */
  ocr_line_id: number | null;
  /** The submitted item it was compared with (id of the item row, null when nothing was submitted for it). */
  item_row_id: number | null;
  field_name: string;
  ocr_value: string | null;
  submitted_value: string | null;
  description: string;
  /** When it was the only number that differed, the side the other numbers on the receipt don't fit (null when
   *  they could not decide, or for a difference that is not such a number). */
  likely_wrong: "submitted" | "ocr" | null;
  /** The value those other numbers give (volume x price for an amount, ...); null with likely_wrong null. */
  expected_value: number | null;
}

export interface OcrResult<Line> {
  id: number;
  decision: OcrDecision;
  elapsed_seconds: number;
  grand_total: number | null;
  confidence_grand_total: number | null;
  ocr_process_id: number;
  processed_at: string;
  lines: Line[];
  differences: OcrDifference[];
}

/** Why the OCR could not read a file (the backend's failure_reason). */
export type OcrErrorReason =
  | "file_missing"
  | "storage_unavailable"
  | "pdf_too_large"
  | "pdf_too_many_pages"
  | "timed_out"
  | "unreadable"
  | "ocr_unavailable"
  | "other";

export interface ReimbursementPhoto<Line> {
  id: number;
  name: string;
  /** The OCR result of this file; null while the OCR has not read it (or could not). */
  ocr: OcrResult<Line> | null;
  /** processing (queued or being read), failed (the OCR could not read it), or the OCR's decision. */
  ocr_status: OcrStatus;
  /** Why the OCR could not read it; only when failed. */
  ocr_error_reason: OcrErrorReason | null;
  /** How many times the OCR tried to read it. */
  ocr_attempts: number;
}

export interface ReimbursementRevision<Item, Line> {
  id: number;
  revision_no: number;
  grand_total: number;
  received_at: string;
  ocr_status: OcrStatus;
  review_status: ReviewStatus;
  /** The decision in force; null when none. */
  decision: DecisionInForce | null;
  /** Every decision on this revision, newest first (with the reopened ones). */
  decisions: ReviewDecision[];
  /** The latest earlier revision with a decision was rejected. */
  previously_rejected: boolean;
  /** The latest earlier revision that ended approved or rejected was approved (see ReimbursementSummary). */
  previously_approved: boolean;
  items: Item[];
  photos: ReimbursementPhoto<Line>[];
}

export interface ReimbursementComment {
  id: number;
  user_email: string;
  user_name: string;
  description: string;
  created_at: string;
  edited_at: string | null;
}

export interface ReimbursementDetail<Item, Line> {
  reimbursement_code: string;
  reimbursement_type: string;
  employee_no: string;
  employee_name: string;
  /** Newest first: the first one is the current revision. */
  revisions: ReimbursementRevision<Item, Line>[];
  comments: ReimbursementComment[];
}

// ---------------------------------------------------------------------------
// BBM (fuel)
// ---------------------------------------------------------------------------

export interface BbmItem {
  /** Row id, which differences point at (item_row_id). */
  id: number;
  /** The caller's id of the item. */
  item_id: string;
  product_name: string;
  date_of_expense: string;
  price_per_liter: number | null;
  volume_liter: number;
  kilometer: number | null;
  total_price: number;
}

export interface BbmOcrLine {
  id: number;
  product_name: string | null;
  /** Exactly as printed on the receipt (can be any format, or misread). */
  date_of_expense: string | null;
  price_per_liter: number | null;
  volume_liter: number | null;
  total_price: number | null;
  /** Printed once per receipt, so only on its first line. */
  discount: number | null;
  /** 0 to 1 per field, how sure the OCR was. */
  confidence: Partial<Record<"product_name" | "date_of_expense" | "price_per_liter" | "volume_liter" | "total_price" | "discount", number | null>>;
}

export type BbmReimbursement = ReimbursementDetail<BbmItem, BbmOcrLine>;
export type BbmRevision = ReimbursementRevision<BbmItem, BbmOcrLine>;
export type BbmPhoto = ReimbursementPhoto<BbmOcrLine>;

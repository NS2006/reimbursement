// What the backend sends for reimbursements (GET /api/reimbursements and /api/reimbursements/<code>).
// Amounts are numbers, dates are "DD-MM-YYYY" text, timestamps ISO 8601 text.
// The general shapes take the type-specific parts (items, OCR lines) as type parameters; BBM fills them in below.

import type { FuelPriceSource } from "./fuelPrice";

/** What the OCR decided for one file (photo or PDF). */
export type OcrDecision = "matched" | "proceed" | "needs_review";

/** The OCR status of a file, and of a report from its files: failed (the OCR could not read a file) wins over
 * needs_review, which wins over processing (a file not read yet), and so on. */
export type OcrStatus = OcrDecision | "processing" | "failed";

/** What is left to do with a report. A reviewer's decision wins; without one, a matched or proceed report is
 * approved by the OCR, a failed one needs review, and the others keep their OCR status. */
export type ReviewStatus = "needs_review" | "processing" | "approved" | "rejected";

/** A reviewer's decision on a report; "reopened" takes the decision before it back. */
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
  employee_no: string;
  employee_name: string;
  grand_total: number;
  received_at: string;
  /** Its files (the same file sent with several items counts once). */
  photo_count: number;
  ocr_status: OcrStatus;
  /** What the OCR read as the total of the files; null while nothing is read. */
  ocr_grand_total: number | null;
  difference_count: number;
  /** The field_name of each difference (a field appears once per difference), e.g. ["volume_liter", "total_price"]. */
  difference_fields: string[];
  review_status: ReviewStatus;
  /** The reviewer's decision; null when none is in force. */
  decision: DecisionInForce | null;
  /** A report received earlier claims the same receipt, and this is not a resubmission of it (see SameReceipt): it
   *  needs review whatever the OCR found, unless a reviewer decided. */
  double_claim: boolean;
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
  /** How they were approved (matched / proceed / reviewer) or why they need review (duplicate / differences /
   *  failed). */
  part: "matched" | "proceed" | "reviewer" | "duplicate" | "differences" | "failed" | null;
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

/** A receipt file of a report (a photo or a PDF): the same file sent with several items is one, shown as its first
 *  attachment. The OCR reads it once and compares it with the items it is attached to. */
export interface ReimbursementPhoto<Line> {
  id: number;
  name: string;
  /** The row ids of the items it is attached to. */
  item_ids: number[];
  /** The OCR result of this file; null while the OCR has not read it (or could not). */
  ocr: OcrResult<Line> | null;
  /** processing (queued or being read), failed (the OCR could not read it), or the OCR's decision. */
  ocr_status: OcrStatus;
  /** Why the OCR could not read it; only when failed. */
  ocr_error_reason: OcrErrorReason | null;
  /** How many times the OCR tried to read it. */
  ocr_attempts: number;
}

export interface ReimbursementComment {
  id: number;
  user_email: string;
  user_name: string;
  description: string;
  created_at: string;
  edited_at: string | null;
}

/** A report as it was sent (it is never changed: a rejected report comes back under a new code), with what the
 *  OCR read, the reviewers' decisions and their comments. */
export interface ReimbursementDetail<Item, Line> {
  reimbursement_code: string;
  employee_no: string;
  employee_name: string;
  grand_total: number;
  received_at: string;
  ocr_status: OcrStatus;
  review_status: ReviewStatus;
  /** The decision in force; null when none. */
  decision: DecisionInForce | null;
  /** Every decision on the report, newest first (with the reopened ones). */
  decisions: ReviewDecision[];
  items: Item[];
  photos: ReimbursementPhoto<Line>[];
  comments: ReimbursementComment[];
  /** The other reports claiming the same receipt: double claims first, then resubmissions, then the later ones;
   *  each kind oldest first. */
  same_receipt: SameReceipt[];
  /** One of them is a double_claim. */
  double_claim: boolean;
}

/** What another report claiming the same receipt is to this one:
 *  - double_claim: received before, and not a resubmission: this report may claim the receipt a second time
 *  - resubmission: received before, the same employee's report a reviewer rejected: this one sends it again
 *  - claimed_again: received after, claiming it again
 *  - resubmitted: received after, the same employee resubmitting this rejected report */
export type SameReceiptKind = "double_claim" | "resubmission" | "claimed_again" | "resubmitted";

/** Another report claiming the same receipt: a file with the same content (whoever sent it), or the same
 *  employee's item with the same day, amount and volume (as submitted, or as the OCR read them). */
export interface SameReceipt {
  reimbursement_code: string;
  employee_no: string;
  employee_name: string;
  received_at: string;
  review_status: ReviewStatus;
  decision: DecisionInForce | null;
  kind: SameReceiptKind;
  /** This report's files with the same content as one of the other report's. */
  files: string[];
  /** The receipts they both have, by their numbers (day as DD-MM-YYYY). */
  numbers: { day: string; amount: number; volume: number }[];
}

// ---------------------------------------------------------------------------
// BBM (fuel)
// ---------------------------------------------------------------------------

export interface BbmItem {
  /** Row id, which differences point at (item_row_id). */
  id: number;
  /** The caller's id of the item. */
  item_id: string;
  /** The fuel type as the other system sends it: Pertamax 92, BP 92, Diesel/Dex, ... */
  product_name: string;
  date_of_expense: string;
  /** Not sent: the database works it out (total_price / volume_liter), so it is not compared with the receipt. */
  price_per_liter: number;
  volume_liter: number;
  kilometer: number | null;
  total_price: number;
  /** The ids of its receipt files (photos). */
  photo_ids: number[];
  /** The fuel price page's price of its fuel; null when the fuel can't be told (Performa > 92 or Diesel/Dex without
   *  a receipt naming one fuel, or a fuel the page doesn't list). */
  fuel_price: ItemFuelPrice | null;
}

/** The fuel an item is (its fuel type, or the name on its receipt) and its DKI Jakarta price per liter. */
export interface ItemFuelPrice {
  merchant: string;
  product: string;
  /** The fuel type names several fuels (Performa > 92, Diesel/Dex): the receipt told which. */
  from_receipt: boolean;
  /** null when no price of it was known that day. */
  today: FuelPriceOnDay | null;
  /** On the item's date. */
  on_date: FuelPriceOnDay | null;
}

export interface FuelPriceOnDay {
  /** null: the source listed no price for it from valid_from on (not listed). */
  price_per_liter: number | null;
  /** The day this price started. */
  valid_from: string;
  source: FuelPriceSource;
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
export type BbmPhoto = ReimbursementPhoto<BbmOcrLine>;

import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "../app/i18n";
import { navigate } from "../app/router";
import { useBlueToast } from "../components/blue/useBlueToast";
import type { ViewerFile } from "../components/FileViewer";
import type {
  BbmItem,
  BbmOcrLine,
  BbmReimbursement,
  BbmRevision,
  DecisionInForce,
  OcrDifference,
  OcrErrorReason,
  OcrResult,
  OcrStatus,
  ReimbursementComment,
  ReviewDecision,
  ReviewStatus,
} from "../types/reimbursement";
import type { User } from "../types/user";
import { BBM_FIELDS, fieldLabel, formatField } from "../utils/bbmFields";
import { EMPTY, formatMoney, formatNumber, formatPercent } from "../utils/format";
import { REVIEW_STATUSES } from "../utils/reviewStatus";
import { changedParts, slipBetween, type ValuePart } from "../utils/valueDiff";
import { ApiError, apiUrl, errorMessage, jsonBody, request, requestFile, useApi } from "./api";
import { BBM_PATH, bbmReportPath, queueCodes as loadQueueCodes, queueLabel, readBbmQueue } from "./BbmController";

// Logic for one BBM report (pages/BbmReportPage.tsx): the report and its revisions, which revision is shown,
// where the OCR reading differs from the submitted items, what changed since the revision before, the way
// back to the list and to the previous / next report in it, the reviewer's decision (approve, reject, take back,
// undo, then on to the next report) and the reviewers' comments.

/** Why the OCR couldn't read a file, when reading it again can't help: the file is gone, or too big for the OCR. */
const FINAL_FAILURES: ReadonlySet<OcrErrorReason> = new Set(["file_missing", "pdf_too_large", "pdf_too_many_pages"]);

// ---------------------------------------------------------------------------
// Backend calls
// ---------------------------------------------------------------------------

interface LoadedReport {
  report: BbmReimbursement;
  /** When the report was loaded (milliseconds), for "Updated 09:30" and the age of the revision. */
  loadedAt: number;
}

async function getReport(code: string, signal: AbortSignal): Promise<LoadedReport> {
  const body = await request<{ reimbursement: BbmReimbursement }>(`/reimbursements/${encodeURIComponent(code)}`, {
    signal,
  });
  return { report: body.reimbursement, loadedAt: Date.now() };
}

function commentsPath(code: string, commentId?: number): string {
  const path = `/reimbursements/${encodeURIComponent(code)}/comments`;
  return commentId === undefined ? path : `${path}/${commentId}`;
}

async function postComment(code: string, userEmail: string, description: string): Promise<ReimbursementComment> {
  const body = await request<{ comment: ReimbursementComment }>(
    commentsPath(code),
    jsonBody("POST", { user_email: userEmail, description }),
  );
  return body.comment;
}

async function patchComment(code: string, commentId: number, userEmail: string, description: string) {
  const body = await request<{ comment: ReimbursementComment }>(
    commentsPath(code, commentId),
    jsonBody("PATCH", { user_email: userEmail, description }),
  );
  return body.comment;
}

async function deleteComment(code: string, commentId: number, userEmail: string): Promise<void> {
  await request<null>(commentsPath(code, commentId), jsonBody("DELETE", { user_email: userEmail }));
}

interface DecisionRequest {
  user_email: string;
  revision_no: number;
  decision: ReviewDecision["decision"];
  reason: string | null;
  /** The newest decision the reviewer saw on the revision (null when it had none): if another reviewer decided
   * in the meantime, the backend answers 409 instead of overwriting it. */
  based_on: number | null;
}

/** The new decision, and the whole report as it is now. */
async function postDecision(code: string, body: DecisionRequest) {
  return request<{ decision: ReviewDecision; reimbursement: BbmReimbursement }>(
    `/reimbursements/${encodeURIComponent(code)}/decisions`,
    jsonBody("POST", body),
  );
}

/** The files of the revision the OCR could not read, queued again; and the whole report as it is now. */
async function postOcrRetry(code: string, revisionNo: number) {
  return request<{ queued: number; reimbursement: BbmReimbursement }>(
    `/reimbursements/${encodeURIComponent(code)}/ocr/retry`,
    jsonBody("POST", { revision_no: revisionNo }),
  );
}

/** How often the page loads the report again while the OCR reads the files it was asked to retry. */
const RETRY_WATCH_MS = 10_000;

/** The comment (or its report) no longer exists. */
function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** Another reviewer decided, or a new revision arrived, while the report was on screen. */
function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

/** An error whose message can be shown to the user as it is. */
function shownError(error: unknown): Error {
  return new Error(errorMessage(error));
}

/** OCR confidence below this is shown as unsure; the OCR validation uses the same line. */
export const CONFIDENT = 0.9;

export const COMMENT_MAX_LENGTH = 2000;

/** The backend's limit for the reason of a decision. */
export const REASON_MAX_LENGTH = 1000;

// ---------------------------------------------------------------------------
// The report page
// ---------------------------------------------------------------------------

/** A difference with what the page shows next to it. */
export interface ReviewDifference extends OcrDifference {
  photoName: string;
  /** The caller's id of the submitted item (null for a difference on the whole receipt). */
  itemId: string | null;
  /** The line of the OCR reading, counted from 1 within its photo. */
  lineNo: number | null;
}

function cellKey(rowId: number | null, field: string): string {
  return `${rowId}:${field}`;
}

/** The submitted items by item id; numbers in it count as numbers, so RB-064-10 comes after RB-064-9. */
function itemsById(items: BbmItem[]): BbmItem[] {
  return [...items].sort((a, b) => a.item_id.localeCompare(b.item_id, "en", { numeric: true }));
}

/** The receipt files of a revision (a photo or a PDF), loaded through the backend for the viewer. */
function filesOf(photos: Pick<BbmRevision["photos"][number], "id" | "name">[]): ViewerFile[] {
  return photos.map((photo) => {
    const path = `/attachments/${photo.id}/file`;
    return {
      id: photo.id,
      name: photo.name,
      load: (signal) => requestFile(path, { signal }).then((file) => file.blob),
      openUrl: apiUrl(path),
    };
  });
}

// ---------------------------------------------------------------------------
// The review summary: each difference explained, and what it means for the total
// ---------------------------------------------------------------------------

/** One side of a difference as the summary shows it. */
export interface DifferenceSide {
  /** The value, with the characters that differ from the other side marked (or "Not found", "Couldn't read"). */
  parts: ValuePart[];
  /** There is no value on this side. */
  empty: boolean;
  /** fits: agrees with the other numbers on the receipt. wrong: doesn't (submitted: likely a mistake in the
   *  submitted data; read by the OCR: a misread). plain: nothing could decide. */
  tone: "fits" | "wrong" | "plain";
  /** Why, e.g. "Fits 32,859 L × Rp 12.300" or "32,859 L × Rp 12.300 is Rp 404.166"; null when nothing to say. */
  note: string | null;
}

/** A difference explained for the reviewer: what differs, both values, which one the receipt supports, and why. */
export interface DifferenceView {
  difference: ReviewDifference;
  /** e.g. "Amount", "Receipt" */
  label: string;
  /** e.g. "item RB-046-1 · receipt 1" */
  where: string;
  /** The headline when it is the only difference, e.g. "Amount of RB-046-1 doesn't match the receipt". */
  title: string;
  /** The line under that headline. */
  summary: string;
  submitted: DifferenceSide;
  receipt: DifferenceSide;
  /** What it looks like ("Two digits are swapped (1 and 4): ...") and what to check; null when the sides say it. */
  hint: string | null;
}

/** What the receipts of one file add up to, for the totals under its table. */
export interface FileTotals {
  /** The amounts read, added up; a receipt whose amount wasn't read adds nothing (see note). */
  amounts: number;
  discounts: number;
  /** The total paid printed on the receipts, as the OCR read it; null when it couldn't read it. */
  printed: number | null;
  /** How sure the OCR was of `printed`. */
  confidence: number | null;
  /** The printed total equals the amounts with no discount, so one total says it all. */
  simple: boolean;
  /** Why the printed total isn't the amounts minus the discounts; null when it is. */
  note: string | null;
}

/** The totals under the tables. */
export interface TableTotals {
  submitted: {
    /** The amounts of the submitted items, added up. */
    amounts: number;
    /** The total to reimburse (the grand total sent with the items). */
    total: number;
    /** Why the total isn't the amounts; null when it is. */
    note: string | null;
  };
  /** By photo id, for each file the OCR read. */
  files: Map<number, FileTotals>;
  /** The receipt total (over every file) is known and isn't the submitted one. */
  differs: boolean;
  /** For the only file (with several, see allFiles): how far its receipt total is from the submitted one ("Rp
   *  646.180 more than submitted"); null when they are the same, or there is no receipt total yet. */
  gap: string | null;
  /** With several files, once every total is read: what each file's receipts printed as paid, the sum, and how far
   *  it is from the submitted total (null when the same). */
  allFiles: { parts: { name: string; printed: number }[]; total: number; gap: string | null } | null;
}

/** How a field's two values are compared, for marking what differs and naming the slip. */
function compareKind(field: string): "number" | "date" | "text" {
  if (field === "date_of_expense") return "date";
  const kind = BBM_FIELDS[field]?.kind;
  return kind === "money" || kind === "number" ? "number" : "text";
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** "a", "a and b", "a, b and c" */
function listText(parts: string[]): string {
  return parts.length < 2
    ? (parts[0] ?? "")
    : t("report:and", { list: parts.slice(0, -1).join(", "), last: parts.at(-1) });
}

/** The other numbers the arithmetic check used for `field`, written as on the page ("32,859 L × Rp 12.300" for an
 *  amount); null for another field, or when one of them is unknown. Only one number differed, so the OCR line and
 *  the submitted item agree on these; the OCR line is used when it has them. */
function formulaOf(field: string, line: BbmOcrLine | null, item: BbmItem | null): string | null {
  const value = (key: "volume_liter" | "price_per_liter" | "total_price") => line?.[key] ?? item?.[key] ?? null;
  const volume = value("volume_liter");
  const price = value("price_per_liter");
  const amount = value("total_price");
  switch (field) {
    case "total_price":
      return volume !== null && price !== null ? `${formatNumber(volume)} L × ${formatMoney(price)}` : null;
    case "volume_liter":
      return amount !== null && price !== null ? `${formatMoney(amount)} ÷ ${formatMoney(price)}` : null;
    case "price_per_liter":
      return amount !== null && volume !== null ? `${formatMoney(amount)} ÷ ${formatNumber(volume)} L` : null;
    default:
      return null;
  }
}

/** The value the other numbers give, as the field is shown (amounts to the rupiah: Rp 404.166, not 404.165,7). */
function expectedText(field: string, value: number): string {
  return formatField(field, BBM_FIELDS[field]?.kind === "money" ? Math.round(value) : value);
}

function differenceView(
  difference: ReviewDifference,
  line: BbmOcrLine | null,
  item: BbmItem | null,
  manyPhotos: boolean,
): DifferenceView {
  const field = difference.field_name;
  const { submitted_value: submittedValue, ocr_value: ocrValue, likely_wrong: likelyWrong } = difference;
  const where = [
    difference.itemId ? t("report:difference.item", { id: difference.itemId }) : null,
    difference.lineNo ? t("report:difference.receipt", { no: difference.lineNo }) : null,
    manyPhotos ? difference.photoName : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const plain = (text: string, empty = false): DifferenceSide => ({
    parts: [{ text, changed: false }],
    empty,
    tone: "plain",
    note: null,
  });

  // A receipt on one side only
  if (field === "product_name" && ocrValue === null && difference.ocr_line_id === null) {
    return {
      difference,
      label: t("report:receipt"),
      where,
      title: difference.itemId
        ? t("report:difference.missing", { item: difference.itemId })
        : t("report:difference.missingItem"),
      summary: t("report:difference.missingText"),
      submitted: plain(item ? `${submittedValue ?? EMPTY} · ${formatMoney(item.total_price)}` : (submittedValue ?? EMPTY)),
      receipt: plain(t("report:difference.notFound"), true),
      hint: t("report:difference.missingText"),
    };
  }
  if (field === "product_name" && submittedValue === null) {
    const amount = line?.total_price ?? null;
    return {
      difference,
      label: t("report:receipt"),
      where,
      title: t("report:difference.extra"),
      summary: t("report:difference.extraText"),
      submitted: plain(t("report:difference.notSubmitted"), true),
      receipt: plain(amount !== null ? `${ocrValue ?? EMPTY} · ${formatMoney(amount)}` : (ocrValue ?? EMPTY)),
      hint: t("report:difference.extraText"),
    };
  }

  const label = fieldLabel(field);
  const of = difference.itemId ? t("report:difference.fieldOf", { field: label, item: difference.itemId }) : label;
  const kind = compareKind(field);
  const submittedText = formatField(field, submittedValue);
  const receiptText = formatField(field, ocrValue);
  const compared = submittedValue !== null && ocrValue !== null && kind !== "text";
  const slip = compared ? slipBetween(kind, submittedValue, ocrValue) : null;

  const formula = formulaOf(field, line, item);
  const expected = difference.expected_value === null ? null : expectedText(field, difference.expected_value);
  // The pump rounds: the value that fits can be a little off what the numbers give (Rp 646.180 for 646.176)
  const fittingText = likelyWrong === "submitted" ? receiptText : submittedText;
  const is = expected === fittingText ? "report:difference.is" : "report:difference.isAbout";
  const fitsNote = formula ? t("report:difference.fits", { formula }) : t("report:difference.fitsOther");
  const wrongNote =
    formula && expected
      ? t(is, { formula, expected })
      : expected
        ? t("report:difference.otherNumbersGive", { expected })
        : null;
  const side = (value: string | null, text: string, other: string, wrong: boolean, emptyText: string): DifferenceSide =>
    value === null
      ? plain(emptyText, true)
      : {
          parts: compared ? changedParts(text, other) : [{ text, changed: false }],
          empty: false,
          tone: likelyWrong === null ? "plain" : wrong ? "wrong" : "fits",
          note: likelyWrong === null ? null : wrong ? wrongNote : fitsNote,
        };
  const submitted = side(
    submittedValue,
    submittedText,
    receiptText,
    likelyWrong === "submitted",
    t("report:difference.notSubmitted"),
  );
  const receipt = side(ocrValue, receiptText, submittedText, likelyWrong === "ocr", t("report:difference.couldNotRead"));

  if (likelyWrong === "submitted") {
    return {
      difference,
      label,
      where,
      title: t("report:difference.submittedTitle", { what: of }),
      summary: t("report:difference.submittedSummary"),
      submitted,
      receipt,
      hint: slip ? t("report:difference.submittedHint", { slip }) : null,
    };
  }
  // The receipt side already says "Couldn't read", so no hint repeats it
  if (likelyWrong === "ocr") {
    return {
      difference,
      label,
      where,
      title:
        ocrValue === null
          ? t("report:difference.unreadTitle", { what: lowerFirst(of) })
          : t("report:difference.misreadTitle", { what: lowerFirst(of) }),
      summary: t("report:difference.ocrSummary"),
      submitted,
      receipt,
      hint: slip ? t("report:difference.ocrHint", { slip }) : null,
    };
  }
  if (ocrValue === null) {
    return {
      difference,
      label,
      where,
      title: t("report:difference.unreadTitle", { what: lowerFirst(of) }),
      summary: t("report:difference.unreadSummary"),
      submitted,
      receipt,
      hint: null,
    };
  }
  const confidence = line?.confidence[field as keyof BbmOcrLine["confidence"]] ?? null;
  const unsure =
    confidence !== null && confidence < CONFIDENT
      ? t("report:difference.unsure", { percent: formatPercent(confidence) })
      : null;
  return {
    difference,
    label,
    where,
    title: t("report:difference.differsTitle", { what: of }),
    summary: t("report:difference.checkWhich"),
    submitted,
    receipt,
    hint: [slip ? `${slip}.` : null, unsure].filter(Boolean).join(" ") || t("report:difference.checkWhich"),
  };
}

/** What the receipts of one file add up to. A printed total that is not the amounts minus the discounts (by more
 *  than Rp 1) is explained when the amounts are short and a receipt has no amount (a payment slip read as a
 *  receipt, a torn receipt). */
function fileTotalsOf(result: OcrResult<BbmOcrLine>): FileTotals {
  const amounts = result.lines.reduce((sum, line) => sum + (line.total_price ?? 0), 0);
  const discounts = result.lines.reduce((sum, line) => sum + (line.discount ?? 0), 0);
  const printed = result.grand_total;
  const gap = printed === null ? 0 : printed - (amounts - discounts);
  const noAmount = result.lines.flatMap((line, index) => (line.total_price === null ? [index + 1] : []));
  let note: string | null = null;
  if (Math.abs(gap) > 1) {
    const why =
      gap > 0 && noAmount.length > 0
        ? t("report:totals.noAmount", { count: noAmount.length, list: listText(noAmount.map(String)) })
        : t("report:totals.maybeMisread");
    note = t(gap > 0 ? "report:totals.printedMore" : "report:totals.printedLess", {
      amount: formatMoney(Math.abs(gap)),
      why,
    });
  }
  return {
    amounts,
    discounts,
    printed,
    confidence: result.confidence_grand_total,
    simple: printed !== null && discounts === 0 && note === null && noAmount.length === 0,
    note,
  };
}

/** "Rp 646.180 more than submitted"; null when the receipt total is the submitted one. */
function gapText(submitted: number, receipt: number): string | null {
  const gap = receipt - submitted;
  return Math.abs(gap) < 0.01
    ? null
    : t(gap > 0 ? "report:totals.more" : "report:totals.less", { amount: formatMoney(Math.abs(gap)) });
}

function tableTotalsOf(revision: BbmRevision, receiptTotal: number | null): TableTotals {
  const amounts = revision.items.reduce((sum, item) => sum + item.total_price, 0);
  const total = revision.grand_total;
  const gap = total - amounts;
  const files = new Map(revision.photos.flatMap((photo) => (photo.ocr ? [[photo.id, fileTotalsOf(photo.ocr)] as const] : [])));
  const many = revision.photos.length > 1;
  return {
    submitted: {
      amounts,
      total,
      note:
        Math.abs(gap) > 1
          ? t(gap > 0 ? "report:totals.toReimburseMore" : "report:totals.toReimburseLess", {
              amount: formatMoney(Math.abs(gap)),
            })
          : null,
    },
    files,
    differs: receiptTotal !== null && gapText(total, receiptTotal) !== null,
    gap: !many && receiptTotal !== null ? gapText(total, receiptTotal) : null,
    allFiles:
      many && receiptTotal !== null
        ? {
            parts: revision.photos.map((photo) => ({ name: photo.name, printed: photo.ocr?.grand_total ?? 0 })),
            total: receiptTotal,
            gap: gapText(total, receiptTotal),
          }
        : null,
  };
}

/** What the OCR found for one revision, over all its photos. */
function reviewOf(revision: BbmRevision) {
  const itemIds = new Map(revision.items.map((item) => [item.id, item.item_id]));
  const itemsByRow = new Map(revision.items.map((item) => [item.id, item]));
  const linesById = new Map<number, BbmOcrLine>();
  const differences: ReviewDifference[] = [];
  for (const photo of revision.photos) {
    const lineNos = new Map(photo.ocr?.lines.map((line, index) => [line.id, index + 1]) ?? []);
    for (const line of photo.ocr?.lines ?? []) linesById.set(line.id, line);
    for (const difference of photo.ocr?.differences ?? []) {
      differences.push({
        ...difference,
        photoName: photo.name,
        itemId: difference.item_row_id === null ? null : (itemIds.get(difference.item_row_id) ?? null),
        lineNo: difference.ocr_line_id === null ? null : (lineNos.get(difference.ocr_line_id) ?? null),
      });
    }
  }

  const byItemCell = new Map<string, ReviewDifference[]>();
  const byLineCell = new Map<string, ReviewDifference[]>();
  for (const difference of differences) {
    for (const [map, rowId] of [
      [byItemCell, difference.item_row_id],
      [byLineCell, difference.ocr_line_id],
    ] as const) {
      const key = cellKey(rowId, difference.field_name);
      map.set(key, [...(map.get(key) ?? []), difference]);
    }
  }

  const read = revision.photos.flatMap((photo) => (photo.ocr ? [photo.ocr] : []));
  const totals = read.map((result) => result.grand_total);
  const ocrTotal =
    read.length === revision.photos.length && read.length > 0 && totals.every((total) => total !== null)
      ? totals.reduce<number>((sum, total) => sum + (total ?? 0), 0)
      : null;

  // The grand total is explained with the total to reimburse; the other differences one by one
  const lineOf = (difference: ReviewDifference) =>
    difference.ocr_line_id === null ? null : (linesById.get(difference.ocr_line_id) ?? null);
  const itemOf = (difference: ReviewDifference) =>
    difference.item_row_id === null ? null : (itemsByRow.get(difference.item_row_id) ?? null);
  const fieldViews = differences
    .filter((difference) => difference.field_name !== "grand_total")
    .map((difference) =>
      differenceView(difference, lineOf(difference), itemOf(difference), revision.photos.length > 1),
    );
  const totalDifference = differences.find((difference) => difference.field_name === "grand_total") ?? null;

  return {
    differences,
    /** Every difference but the grand total, explained (the grand totals are compared under the tables). */
    fieldViews,
    /** The totals under the tables. */
    totals: tableTotalsOf(revision, ocrTotal),
    /** When the grand total is the only difference: its headline and the line under it. */
    totalHeadline: fieldViews.length === 0 && totalDifference ? totalHeadlineOf(totalDifference) : null,
    items: itemsById(revision.items),
    byItemCell,
    byLineCell,
    photosRead: read.length,
    /** The files the OCR could not read, with why and how many times it tried. */
    failed: revision.photos
      .filter((photo) => photo.ocr_status === "failed")
      .map((photo) => ({ name: photo.name, reason: photo.ocr_error_reason ?? "other", attempts: photo.ocr_attempts })),
    /** The total the OCR read over all photos; null until every photo is read. */
    ocrTotal,
    /** When the OCR last read a photo of this revision. */
    readAt: read.map((result) => result.processed_at).sort().at(-1) ?? null,
  };
}

/** The headline when the grand total is the only difference. */
function totalHeadlineOf(difference: ReviewDifference): { title: string; summary: string } {
  // The receipt's total is the claimed one and still it is a difference: the receipt's other numbers don't back it
  // (backed_amounts in the backend's receipt_validation.py), so the total may have been changed.
  const { submitted_value: submitted, ocr_value: ocr } = difference;
  if (difference.likely_wrong === null && submitted !== null && ocr !== null && Math.abs(Number(submitted) - Number(ocr)) < 0.01) {
    return { title: t("report:totalHeadline.doesNotAddUp"), summary: t("report:totalHeadline.doesNotAddUpText") };
  }
  switch (difference.likely_wrong) {
    case "submitted":
      return { title: t("report:totalHeadline.submittedTitle"), summary: t("report:totalHeadline.submittedText") };
    case "ocr":
      return { title: t("report:totalHeadline.ocrTitle"), summary: t("report:totalHeadline.ocrText") };
    default:
      return { title: t("report:totalHeadline.differsTitle"), summary: t("report:difference.checkWhich") };
  }
}

// ---------------------------------------------------------------------------
// What changed from one revision to the next
// ---------------------------------------------------------------------------

const ITEM_FIELDS = [
  "product_name",
  "date_of_expense",
  "price_per_liter",
  "volume_liter",
  "kilometer",
  "total_price",
] as const satisfies readonly (keyof BbmItem)[];

export type RevisionChange =
  | { kind: "value"; itemId: string; field: string; before: string | number | null; after: string | number | null }
  | { kind: "added" | "removed"; itemId: string; amount: number }
  | { kind: "grand_total"; before: number; after: number }
  | { kind: "photos"; before: string[]; after: string[] };

/** The differences between a revision and the one sent before it; items are matched by their item id. */
function changesBetween(before: BbmRevision, after: BbmRevision): RevisionChange[] {
  const changes: RevisionChange[] = [];
  if (before.grand_total !== after.grand_total) {
    changes.push({ kind: "grand_total", before: before.grand_total, after: after.grand_total });
  }
  const earlier = new Map(before.items.map((item) => [item.item_id, item]));
  const later = new Set(after.items.map((item) => item.item_id));
  for (const item of itemsById(after.items)) {
    const old = earlier.get(item.item_id);
    if (!old) {
      changes.push({ kind: "added", itemId: item.item_id, amount: item.total_price });
      continue;
    }
    for (const field of ITEM_FIELDS) {
      if (old[field] !== item[field]) {
        changes.push({ kind: "value", itemId: item.item_id, field, before: old[field], after: item[field] });
      }
    }
  }
  for (const item of itemsById(before.items)) {
    if (!later.has(item.item_id)) changes.push({ kind: "removed", itemId: item.item_id, amount: item.total_price });
  }
  const photoNames = (revision: BbmRevision) => revision.photos.map((photo) => photo.name).sort();
  const [namesBefore, namesAfter] = [photoNames(before), photoNames(after)];
  if (namesBefore.join("\n") !== namesAfter.join("\n")) {
    changes.push({ kind: "photos", before: namesBefore, after: namesAfter });
  }
  return changes;
}

// ---------------------------------------------------------------------------
// Going from a difference to its cells in the tables
// ---------------------------------------------------------------------------

/** Class that makes a table cell blink once (styles/pages/BbmReportPage.css). */
const FLASH_CLASS = "bbm-report__cell--flash";

/** A difference that points at a submitted item or an OCR line, so it has cells in the tables. */
export function hasCells(difference: OcrDifference): boolean {
  return difference.item_row_id !== null || difference.ocr_line_id !== null;
}

/** Scroll to the cells of a difference (the submitted item's and the OCR line's) and make them blink. The page
 * marks those cells with data-differences="<difference ids>". */
function showDifference(difference: OcrDifference) {
  flash(
    [...document.querySelectorAll(`[data-differences~="${difference.id}"]`)]
      .map((element) => element.closest("td"))
      .filter((cell) => cell !== null),
  );
}

/** Scroll to the first of `cells` and make them all blink once. */
function flash(cells: HTMLElement[]) {
  if (cells.length === 0) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  cells[0].scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "center" });
  for (const cell of cells) {
    cell.classList.remove(FLASH_CLASS);
    void cell.offsetWidth; // restarts the animation when the cell is still blinking
    cell.classList.add(FLASH_CLASS);
    cell.addEventListener("animationend", () => cell.classList.remove(FLASH_CLASS), { once: true });
  }
}

// ---------------------------------------------------------------------------
// The reviewer's decision
// ---------------------------------------------------------------------------

/** The rejection of the revision before, which the shown revision should fix. */
export interface PreviousRejection {
  revisionNo: number;
  decision: DecisionInForce;
}

/** What the decision bar at the bottom of the page offers for the shown revision. */
export type DecisionPanel =
  /** An older revision: only the current one is decided. */
  | { kind: "old"; currentNo: number }
  /** Nobody decided yet: approve or reject. */
  | { kind: "open"; status: "needs_review" | "processing" }
  /** The OCR approved it (matched, or only OCR misreads); a reviewer can still reject it. */
  | { kind: "auto"; by: "matched" | "proceed" }
  /** A reviewer decided: decide the other way, or take the decision back. */
  | { kind: "decided"; decision: DecisionInForce; mine: boolean; afterTakeBack: ReviewStatus };

/** The review status of a revision without a reviewer's decision (as the backend's review_status). */
function statusWithoutDecision(revision: BbmRevision): ReviewStatus {
  if (revision.ocr_status === "matched" || revision.ocr_status === "proceed") return "approved";
  return revision.ocr_status === "failed" ? "needs_review" : revision.ocr_status;
}

function decisionPanelOf(revision: BbmRevision, current: BbmRevision, userEmail: string): DecisionPanel {
  if (revision !== current) return { kind: "old", currentNo: current.revision_no };
  if (revision.decision) {
    return {
      kind: "decided",
      decision: revision.decision,
      mine: revision.decision.user_email === userEmail,
      afterTakeBack: statusWithoutDecision(revision),
    };
  }
  if (revision.review_status === "approved") {
    return { kind: "auto", by: revision.ocr_status === "proceed" ? "proceed" : "matched" };
  }
  return { kind: "open", status: revision.review_status === "processing" ? "processing" : "needs_review" };
}

/** The latest earlier revision with a decision, when that decision was a rejection. */
function previousRejectionOf(revisions: BbmRevision[], index: number): PreviousRejection | null {
  const decided = revisions.slice(index + 1).find((candidate) => candidate.decision !== null);
  return decided?.decision?.decision === "rejected"
    ? { revisionNo: decided.revision_no, decision: decided.decision }
    : null;
}

/** A list of reports still to decide (the "Needs review" filter): deciding one there opens the next one. */
function isWorkList(url: string): boolean {
  return new URL(url, window.location.origin).searchParams.get("status") === "needs_review";
}

function usualReasons(): string[] {
  return [t("report:rejectDialog.unreadable"), t("report:rejectDialog.claimedBefore")];
}

/** Ready-made reasons to reject: what the receipt shows where it differs from the submitted data, and the usual ones. */
function reasonSuggestions(differences: ReviewDifference[]): string[] {
  const found = differences
    .filter((difference) => difference.ocr_value !== null)
    .map((difference) => {
      const field = fieldLabel(difference.field_name);
      const what = difference.itemId ? t("report:rejectDialog.fieldOfItem", { field, item: difference.itemId }) : field;
      const submitted = formatField(difference.field_name, difference.submitted_value);
      const read = formatField(difference.field_name, difference.ocr_value);
      return t("report:rejectDialog.suggestion", { what, submitted, read });
    });
  return [...new Set(found)].slice(0, 4).concat(usualReasons());
}

/** One line of the report's history. */
export type HistoryEvent =
  | { kind: "received"; at: string; revisionNo: number }
  | { kind: "read"; at: string; revisionNo: number; status: OcrStatus }
  | { kind: "decision"; at: string; revisionNo: number; decision: ReviewDecision };

const EVENT_ORDER = { received: 0, read: 1, decision: 2 } as const;

/** Everything that happened to the report, newest first: revisions received, read by the OCR, and decided. */
function historyOf(report: BbmReimbursement): HistoryEvent[] {
  const events: HistoryEvent[] = [];
  for (const revision of report.revisions) {
    const revisionNo = revision.revision_no;
    events.push({ kind: "received", at: revision.received_at, revisionNo });
    const readAt = revision.photos.map((photo) => photo.ocr?.processed_at ?? null);
    if (revision.ocr_status !== "processing" && readAt.every((at) => at !== null)) {
      events.push({ kind: "read", at: readAt.sort().at(-1) ?? revision.received_at, revisionNo, status: revision.ocr_status });
    }
    for (const decision of revision.decisions) {
      events.push({ kind: "decision", at: decision.decided_at, revisionNo, decision });
    }
  }
  return events.sort(
    (a, b) =>
      Date.parse(b.at) - Date.parse(a.at) ||
      b.revisionNo - a.revisionNo ||
      EVENT_ORDER[b.kind] - EVENT_ORDER[a.kind] ||
      (a.kind === "decision" && b.kind === "decision" ? b.decision.id - a.decision.id : 0),
  );
}

/**
 * The decision bar's ref: keeps the bar's height in --bbm-decision-height on the page, so the receipt files next to
 * the tables (sticky, see BbmReportPage.css) end above the bar instead of under it.
 */
function measureDecisionBar(bar: HTMLElement | null) {
  const page = bar?.closest<HTMLElement>(".bbm-report");
  if (!bar || !page) return;
  const observer = new ResizeObserver(() => page.style.setProperty("--bbm-decision-height", `${bar.offsetHeight}px`));
  observer.observe(bar);
  return () => {
    observer.disconnect();
    page.style.removeProperty("--bbm-decision-height");
  };
}

export type BbmReportController = ReturnType<typeof useBbmReportController>;

export function useBbmReportController(code: string, user: User) {
  const { state, refreshing, reload, update } = useApi(`bbm-report:${code}`, (signal) => getReport(code, signal));
  const report = state.status === "ready" ? state.data.report : null;
  // The list this report was opened from (read once: the page starts fresh for every report), and its reports: loaded
  // by the first report page opened from the list, then kept with it.
  const [queue] = useState(readBbmQueue);
  const queueApi = useApi(`bbm-queue:${queue?.query ?? ""}`, (signal) => loadQueueCodes(queue, signal));
  const queueList = queueApi.state.status === "ready" ? queueApi.state.data : null;

  // The revision on screen: the current (newest) one unless another one is picked.
  const [pickedRevisionNo, setPickedRevisionNo] = useState<number | null>(null);
  const revision = report
    ? (report.revisions.find((candidate) => candidate.revision_no === pickedRevisionNo) ?? report.revisions[0])
    : null;
  const review = useMemo(() => (revision ? reviewOf(revision) : null), [revision]);
  // Kept while the files stay the same (also when the report is loaded again, e.g. after a decision), so the
  // viewer does not load and draw them again.
  const filesKey = JSON.stringify(revision?.photos.map(({ id, name }) => ({ id, name })) ?? []);
  const files = useMemo(() => filesOf(JSON.parse(filesKey)), [filesKey]);
  // For an older revision: the one sent right after it. For any but the first: the one sent before it.
  const revisionIndex = report && revision ? report.revisions.indexOf(revision) : -1;
  const replacedBy = report ? (report.revisions[revisionIndex - 1] ?? null) : null;
  const previousRevision = report ? (report.revisions[revisionIndex + 1] ?? null) : null;
  const changes = useMemo(
    () => (previousRevision && revision ? changesBetween(previousRevision, revision) : null),
    [previousRevision, revision],
  );

  const queueCodes = queueList?.codes ?? [];
  const position = queueCodes.indexOf(code);
  const history = useMemo(() => (report ? historyOf(report) : []), [report]);

  // Deciding: always on the current revision, as the reviewer saw it (based_on). After approving or rejecting, the
  // next report of the "Needs review" list opens; a toast offers to undo it.
  const toast = useBlueToast();
  const current = report?.revisions[0] ?? null;
  const [deciding, setDeciding] = useState<ReviewDecision["decision"] | null>(null);
  const [rejecting, setRejecting] = useState(false);
  // Kept when the dialog is closed without rejecting, so a typed reason is not lost
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  // false once the reviewer has left the page (e.g. on to the next report): "Undo" then opens this report again
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const nextCode = position >= 0 ? (queueCodes[position + 1] ?? null) : null;
  const advance =
    queue && nextCode && isWorkList(queue.url)
      ? { code: nextCode, number: position + 2, count: queueCodes.length }
      : null;

  function showReport(reimbursement: BbmReimbursement) {
    update((data) => ({ ...data, report: reimbursement }));
  }

  /** Decide on the current revision; throws the backend's error. */
  async function send(decision: ReviewDecision["decision"], reasonText: string | null) {
    if (!current) throw new Error("The report is not loaded.");
    const before = current.decision;
    const body = await postDecision(code, {
      user_email: user.email,
      revision_no: current.revision_no,
      decision,
      reason: reasonText,
      based_on: current.decisions[0]?.id ?? null,
    });
    return { made: body.decision, before, revisionNo: current.revision_no, reimbursement: body.reimbursement };
  }

  /** Show the decided report, say so (with Undo), and open the next report of the list when there is one. */
  function finish({ made, before, revisionNo, reimbursement }: Awaited<ReturnType<typeof send>>) {
    showReport(reimbursement);
    const reopened = made.decision === "reopened";
    const next = reopened ? null : advance;
    const status = REVIEW_STATUSES[reimbursement.revisions[0].review_status].label;
    const lastOfList = queue && isWorkList(queue.url) && position === queueCodes.length - 1;
    toast.show({
      variant: "success",
      title: reopened
        ? t("report:toast.takenBack", { code })
        : t(made.decision === "approved" ? "report:toast.approved" : "report:toast.rejected", { code }),
      message: reopened
        ? t("report:toast.statusAgain", { status })
        : next
          ? t("report:toast.opening", { code: next.code })
          : lastOfList
            ? t("report:toast.lastOfList", { list: queueLabel(queue) })
            : undefined,
      duration: 10000,
      action: { label: t("report:toast.undo"), onClick: () => void undo(made, before, revisionNo) },
    });
    if (next) navigate(bbmReportPath(next.code));
  }

  /** Put back the decision that was in force before (or none), right after deciding. */
  async function undo(made: ReviewDecision, before: DecisionInForce | null, revisionNo: number) {
    try {
      const body = await postDecision(code, {
        user_email: user.email,
        revision_no: revisionNo,
        decision: before?.decision ?? "reopened",
        reason: before?.reason ?? null,
        based_on: made.id,
      });
      if (mounted.current) showReport(body.reimbursement);
      else navigate(bbmReportPath(code));
      const status = REVIEW_STATUSES[body.reimbursement.revisions[0].review_status].label;
      toast.show({ variant: "info", title: t("report:toast.undone", { code, status }) });
    } catch (error) {
      toast.error(t("report:toast.undoFailed", { code }), errorMessage(error));
      if (mounted.current && isConflict(error)) reload();
    }
  }

  function decisionFailed(error: unknown) {
    if (isConflict(error)) {
      toast.show({
        variant: "warning",
        title: t("report:toast.changed", { code }),
        message: t("report:toast.reloaded", { error: errorMessage(error) }),
      });
      setPickedRevisionNo(null);
      reload();
    } else {
      toast.error(t("report:toast.saveFailed", { code }), errorMessage(error));
    }
  }

  async function decide(decision: "approved" | "reopened") {
    if (deciding) return;
    setDeciding(decision);
    try {
      finish(await send(decision, null));
    } catch (error) {
      decisionFailed(error);
    } finally {
      if (mounted.current) setDeciding(null);
    }
  }

  async function reject() {
    const text = reason.trim();
    if (!text) {
      setReasonError(t("errors.codes.reason_required"));
      return;
    }
    if (text.length > REASON_MAX_LENGTH) {
      setReasonError(t("report:rejectDialog.reasonTooLong", { max: REASON_MAX_LENGTH }));
      return;
    }
    if (deciding) return;
    setDeciding("rejected");
    try {
      const result = await send("rejected", text);
      // Closed before the toast shows: the page behind an open dialog can't be clicked, the toast's Undo neither
      setRejecting(false);
      setReason("");
      finish(result);
    } catch (error) {
      if (isConflict(error)) {
        setRejecting(false);
        decisionFailed(error);
      } else {
        setReasonError(errorMessage(error));
      }
    } finally {
      if (mounted.current) setDeciding(null);
    }
  }

  // Retrying the OCR on the current revision: the files it could not read go back in its queue. The page then loads
  // the report again every RETRY_WATCH_MS until the OCR has read them (or failed again), so the result shows by itself.
  const [retrying, setRetrying] = useState(false);
  const [watchingCode, setWatchingCode] = useState<string | null>(null);
  const watching = watchingCode === code && current?.ocr_status === "processing";
  const loadedAt = state.status === "ready" ? state.data.loadedAt : null;
  useEffect(() => {
    if (!watching) return;
    const timer = window.setTimeout(reload, RETRY_WATCH_MS);
    return () => window.clearTimeout(timer);
  }, [watching, loadedAt, reload]);

  async function retryOcr() {
    if (!current || retrying) return;
    setRetrying(true);
    try {
      const body = await postOcrRetry(code, current.revision_no);
      if (!mounted.current) return;
      showReport(body.reimbursement);
      setWatchingCode(code);
    } catch (error) {
      if (isConflict(error)) {
        toast.show({
          variant: "warning",
          title: t("report:toast.changed", { code }),
          message: t("report:toast.reloaded", { error: errorMessage(error) }),
        });
        setPickedRevisionNo(null);
        reload();
      } else {
        toast.error(t("report:toast.retryFailed", { code }), errorMessage(error));
      }
    } finally {
      if (mounted.current) setRetrying(false);
    }
  }

  // Comments: the backend calls for components/CommentThread.tsx, which keeps the list on screen in step.
  function changeComments(change: (comments: ReimbursementComment[]) => ReimbursementComment[]) {
    update((data) => ({ ...data, report: { ...data.report, comments: change(data.report.comments) } }));
  }

  async function addComment(text: string): Promise<void> {
    try {
      const comment = await postComment(code, user.email, text);
      changeComments((comments) => [...comments, comment]);
    } catch (error) {
      throw shownError(error);
    }
  }

  async function editComment(comment: ReimbursementComment, text: string): Promise<"saved" | "gone"> {
    try {
      const saved = await patchComment(code, comment.id, user.email, text);
      changeComments((comments) => comments.map((candidate) => (candidate.id === saved.id ? saved : candidate)));
      return "saved";
    } catch (error) {
      if (!isGone(error)) throw shownError(error);
      changeComments((comments) => comments.filter((candidate) => candidate.id !== comment.id));
      return "gone";
    }
  }

  async function removeComment(comment: ReimbursementComment): Promise<"deleted" | "gone"> {
    let result: "deleted" | "gone" = "deleted";
    try {
      await deleteComment(code, comment.id, user.email);
    } catch (error) {
      if (!isGone(error)) throw shownError(error);
      result = "gone";
    }
    changeComments((comments) => comments.filter((candidate) => candidate.id !== comment.id));
    return result;
  }

  return {
    state,
    refreshing,
    reload,
    loadedAt,
    report,
    isBbm: report?.reimbursement_type === "bbm",
    /** Back to the list as the reviewer left it, and the reports before and after this one in it. */
    navigation: {
      backPath: queue?.url ?? BBM_PATH,
      backLabel: queue
        ? queueList
          ? `${queueLabel(queue)} (${queueCodes.length}${queueList.more ? "+" : ""})`
          : queueLabel(queue)
        : t("report:nav.bbmReports"),
      position: position >= 0 ? { number: position + 1, count: queueCodes.length } : null,
      previousPath: position > 0 ? bbmReportPath(queueCodes[position - 1]) : null,
      nextPath: position >= 0 && position < queueCodes.length - 1 ? bbmReportPath(queueCodes[position + 1]) : null,
    },
    revision,
    replacedBy,
    previousRevision,
    /** What changed since the revision sent before the shown one (null for the first revision). */
    changes,
    /** When the shown revision came after an approval (previously_approved): the number of the approved revision. */
    approvedBefore:
      report && revision?.previously_approved
        ? (report.revisions.find(
            (earlier) =>
              earlier.revision_no < revision.revision_no &&
              (earlier.review_status === "approved" || earlier.review_status === "rejected"),
          )?.revision_no ?? null)
        : null,
    showRevision: (revisionNo: number) => setPickedRevisionNo(revisionNo),
    /** The receipt files of the shown revision. */
    files,
    review,
    /** Retrying the OCR: offered on the current revision when the OCR could not read a file of it and no decision
     *  is in force (a decision wins over the OCR anyway). */
    ocrRetry: {
      available:
        revision !== null &&
        revision === current &&
        revision.ocr_status === "failed" &&
        revision.decision === null &&
        revision.photos.some((photo) => photo.ocr_status === "failed" && !FINAL_FAILURES.has(photo.ocr_error_reason ?? "other")),
      retrying,
      retry: () => void retryOcr(),
    },
    showDifference,
    itemDifferences: (itemRowId: number, field: string) => review?.byItemCell.get(cellKey(itemRowId, field)),
    lineDifferences: (lineId: number, field: string) => review?.byLineCell.get(cellKey(lineId, field)),
    /** The decision bar: what can be decided on the shown revision, and what happens after. */
    decision: {
      /** For the bar's element (see measureDecisionBar). */
      barRef: measureDecisionBar,
      panel: revision && current ? decisionPanelOf(revision, current, user.email) : null,
      previousRejection: report && revision ? previousRejectionOf(report.revisions, revisionIndex) : null,
      /** The decision being saved, if any. */
      deciding,
      /** The report that opens after deciding (only in the "Needs review" list). */
      advance,
      approve: () => void decide("approved"),
      takeBack: () => void decide("reopened"),
      openReject: () => {
        setReasonError(null);
        setRejecting(true);
      },
      showCurrent: () => setPickedRevisionNo(null),
    },
    rejectDialog: {
      open: rejecting,
      reason,
      error: reasonError,
      saving: deciding === "rejected",
      suggestions: review ? reasonSuggestions(review.differences) : usualReasons(),
      change: (text: string) => {
        setReason(text);
        setReasonError(null);
      },
      /** Add a ready-made reason after what is typed. */
      add: (suggestion: string) => {
        setReason((text) => (text.trim() ? `${text.trimEnd()} ${suggestion}` : suggestion));
        setReasonError(null);
      },
      close: () => {
        if (deciding !== "rejected") setRejecting(false);
      },
      submit: () => void reject(),
    },
    history,
    userEmail: user.email,
    addComment,
    editComment,
    removeComment,
  };
}

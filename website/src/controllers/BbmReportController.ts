import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "../app/i18n";
import { navigate } from "../app/router";
import { useBlueToast } from "../components/blue/useBlueToast";
import type { ViewerFile } from "../components/FileViewer";
import type {
  BbmItem,
  BbmOcrLine,
  BbmPhoto,
  BbmReimbursement,
  DecisionInForce,
  FuelPriceOnDay,
  OcrDifference,
  OcrErrorReason,
  OcrResult,
  OcrStatus,
  ReimbursementComment,
  ReviewDecision,
  ReviewStatus,
  SameReceipt,
} from "../types/reimbursement";
import type { User } from "../types/user";
import { BBM_FIELDS, fieldLabel, formatField, priceToleranceText } from "../utils/bbmFields";
import { EMPTY, formatDateTime, formatMoney, formatNumber, formatPercent } from "../utils/format";
import { REVIEW_STATUSES } from "../utils/reviewStatus";
import { changedParts, slipBetween, type ValuePart } from "../utils/valueDiff";
import { ApiError, apiUrl, errorMessage, jsonBody, request, requestFile, useApi } from "./api";
import { BBM_PATH, bbmReportPath, queueCodes as loadQueueCodes, queueLabel, readBbmQueue } from "./BbmController";
import { merchantName } from "./FuelPriceController";

// Logic for one BBM report (pages/BbmReportPage.tsx): the report, where the OCR reading of each receipt file differs
// from the submitted items it is attached to, the way back to the list and to the previous / next report in it, the
// reviewer's decision (approve, reject, take back, undo, then on to the next report) and the reviewers' comments.

/** Why the OCR couldn't read a file, when reading it again can't help: the file is gone, or too big for the OCR. */
const FINAL_FAILURES: ReadonlySet<OcrErrorReason> = new Set(["file_missing", "pdf_too_large", "pdf_too_many_pages"]);

// ---------------------------------------------------------------------------
// Backend calls
// ---------------------------------------------------------------------------

interface LoadedReport {
  report: BbmReimbursement;
  /** When the report was loaded (milliseconds), for "Updated 09:30". */
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
  decision: ReviewDecision["decision"];
  reason: string | null;
  /** The newest decision the reviewer saw on the report (null when it had none): if another reviewer decided
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

/** The files of the report the OCR could not read, queued again; and the whole report as it is now. */
async function postOcrRetry(code: string) {
  return request<{ queued: number; reimbursement: BbmReimbursement }>(
    `/reimbursements/${encodeURIComponent(code)}/ocr/retry`,
    jsonBody("POST", {}),
  );
}

/** How often the page loads the report again while the OCR reads the files it was asked to retry. */
const RETRY_WATCH_MS = 10_000;

/** The comment (or its report) no longer exists. */
function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** Another reviewer decided (or retried the OCR) while the report was on screen. */
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

/** The submitted items by item id; numbers in it count as numbers, so EXP_10 comes after EXP_9. */
function itemsById(items: BbmItem[]): BbmItem[] {
  return [...items].sort((a, b) => a.item_id.localeCompare(b.item_id, "en", { numeric: true }));
}

/** The receipt files of a report (a photo or a PDF), loaded through the backend for the viewer. */
function filesOf(photos: Pick<BbmPhoto, "id" | "name">[]): ViewerFile[] {
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

/** One side of a difference as the summary shows it: the value only (why goes in the view's hint). */
export interface DifferenceSide {
  /** The value, with the characters that differ from the other side marked (or "Not found", "Couldn't read"). */
  parts: ValuePart[];
  /** There is no value on this side. */
  empty: boolean;
  /** fits: agrees with the other numbers on the receipt. wrong: doesn't (submitted: likely a mistake in the
   *  submitted data; read by the OCR: a misread). plain: nothing could decide. */
  tone: "fits" | "wrong" | "plain";
}

/** A difference explained for the reviewer: what differs, both values, which one the receipt supports, and why. */
export interface DifferenceView {
  difference: ReviewDifference;
  /** e.g. "Amount", "Receipt" */
  label: string;
  /** e.g. "item EXP_10064 · receipt 1" */
  where: string;
  /** The headline when it is the only difference, e.g. "Amount of EXP_10064 doesn't match the receipt". */
  title: string;
  /** The line under that headline. */
  summary: string;
  /** The caption over the submitted value when it isn't just "Submitted" (the price per liter: worked out from the
   *  submitted amount and volume). */
  submittedCaption?: string;
  submitted: DifferenceSide;
  receipt: DifferenceSide;
  /** Why, under both values: which side the receipt's other numbers support and how ("The OCR is likely right:
   *  35,291 L × Rp 12.750 is about Rp 449.960, which fits what the OCR read."), what the slip looks like ("Two digits
   *  are swapped (5 and 4): ...") and what to check; null when there is nothing to add. */
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
    default:
      return null;
  }
}

/** The value the other numbers give, as the field is shown (amounts to the rupiah: Rp 404.166, not 404.165,7). */
function expectedText(field: string, value: number): string {
  return formatField(field, BBM_FIELDS[field]?.kind === "money" ? Math.round(value) : value);
}

/** "The OCR was only 70% sure it read this right."; null when it was sure enough. */
function unsureOf(line: BbmOcrLine | null, field: string): string | null {
  const confidence = line?.confidence[field as keyof BbmOcrLine["confidence"]] ?? null;
  return confidence !== null && confidence < CONFIDENT
    ? t("report:difference.unsure", { percent: formatPercent(confidence) })
    : null;
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

  // The price per liter isn't submitted: the item's amount ÷ volume against the price on the receipt. Nothing decides
  // which is right (receipt_validation.py's _computed_price): an OCR misread of the price looks just like an amount or
  // volume changed on the receipt.
  if (field === "price_per_liter") {
    const gap = compared ? Math.abs(Number(ocrValue) - Number(submittedValue)) : null;
    const value = (text: string, other: string): DifferenceSide => ({
      ...plain(text),
      parts: compared ? changedParts(text, other) : [{ text, changed: false }],
    });
    return {
      difference,
      label,
      where,
      title: t("report:difference.priceTitle", { what: of }),
      summary: t("report:difference.priceSummary"),
      submittedCaption: t("report:difference.computed"),
      submitted: value(submittedText, receiptText),
      receipt: ocrValue === null ? plain(t("report:difference.couldNotRead"), true) : value(receiptText, submittedText),
      hint:
        [
          item
            ? t("report:difference.computedFrom", {
                amount: formatMoney(item.total_price),
                volume: formatNumber(item.volume_liter),
              })
            : null,
          gap === null ? null : t("report:difference.priceApart", { gap: formatMoney(gap), percent: priceToleranceText() }),
          unsureOf(line, field),
        ]
          .filter(Boolean)
          .join(" ") || null,
    };
  }

  const formula = formulaOf(field, line, item);
  const expected = difference.expected_value === null ? null : expectedText(field, difference.expected_value);
  // Why the receipt's other numbers support one side. The pump rounds: the value that fits can be a little off what
  // the numbers give (Rp 646.180 for 646.176), so it is "about" then.
  const fittingText = likelyWrong === "submitted" ? receiptText : submittedText;
  const fittingSide = t(likelyWrong === "submitted" ? "report:difference.sideOcr" : "report:difference.sideSubmitted");
  const because =
    formula && expected
      ? t(expected === fittingText ? "report:difference.becauseIs" : "report:difference.becauseAbout", {
          formula,
          expected,
          side: fittingSide,
        })
      : expected
        ? t("report:difference.becauseOther", { expected, side: fittingSide })
        : t("report:difference.becauseFits", { side: fittingSide });
  const side = (value: string | null, text: string, other: string, wrong: boolean, emptyText: string): DifferenceSide =>
    value === null
      ? plain(emptyText, true)
      : {
          parts: compared ? changedParts(text, other) : [{ text, changed: false }],
          empty: false,
          tone: likelyWrong === null ? "plain" : wrong ? "wrong" : "fits",
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
      hint: [t("report:difference.ocrRight", { because }), slip ? t("report:difference.submittedHint", { slip }) : null]
        .filter(Boolean)
        .join(" "),
    };
  }
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
      hint: [t("report:difference.submittedRight", { because }), slip ? t("report:difference.ocrHint", { slip }) : null]
        .filter(Boolean)
        .join(" "),
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
      hint: t("report:difference.unreadSummary"),
    };
  }
  const unsure = unsureOf(line, field);
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

function tableTotalsOf(report: BbmReimbursement, receiptTotal: number | null): TableTotals {
  const amounts = report.items.reduce((sum, item) => sum + item.total_price, 0);
  const total = report.grand_total;
  const gap = total - amounts;
  const files = new Map(report.photos.flatMap((photo) => (photo.ocr ? [[photo.id, fileTotalsOf(photo.ocr)] as const] : [])));
  const many = report.photos.length > 1;
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
            parts: report.photos.map((photo) => ({ name: photo.name, printed: photo.ocr?.grand_total ?? 0 })),
            total: receiptTotal,
            gap: gapText(total, receiptTotal),
          }
        : null,
  };
}

/** What the OCR found for a report, over all its files. */
function reviewOf(report: BbmReimbursement) {
  const itemIds = new Map(report.items.map((item) => [item.id, item.item_id]));
  const itemsByRow = new Map(report.items.map((item) => [item.id, item]));
  const photoNames = new Map(report.photos.map((photo) => [photo.id, photo.name]));
  const linesById = new Map<number, BbmOcrLine>();
  const differences: ReviewDifference[] = [];
  for (const photo of report.photos) {
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

  const read = report.photos.flatMap((photo) => (photo.ocr ? [photo.ocr] : []));
  const totals = read.map((result) => result.grand_total);
  const ocrTotal =
    read.length === report.photos.length && read.length > 0 && totals.every((total) => total !== null)
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
      differenceView(difference, lineOf(difference), itemOf(difference), report.photos.length > 1),
    );
  const totalDifference = differences.find((difference) => difference.field_name === "grand_total") ?? null;

  return {
    differences,
    /** Every difference but the grand total, explained (the grand totals are compared under the tables). */
    fieldViews,
    /** The totals under the tables. */
    totals: tableTotalsOf(report, ocrTotal),
    /** When the grand total is the only difference: its headline and the line under it. */
    totalHeadline: fieldViews.length === 0 && totalDifference ? totalHeadlineOf(totalDifference) : null,
    items: itemsById(report.items),
    /** The names of an item's receipt files. */
    fileNamesOf: (item: BbmItem) => item.photo_ids.flatMap((id) => photoNames.get(id) ?? []),
    /** The item ids a receipt file is attached to (what the OCR compared it with), by item id. */
    itemIdsOf: (photo: BbmPhoto) =>
      photo.item_ids.flatMap((id) => itemIds.get(id) ?? []).sort((a, b) => a.localeCompare(b, "en", { numeric: true })),
    byItemCell,
    byLineCell,
    photosRead: read.length,
    /** The files the OCR could not read, with why and how many times it tried. */
    failed: report.photos
      .filter((photo) => photo.ocr_status === "failed")
      .map((photo) => ({ name: photo.name, reason: photo.ocr_error_reason ?? "other", attempts: photo.ocr_attempts })),
    /** The total the OCR read over all files; null until every file is read. */
    ocrTotal,
    /** When the OCR last read a file of this report. */
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

/** What the decision bar at the bottom of the page offers. */
export type DecisionPanel =
  /** Nobody decided yet: approve or reject. */
  | { kind: "open"; status: "needs_review" | "processing" }
  /** The OCR approved it (matched, or only OCR misreads); a reviewer can still reject it. */
  | { kind: "auto"; by: "matched" | "proceed" }
  /** A reviewer decided: decide the other way, or take the decision back. */
  | { kind: "decided"; decision: DecisionInForce; mine: boolean; afterTakeBack: ReviewStatus };

/** The review status of a report without a reviewer's decision (as the backend's review_status). */
function statusWithoutDecision(report: BbmReimbursement): ReviewStatus {
  if (report.double_claim) return "needs_review";
  if (report.ocr_status === "matched" || report.ocr_status === "proceed") return "approved";
  return report.ocr_status === "failed" ? "needs_review" : report.ocr_status;
}

function decisionPanelOf(report: BbmReimbursement, userEmail: string): DecisionPanel {
  if (report.decision) {
    return {
      kind: "decided",
      decision: report.decision,
      mine: report.decision.user_email === userEmail,
      afterTakeBack: statusWithoutDecision(report),
    };
  }
  if (report.review_status === "approved") {
    return { kind: "auto", by: report.ocr_status === "proceed" ? "proceed" : "matched" };
  }
  return { kind: "open", status: report.review_status === "processing" ? "processing" : "needs_review" };
}

/** A list of reports still to decide (the "Needs review" filter): deciding one there opens the next one. */
function isWorkList(url: string): boolean {
  return new URL(url, window.location.origin).searchParams.get("status") === "needs_review";
}

/** "Already claimed in EREP_x", for each report that claimed the receipt before. */
function claimedInReasons(report: BbmReimbursement | null): string[] {
  return report ? doubleClaims(report).map((entry) => t("report:rejectDialog.claimedIn", { code: entry.reimbursement_code })) : [];
}

/** The usual reasons; "claimed in another report" only when no report is known to have claimed it before. */
function usualReasons(report: BbmReimbursement | null): string[] {
  return [t("report:rejectDialog.unreadable"), ...(report?.double_claim ? [] : [t("report:rejectDialog.claimedBefore")])];
}

/** Ready-made reasons to reject: the reports that claimed the receipt before, what the receipt shows where it
 *  differs from the submitted data, and the usual ones. */
function reasonSuggestions(differences: ReviewDifference[], report: BbmReimbursement): string[] {
  const found = differences
    .filter((difference) => difference.ocr_value !== null)
    .map((difference) => {
      const field = fieldLabel(difference.field_name);
      const what = difference.itemId ? t("report:rejectDialog.fieldOfItem", { field, item: difference.itemId }) : field;
      const submitted = formatField(difference.field_name, difference.submitted_value);
      const read = formatField(difference.field_name, difference.ocr_value);
      // The price per liter isn't submitted: the amount ÷ volume gives it
      return difference.field_name === "price_per_liter"
        ? t("report:rejectDialog.priceSuggestion", { what, computed: submitted, read })
        : t("report:rejectDialog.suggestion", { what, submitted, read });
    });
  return [...claimedInReasons(report), ...[...new Set(found)].slice(0, 4), ...usualReasons(report)];
}

/** One line of the report's history. */
export type HistoryEvent =
  | { kind: "received"; at: string }
  | { kind: "read"; at: string; status: OcrStatus }
  | { kind: "decision"; at: string; decision: ReviewDecision };

const EVENT_ORDER = { received: 0, read: 1, decision: 2 } as const;

/** Everything that happened to the report, newest first: received, read by the OCR, and decided. */
function historyOf(report: BbmReimbursement): HistoryEvent[] {
  const events: HistoryEvent[] = [{ kind: "received", at: report.received_at }];
  const readAt = report.photos.map((photo) => photo.ocr?.processed_at ?? null);
  if (report.ocr_status !== "processing" && readAt.every((at) => at !== null)) {
    events.push({ kind: "read", at: readAt.sort().at(-1) ?? report.received_at, status: report.ocr_status });
  }
  for (const decision of report.decisions) {
    events.push({ kind: "decision", at: decision.decided_at, decision });
  }
  return events.sort(
    (a, b) =>
      Date.parse(b.at) - Date.parse(a.at) ||
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

// ---------------------------------------------------------------------------
// Other reports claiming the same receipt (the backend finds them: a file with the same content, or the same
// employee's receipt with the same day, amount and volume)
// ---------------------------------------------------------------------------

/** The id of the card listing them, which the summary's "compare" button scrolls to. */
export const SAME_RECEIPT_ID = "bbm-same-receipt";

function showSameReceipt() {
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(SAME_RECEIPT_ID)?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
}

/** The reports received before that claim the same receipt, not as a resubmission: oldest first. */
export function doubleClaims(report: BbmReimbursement): SameReceipt[] {
  return report.same_receipt.filter((entry) => entry.kind === "double_claim");
}

/** Another report claiming the same receipt, as the page shows it. */
export interface SameReceiptRow {
  entry: SameReceipt;
  path: string;
  /** A double claim: the one problem here. */
  problem: boolean;
  /** Sent by another employee than this report: shown as a warning. */
  otherEmployee: boolean;
  /** What both have: "The exact same file: 14.jpeg", or else "Receipt of 03-09-2026 · Rp 449.960 · 35,291 L". */
  evidence: string[];
  /** Who decided it, under its status: "By Rina, 08-09-2026 10:00", "By the OCR"; null while it is open. */
  decidedBy: string | null;
  /** Why it was rejected (a resubmission: check it was fixed). */
  reason: string | null;
}

function sameReceiptRows(report: BbmReimbursement): SameReceiptRow[] {
  return report.same_receipt.map((entry) => ({
    entry,
    path: bbmReportPath(entry.reimbursement_code),
    problem: entry.kind === "double_claim",
    otherEmployee: entry.employee_no !== report.employee_no,
    // The exact same file says it all; else the numbers both receipts have
    evidence: [
      ...entry.files.map((name) => t("report:sameReceipt.sameFile", { name })),
      ...(entry.files.length > 0 ? [] : entry.numbers).map((numbers) =>
        t("report:sameReceipt.sameNumbers", {
          day: numbers.day,
          amount: formatField("total_price", numbers.amount),
          volume: formatField("volume_liter", numbers.volume),
        }),
      ),
    ],
    decidedBy: entry.decision
      ? t("report:sameReceipt.decidedBy", { name: entry.decision.user_name, date: formatDateTime(entry.decision.decided_at) })
      : entry.review_status === "approved"
        ? t("report:sameReceipt.byOcr")
        : null,
    reason: entry.decision?.decision === "rejected" ? entry.decision.reason : null,
  }));
}

/** The headline of a double claim no reviewer decided yet, and what to do: worked out from the earlier report that
 *  matters most (approved: likely paid already; then one still open; then one rejected, which another employee sent:
 *  the same employee's would be a resubmission). null when it is not a double claim, or a reviewer decided. */
function doubleClaimSummary(report: BbmReimbursement): { title: string; text: string } | null {
  const earlier = doubleClaims(report);
  if (earlier.length === 0 || report.decision) return null;
  const title =
    earlier.length === 1
      ? t("report:sameReceipt.title", { code: earlier[0].reimbursement_code })
      : t("report:sameReceipt.titleMany", { count: earlier.length });
  const approved = earlier.find((entry) => entry.review_status === "approved");
  if (approved) return { title, text: t("report:sameReceipt.textApproved", { code: approved.reimbursement_code }) };
  const open = earlier.find((entry) => entry.review_status !== "rejected");
  if (open) return { title, text: t("report:sameReceipt.textOpen", { code: open.reimbursement_code }) };
  return {
    title,
    text: t("report:sameReceipt.textRejected", {
      code: earlier[0].reimbursement_code,
      name: earlier[0].employee_name,
      employee: report.employee_name,
    }),
  };
}

// ---------------------------------------------------------------------------
// The fuel price page's price of each item's fuel (DKI Jakarta), next to the price per liter worked out from the item
// ---------------------------------------------------------------------------

/** How far the price per liter worked out from an item may be from the fuel price page's price on its date before it
 *  is marked. Wider than PRICE_TOLERANCE: the page has Jakarta's prices, and other regions' differ a little. */
export const FUEL_PRICE_TOLERANCE = 0.1;

export interface FuelPriceCell {
  /** "Rp 13.860", "Tidak tercantum", "Belum ada data" */
  value: string;
  /** A price is known (not "not listed", "no data"). */
  known: boolean;
  /** "Sejak 01-01-2026 · Berita" */
  note: string | null;
}

export interface ItemFuelPriceRow {
  item: BbmItem;
  /** The fuel's name, or what to say when it can't be told. */
  fuel: string;
  fuelKnown: boolean;
  /** Its merchant (and that the receipt named it), or why it can't be told. */
  fuelNote: string;
  onDate: FuelPriceCell;
  today: FuelPriceCell;
  /** "Selisih 45% dari harga per liter dihitung": the worked-out price is farther than FUEL_PRICE_TOLERANCE from the
   *  price on the item's date. */
  gap: string | null;
}

const NO_PRICE: FuelPriceCell = { value: EMPTY, known: false, note: null };

function fuelPriceCell(price: FuelPriceOnDay | null): FuelPriceCell {
  if (price === null) return { value: t("report:fuelPrice.noData"), known: false, note: null };
  const note = t("report:fuelPrice.since", { date: price.valid_from, source: t(`fuelPrice:source.${price.source}`) });
  return price.price_per_liter === null
    ? { value: t("report:fuelPrice.notListed"), known: false, note }
    : { value: formatMoney(price.price_per_liter), known: true, note };
}

/** One row per item for the fuel price card. */
function fuelPriceRows(items: BbmItem[]): ItemFuelPriceRow[] {
  return items.map((item) => {
    const fuel = item.fuel_price;
    if (!fuel) {
      return {
        item,
        fuel: t("report:fuelPrice.unknownFuel"),
        fuelKnown: false,
        fuelNote: t("report:fuelPrice.unknownFuelNote", { type: item.product_name }),
        onDate: NO_PRICE,
        today: NO_PRICE,
        gap: null,
      };
    }
    const onDate = fuel.on_date?.price_per_liter ?? null;
    const apart = onDate ? Math.abs(item.price_per_liter - onDate) / onDate : 0;
    const merchant = merchantName(fuel.merchant);
    return {
      item,
      fuel: fuel.product,
      fuelKnown: true,
      fuelNote: fuel.from_receipt ? t("report:fuelPrice.fromReceipt", { merchant, type: item.product_name }) : merchant,
      onDate: fuelPriceCell(fuel.on_date),
      today: fuelPriceCell(fuel.today),
      gap: apart > FUEL_PRICE_TOLERANCE ? t("report:fuelPrice.gap", { percent: formatPercent(apart) }) : null,
    };
  });
}

export function useBbmReportController(code: string, user: User) {
  const { state, refreshing, reload, update } = useApi(`bbm-report:${code}`, (signal) => getReport(code, signal));
  const report = state.status === "ready" ? state.data.report : null;
  // The list this report was opened from (read once: the page starts fresh for every report), and its reports: loaded
  // by the first report page opened from the list, then kept with it.
  const [queue] = useState(readBbmQueue);
  const queueApi = useApi(`bbm-queue:${queue?.query ?? ""}`, (signal) => loadQueueCodes(queue, signal));
  const queueList = queueApi.state.status === "ready" ? queueApi.state.data : null;

  const review = useMemo(() => (report ? reviewOf(report) : null), [report]);
  // Kept while the files stay the same (also when the report is loaded again, e.g. after a decision), so the
  // viewer does not load and draw them again.
  const filesKey = JSON.stringify(report?.photos.map(({ id, name }) => ({ id, name })) ?? []);
  const files = useMemo(() => filesOf(JSON.parse(filesKey)), [filesKey]);

  const queueCodes = queueList?.codes ?? [];
  const position = queueCodes.indexOf(code);
  const history = useMemo(() => (report ? historyOf(report) : []), [report]);
  const fuelPrices = useMemo(() => (report ? fuelPriceRows(report.items) : []), [report]);

  // Deciding: on the report as the reviewer saw it (based_on). After approving or rejecting, the next report of the
  // "Needs review" list opens; a toast offers to undo it.
  const toast = useBlueToast();
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

  /** Decide on the report; throws the backend's error. */
  async function send(decision: ReviewDecision["decision"], reasonText: string | null) {
    if (!report) throw new Error("The report is not loaded.");
    const before = report.decision;
    const body = await postDecision(code, {
      user_email: user.email,
      decision,
      reason: reasonText,
      based_on: report.decisions[0]?.id ?? null,
    });
    return { made: body.decision, before, reimbursement: body.reimbursement };
  }

  /** Show the decided report, say so (with Undo), and open the next report of the list when there is one. */
  function finish({ made, before, reimbursement }: Awaited<ReturnType<typeof send>>) {
    showReport(reimbursement);
    const reopened = made.decision === "reopened";
    const next = reopened ? null : advance;
    const status = REVIEW_STATUSES[reimbursement.review_status].label;
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
      action: { label: t("report:toast.undo"), onClick: () => void undo(made, before) },
    });
    if (next) navigate(bbmReportPath(next.code));
  }

  /** Put back the decision that was in force before (or none), right after deciding. */
  async function undo(made: ReviewDecision, before: DecisionInForce | null) {
    try {
      const body = await postDecision(code, {
        user_email: user.email,
        decision: before?.decision ?? "reopened",
        reason: before?.reason ?? null,
        based_on: made.id,
      });
      if (mounted.current) showReport(body.reimbursement);
      else navigate(bbmReportPath(code));
      const status = REVIEW_STATUSES[body.reimbursement.review_status].label;
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

  // Retrying the OCR: the files it could not read go back in its queue. The page then loads the report again every
  // RETRY_WATCH_MS until the OCR has read them (or failed again), so the result shows by itself.
  const [retrying, setRetrying] = useState(false);
  const [watchingCode, setWatchingCode] = useState<string | null>(null);
  const watching = watchingCode === code && report?.ocr_status === "processing";
  const loadedAt = state.status === "ready" ? state.data.loadedAt : null;
  useEffect(() => {
    if (!watching) return;
    const timer = window.setTimeout(reload, RETRY_WATCH_MS);
    return () => window.clearTimeout(timer);
  }, [watching, loadedAt, reload]);

  async function retryOcr() {
    if (!report || retrying) return;
    setRetrying(true);
    try {
      const body = await postOcrRetry(code);
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
    /** The receipt files of the report. */
    files,
    review,
    /** Retrying the OCR: offered when the OCR could not read a file of the report and no decision is in force (a
     *  decision wins over the OCR anyway). */
    ocrRetry: {
      available:
        report !== null &&
        report.ocr_status === "failed" &&
        report.decision === null &&
        report.photos.some((photo) => photo.ocr_status === "failed" && !FINAL_FAILURES.has(photo.ocr_error_reason ?? "other")),
      retrying,
      retry: () => void retryOcr(),
    },
    showDifference,
    itemDifferences: (itemRowId: number, field: string) => review?.byItemCell.get(cellKey(itemRowId, field)),
    /** The fuel price page's price of each item's fuel, on its date and today. */
    fuelPrices,
    /** The other reports claiming the same receipt, and the headline when one claimed it before. */
    sameReceipt: {
      rows: report ? sameReceiptRows(report) : [],
      doubleClaim: report ? doubleClaimSummary(report) : null,
      /** Scroll to the card. */
      show: showSameReceipt,
    },
    lineDifferences: (lineId: number, field: string) => review?.byLineCell.get(cellKey(lineId, field)),
    /** The decision bar: what can be decided on the report, and what happens after. */
    decision: {
      /** For the bar's element (see measureDecisionBar). */
      barRef: measureDecisionBar,
      panel: report ? decisionPanelOf(report, user.email) : null,
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
    },
    rejectDialog: {
      open: rejecting,
      reason,
      error: reasonError,
      saving: deciding === "rejected",
      suggestions:
        review && report
          ? reasonSuggestions(review.differences, report)
          : [...claimedInReasons(report), ...usualReasons(report)],
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

import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "../app/i18n";
import { navigate, useLocation, withParams } from "../app/router";
import { useBlueToast } from "../components/blue/useBlueToast";
import type { ReimbursementPage, ReimbursementSummary, ReimbursementTotals, ReviewStatus } from "../types/reimbursement";
import { saveFile } from "../utils/download";
import { MONTH_TIME_ZONE, formatMonth } from "../utils/format";
import { REVIEW_STATUSES, REVIEW_STATUS_ORDER, STATUS_PARTS, type StatusPart } from "../utils/reviewStatus";
import { ApiError, errorMessage, jsonBody, request, requestFile, useApi } from "./api";

// Logic for the BBM list page (pages/BbmPage.tsx): the BBM reports of a month (or of every month), filtered by review
// status (and a part of it: how the approved ones were approved, why the ones that need review do) and a search text,
// sorted by a column and shown a page at a time. The backend does the filtering, sorting and paging, so only the
// page on screen is loaded, however many reports there are; the counts of the month picker and the status filters
// come from its summary. The month, filter, search, sort and page are kept in the URL
// (/bbm?period=2026-10&status=approved&by=proceed&q=EREP_100&sort=-total&page=2), so they survive opening a report and
// coming back, and a filtered list can be shared as a link.
// "Export to Excel" downloads the reports of the list (every page); on "Needs review · OCR couldn't read", "Retry OCR
// on all" puts the files of every report in the list back in the OCR queue, once the reviewer confirms it.

export const BBM_PATH = "/bbm";

export function bbmReportPath(code: string): string {
  return `${BBM_PATH}/${encodeURIComponent(code)}`;
}

export type StatusFilter = "all" | ReviewStatus;

/** The status filters, in the order a reviewer works through them (also the most urgent status first). */
export const STATUS_FILTERS: StatusFilter[] = ["all", ...REVIEW_STATUS_ORDER];

function toStatusFilter(value: string | null): StatusFilter {
  return STATUS_FILTERS.find((filter) => filter === value) ?? "all";
}

/** The part of the status filter shown ("by" in the URL): only with a status that has parts (STATUS_PARTS). */
function toStatusPart(value: string | null, status: StatusFilter): StatusPart | null {
  if (status === "all") return null;
  return STATUS_PARTS[status]?.options.find((option) => option.value === value)?.value ?? null;
}

/** "All reports", "Needs review", "Approved · Proceed" or "Needs review · OCR couldn't read" */
function filterLabel(status: StatusFilter, by: StatusPart | null): string {
  if (status === "all") return t("bbmList:allReports");
  const label = REVIEW_STATUSES[status].label;
  const part = STATUS_PARTS[status]?.options.find((option) => option.value === by);
  return part ? `${label} · ${part.label}` : label;
}

/** The OCR read a different total than the one submitted. */
export function totalDiffers(report: ReimbursementSummary): boolean {
  return report.ocr_grand_total !== null && Math.abs(report.ocr_grand_total - report.grand_total) >= 0.01;
}

/** Each field the OCR found a difference in, once, with how many differences it has: [{field, count}]. */
export function differingFields(report: ReimbursementSummary): { field: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const field of report.difference_fields) counts.set(field, (counts.get(field) ?? 0) + 1);
  return [...counts].map(([field, count]) => ({ field, count }));
}

// ---------------------------------------------------------------------------
// Months: the other system sends reports a few times a month, and reviewers check them a month at a time
// ---------------------------------------------------------------------------

/** "all" or a month as "2026-10". */
export type Period = string;

const PERIOD_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
function toPeriod(value: string | null): Period {
  return value && PERIOD_PATTERN.test(value) ? value : "all";
}

const monthParts = new Intl.DateTimeFormat("en-GB", { timeZone: MONTH_TIME_ZONE, year: "numeric", month: "2-digit" });

/** The month of a moment ("2026-10"), in WIB like the backend's months and the Received column, so a report received
 * 31-10 23:30 WIB is in October for every reviewer. A report's month is when it was received. */
export function periodOf(moment: string | number): Period {
  const parts = Object.fromEntries(monthParts.formatToParts(new Date(moment)).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}`;
}

/** "2026-10" -> "October 2026" ("Oktober 2026" in Indonesian) */
export function periodLabel(period: Period): string {
  const [year, month] = period.split("-").map(Number);
  return formatMonth(Date.UTC(year, month - 1, 15)); // mid-month: the same month in WIB
}

/** The browser's time zone, in minutes east of UTC (420 in Jakarta), for the times in the Excel export (the months
 * are WIB for everyone). */
function utcOffset(): string {
  return String(-new Date().getTimezoneOffset());
}

// ---------------------------------------------------------------------------
// Loading: one page of the list, and the summary of every month
// ---------------------------------------------------------------------------

/** A list: its month, status filter (and part), search and sort. */
export interface BbmList {
  period: Period;
  status: StatusFilter;
  by: StatusPart | null;
  search: string;
  sort: BbmSort;
}

/** The list as the backend takes it: query parameters of /reimbursements and /reimbursements/codes, and the body of
 * the export and "Retry OCR on all". */
function listParams(list: BbmList): Record<string, string | null> {
  return {
    period: list.period === "all" ? null : list.period,
    status: list.status === "all" ? null : list.status,
    by: list.by,
    q: list.search.trim() || null,
    sort: sortParam(list.sort),
    tz: utcOffset(),
  };
}

/** The query string of a list for the backend, e.g. "status=needs_review&tz=420". */
export function listQuery(list: BbmList): string {
  return withParams("", listParams(list)).replace(/^\?/, "");
}

export interface BbmReportsPage extends ReimbursementPage {
  /** When the page was loaded (milliseconds), for "Updated 09:30" and the age of each report. */
  loadedAt: number;
}

async function getBbmPage(list: BbmList, page: number, signal: AbortSignal): Promise<BbmReportsPage> {
  const query = withParams("/reimbursements", { ...listParams(list), page: page > 1 ? String(page) : null });
  const body = await request<ReimbursementPage>(query, { signal });
  return { ...body, loadedAt: Date.now() };
}

export interface BbmTotals extends ReimbursementTotals {
  loadedAt: number;
}

/** How many BBM reports each month, status and part has (those matching the search), and their amount (also used by
 * the home page). */
export async function getBbmTotals(search: string, signal: AbortSignal): Promise<BbmTotals> {
  const query = withParams("/reimbursements/summary", { q: search.trim() || null });
  const body = await request<ReimbursementTotals>(query, { signal });
  return { ...body, loadedAt: Date.now() };
}

/** The months with reports, newest first, with how many of their reports are `counted` (those of the status picked,
 * so the month picker says where they are). A month asked for in the URL is there too (with 0) so the picker can
 * show it. */
function monthsOf(totals: ReimbursementTotals | null, counted: (group: ReimbursementTotals["groups"][number]) => boolean, current: Period) {
  const counts = new Map<Period, number>();
  for (const group of totals?.groups ?? []) {
    counts.set(group.period, (counts.get(group.period) ?? 0) + (counted(group) ? group.reports : 0));
  }
  if (current !== "all" && !counts.has(current)) counts.set(current, 0);
  return [...counts]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([period, count]) => ({ period, label: periodLabel(period), count }));
}

// ---------------------------------------------------------------------------
// The review queue: the list as the reviewer last saw it, for "back", "previous" and "next" on a report page
// ---------------------------------------------------------------------------

const QUEUE_KEY = "bbm-queue";

export interface BbmQueue {
  /** The list with its month, filter, search, sort and page, e.g. "/bbm?period=2026-10&status=needs_review". */
  url: string;
  /** The list's month, filter, search and sort; queueLabel() names it in the current language. */
  list: BbmList;
  /** The list for the backend (listQuery), to load its codes. */
  query: string;
  /** Every report in the list (over all pages, the first MAX of them), in the order shown: loaded by the first
   * report page opened from the list, then kept, so previous / next go through the list as it was then. */
  codes?: string[];
  /** The list holds more reports than codes. */
  more?: boolean;
}

/** What the queue's list shows, e.g. "Needs review", "All reports · October 2026" or "Search “EREP_100”". */
export function queueLabel({ list: { period, status, by, search } }: BbmQueue): string {
  const what =
    status !== "all"
      ? filterLabel(status, by)
      : search.trim()
        ? t("bbmList:search.queue", { text: search.trim() })
        : t("bbmList:allReports");
  return period === "all" ? what : `${what} · ${periodLabel(period)}`;
}

/** Kept for this browser tab only (sessionStorage); null when the list was not opened in this tab. */
export function readBbmQueue(): BbmQueue | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(QUEUE_KEY) ?? "null") as BbmQueue | null;
    const list = saved?.list;
    const known = list && typeof list.search === "string" && (list.status === "all" || list.status in REVIEW_STATUSES);
    return saved && known && typeof saved.url === "string" && typeof saved.query === "string" ? saved : null;
  } catch {
    return null;
  }
}

export function saveBbmQueue(queue: BbmQueue) {
  try {
    sessionStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch {
    // Storage blocked (private window, full): the report page then links back to the plain list.
  }
}

/** The codes of the queue's list: the ones kept with it, else loaded from the backend once and kept. */
export async function queueCodes(queue: BbmQueue | null, signal: AbortSignal): Promise<{ codes: string[]; more: boolean }> {
  if (!queue) return { codes: [], more: false };
  if (queue.codes) return { codes: queue.codes, more: queue.more ?? false };
  const body = await request<{ codes: string[]; more: boolean }>(`/reimbursements/codes?${queue.query}`, { signal });
  saveBbmQueue({ ...queue, codes: body.codes, more: body.more });
  return body;
}

// ---------------------------------------------------------------------------
// Export to Excel
// ---------------------------------------------------------------------------

/** The most reports the backend exports at once. */
const MAX_EXPORT_REPORTS = 5000;

/** The backend builds the workbook from the list (every page, sorted as shown). */
async function exportBbmReports(list: BbmList): Promise<{ blob: Blob; name: string; count: number }> {
  const file = await requestFile(
    "/reimbursements/export",
    jsonBody("POST", { ...listParams(list), website_url: window.location.origin }),
  );
  const count = Number(file.headers.get("X-Export-Count"));
  return { blob: file.blob, name: file.name ?? "Reimbursement BBM.xlsx", count: Number.isInteger(count) ? count : 0 };
}

/** What a list holds beyond the page on screen, e.g. "October 2026, every page" ("" for every month, one page). */
function listScope(period: Period, paged: boolean): string {
  return [period !== "all" ? periodLabel(period) : null, paged ? t("bbmList:everyPage") : null].filter(Boolean).join(", ");
}

/** What "Export to Excel" downloads, for its tooltip. */
function exportHint(count: number, period: Period, paged: boolean): string {
  if (count === 0) return t("bbmList:export.none");
  const scope = listScope(period, paged);
  return t("bbmList:export.hint", { count, scope: scope ? ` (${scope})` : "" });
}

// ---------------------------------------------------------------------------
// Retry the OCR on every report it couldn't read
// ---------------------------------------------------------------------------

/** The backend queues the failed files of the list's reports again; a report retried or decided in the meantime is
 * skipped (409 when all of them are). */
async function retryBbmOcr(list: BbmList): Promise<{ queued: string[]; files: number }> {
  return request<{ queued: string[]; files: number }>("/reimbursements/ocr/retry", jsonBody("POST", listParams(list)));
}

/** What "Retry OCR on all" does, for its tooltip. */
function retryHint(count: number, scope: string): string {
  return t("bbmList:retry.hint", { count, scope: scope ? ` (${scope})` : "" });
}

// ---------------------------------------------------------------------------
// Sorting and pages
// ---------------------------------------------------------------------------

/** How the list can be sorted (the keys of the sortable columns on the page; the backend sorts). */
const SORT_KEYS = ["code", "employee", "received", "total", "differences", "status"] as const;

export type SortKey = (typeof SORT_KEYS)[number];
export type SortDirection = "asc" | "desc";

export interface BbmSort {
  key: SortKey;
  direction: SortDirection;
}

/** Newest first. */
const DEFAULT_SORT: BbmSort = { key: "received", direction: "desc" };

function isSortKey(value: string): value is SortKey {
  return (SORT_KEYS as readonly string[]).includes(value);
}

/** "total" -> total ascending, "-total" -> total descending; anything else -> the default sort. */
function toSort(value: string | null): BbmSort {
  const key = value?.replace(/^-/, "") ?? "";
  if (!isSortKey(key)) return DEFAULT_SORT;
  return { key, direction: value?.startsWith("-") ? "desc" : "asc" };
}

function sortParam(sort: BbmSort): string | null {
  if (sort.key === DEFAULT_SORT.key && sort.direction === DEFAULT_SORT.direction) return null;
  return `${sort.direction === "desc" ? "-" : ""}${sort.key}`;
}

export const PAGE_SIZE = 20;

function toPage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page > 1 ? page : 1;
}

/** How long the search waits after the last key before the list is loaded again. */
const SEARCH_DELAY_MS = 300;

/** Why the list is empty although the month has reports, e.g. "Nothing matches “EREP_9” in Needs review, October 2026." */
function noMatchText(period: Period, status: StatusFilter, by: StatusPart | null, search: string): string {
  const text = search.trim();
  if (text) {
    const scope = [status !== "all" ? filterLabel(status, by) : null, period !== "all" ? periodLabel(period) : null];
    const where = scope.filter(Boolean).join(", ");
    return where ? t("bbmList:noMatch.searchIn", { text, where }) : t("bbmList:noMatch.search", { text });
  }
  return period === "all"
    ? t("bbmList:noMatch.status")
    : t("bbmList:noMatch.statusIn", { month: periodLabel(period) });
}

/** "13 reports", "6 of 13 reports", "1–20 of 57 reports" or "1–20 of 30 matching reports". */
function rangeText(shown: { count: number; from: number; to: number }, total: number, paged: boolean, filtered: boolean) {
  if (paged) {
    const range = { count: shown.count, from: shown.from, to: shown.to };
    return filtered ? t("bbmList:range.pagedMatching", range) : t("bbmList:range.paged", range);
  }
  return filtered ? t("bbmList:range.filtered", { shown: shown.count, count: total }) : t("reports", { count: total });
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

export type BbmController = ReturnType<typeof useBbmController>;

export function useBbmController() {
  const { params } = useLocation();
  const period = toPeriod(params.get("period"));
  const status = toStatusFilter(params.get("status"));
  const by = toStatusPart(params.get("by"), status);
  const search = params.get("q") ?? "";
  const sort = toSort(params.get("sort"));
  const askedPage = toPage(params.get("page"));

  // The search box follows every key; the list is loaded again once the reviewer stops typing. A search from
  // elsewhere (a link, the back button, "Show all") applies at once.
  const [searched, setSearched] = useState(search);
  const typing = useRef(false);
  useEffect(() => {
    if (!typing.current) {
      setSearched(search);
      return;
    }
    const timer = window.setTimeout(() => {
      typing.current = false;
      setSearched(search);
    }, SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  const list: BbmList = useMemo(
    () => ({ period, status, by, search: searched, sort }),
    // sort is a new object on every render: follow its parts
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [period, status, by, searched, sort.key, sort.direction],
  );
  const query = listQuery(list);
  // The page on screen stays while the next one loads (refreshing), so the list does not jump.
  const { state, refreshing: pageRefreshing, reload: reloadPage } = useApi(
    `bbm-page:${query}&page=${askedPage}`,
    (signal) => getBbmPage(list, askedPage, signal),
    { keepData: true },
  );
  const totalsApi = useApi(`bbm-totals:${searched.trim()}`, (signal) => getBbmTotals(searched, signal), { keepData: true });
  const totals = totalsApi.state.status === "ready" ? totalsApi.state.data : null;
  const toast = useBlueToast();
  const [exporting, setExporting] = useState(false);
  // "Retry OCR on all": the list (its URL query) the reviewer is asked to confirm it for, so the dialog closes by
  // itself when the list changes (back button), and why it failed.
  const [retryAsked, setRetryAsked] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const data = state.status === "ready" ? state.data : null;
  const rows = useMemo(() => data?.reimbursements ?? [], [data]);
  const matching = data?.matching ?? 0;
  const page = data?.page ?? askedPage;
  const pageCount = data?.page_count ?? 1;

  // The month picker counts the reports of the status picked that match the search, in every month.
  const months = useMemo(
    () => monthsOf(totals, (group) => status === "all" || (group.status === status && (by === null || group.part === by)), period),
    [totals, status, by, period],
  );
  // The month is the scope of the whole page: the status counts, the list and the export.
  const inPeriod = useMemo(
    () => (totals?.groups ?? []).filter((group) => period === "all" || group.period === period),
    [totals, period],
  );
  // How many reports each status filter has, counting only those of the month that match the search; and how many
  // are in each part of their status (how the approved ones were approved, why the others need review).
  const { counts, partCounts, total } = useMemo(() => {
    const statusCounts = Object.fromEntries(STATUS_FILTERS.map((filter) => [filter, 0])) as Record<StatusFilter, number>;
    const parts: Partial<Record<StatusPart, number>> = {};
    for (const group of inPeriod) {
      statusCounts.all += group.reports;
      statusCounts[group.status] += group.reports;
      if (group.part) parts[group.part] = (parts[group.part] ?? 0) + group.reports;
    }
    return { counts: statusCounts, partCounts: parts, total: statusCounts.all };
  }, [inPeriod]);
  const totalAllMonths = useMemo(
    () => (totals ? totals.groups.reduce((sum, group) => sum + group.reports, 0) : null),
    [totals],
  );

  // Remember the list as shown, for the back link and previous / next on the report pages (their codes are loaded
  // by the first report page opened from it).
  const urlQuery = params.toString();
  useEffect(() => {
    if (state.status !== "ready") return;
    saveBbmQueue({
      url: urlQuery ? `${BBM_PATH}?${urlQuery}` : BBM_PATH,
      list,
      query,
    });
  }, [state.status, urlQuery, list, query]);

  const filtered = status !== "all" || searched.trim() !== "";
  const first = (page - 1) * PAGE_SIZE;
  const shown = { count: matching, from: rows.length ? first + 1 : 0, to: first + rows.length };

  function reload() {
    reloadPage();
    totalsApi.reload();
  }

  /** Downloads every report in the list (all pages, sorted as shown) as one Excel file. */
  async function exportToExcel() {
    if (exporting || matching === 0) return;
    if (matching > MAX_EXPORT_REPORTS) {
      toast.error(t("bbmList:export.tooMany"), t("bbmList:export.tooManyText", { max: MAX_EXPORT_REPORTS }));
      return;
    }
    setExporting(true);
    try {
      const shownCount = matching;
      const file = await exportBbmReports(list);
      saveFile(file.blob, file.name);
      if (file.count !== shownCount) {
        // The list changed since it was loaded: say so and show the list as it is now.
        toast.info(
          t("bbmList:export.exported", { count: file.count }),
          t("bbmList:export.changed", { shown: shownCount, file: file.name }),
        );
        reload();
      } else {
        toast.success(t("bbmList:export.done", { count: file.count }), file.name);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Every report in the list changed status since it was loaded.
        toast.error(t("bbmList:export.nothing"), t("bbmList:export.nothingText"));
        reload();
      } else {
        toast.error(t("bbmList:export.failed"), errorMessage(error));
      }
    } finally {
      setExporting(false);
    }
  }

  // Only the list of reports the OCR couldn't read can be retried at once.
  const retryable = status === "needs_review" && by === "failed";

  /** Queues the failed files of every report in the list (all pages) again, then shows the list as it is now. An
   * error the reviewer can try again after stays in the dialog. */
  async function retryAllOcr() {
    if (!retryable || retrying || matching === 0) return;
    setRetrying(true);
    setRetryError(null);
    try {
      const sent = matching;
      const result = await retryBbmOcr(list);
      const skipped = Math.max(0, sent - result.queued.length);
      toast.show({
        variant: "success",
        title: t("bbmList:retry.queued", { count: result.queued.length }),
        message:
          t("bbmList:retry.queuedText") + (skipped > 0 ? ` ${t("bbmList:retry.skipped", { count: skipped })}` : ""),
        action: { label: t("bbmList:retry.showProcessing"), onClick: () => show({ status: "processing" }) },
      });
      setRetryAsked(null);
      reload();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setRetryAsked(null);
        toast.show({
          variant: "warning",
          title: t("bbmList:retry.nothing"),
          message: t("bbmList:retry.nothingText", { error: errorMessage(error) }),
        });
        reload();
      } else {
        setRetryError(errorMessage(error));
      }
    } finally {
      setRetrying(false);
    }
  }

  /** A new month, filter, search or sort starts again on page 1. Another status filter drops the part ("by"). */
  function show(next: {
    period?: Period;
    status?: StatusFilter;
    by?: StatusPart | null;
    search?: string;
    sort?: BbmSort;
    page?: number;
  }) {
    const nextPeriod = next.period ?? period;
    const nextStatus = next.status ?? status;
    const nextBy = next.by !== undefined ? next.by : next.status !== undefined ? null : by;
    navigate(
      withParams(BBM_PATH, {
        period: nextPeriod === "all" ? null : nextPeriod,
        status: nextStatus === "all" ? null : nextStatus,
        by: nextStatus !== "all" && STATUS_PARTS[nextStatus] ? nextBy : null,
        q: next.search ?? search,
        sort: sortParam(next.sort ?? sort),
        page: next.page && next.page > 1 ? String(next.page) : null,
      }),
      { replace: true },
    );
  }

  return {
    state,
    /** The page or the counts are being loaded again (a reload, another page, filter or search). */
    refreshing: pageRefreshing || totalsApi.refreshing || searched !== search,
    reload,
    loadedAt: data?.loadedAt ?? null,
    period,
    /** The month the page shows, e.g. "October 2026", or null for every month. */
    periodLabel: period === "all" ? null : periodLabel(period),
    setPeriod: (next: Period) => show({ period: next }),
    /** The months with reports, newest first, for the month picker; count is of the status picked and the search. */
    months,
    /** The reports of the status picked that match the search, over every month, for the picker's "All months". */
    monthsTotal: months.reduce((sum, month) => sum + month.count, 0),
    status,
    setStatus: (next: StatusFilter) => show({ status: next }),
    /** The part of the status shown (with Approved: matched / proceed / reviewer; with Needs review: differences /
     *  failed), or null for all of it. */
    statusPart: by,
    setStatusPart: (next: StatusPart | null) => show({ by: next }),
    /** How many reports (of the month, matching the search) each part has. */
    partCounts,
    search,
    setSearch: (next: string) => {
      typing.current = true;
      show({ search: next });
    },
    sort,
    setSort: (next: { key: string; direction: SortDirection }) => {
      if (isSortKey(next.key)) show({ sort: { key: next.key, direction: next.direction } });
    },
    page,
    pageCount,
    setPage: (next: number) => {
      show({ page: next });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    /** Shows every report of the month again; the month and sort stay. */
    clearFilters: () => {
      typing.current = false;
      navigate(withParams(BBM_PATH, { period: period === "all" ? null : period, sort: sortParam(sort) }), { replace: true });
    },
    /** A status filter or a search text is applied (the month is not a filter: it is what the page is about). */
    filtered,
    counts,
    rows,
    /** Reports of the month (every report when "all") matching the search; null until the counts are loaded. */
    total: totals ? total : null,
    /** Reports of every month; null until the counts are loaded. */
    totalAllMonths,
    /** Which reports are shown, e.g. "1–20 of 57 reports". */
    rangeText: rangeText(shown, totals ? total : matching, pageCount > 1, filtered),
    /** Why the list is empty, when the month has reports but none pass the filter and search. */
    noMatchText: noMatchText(period, status, by, searched),
    /** Reports passing the filter and search, over all pages. */
    matching,
    openReport: (report: ReimbursementSummary) => navigate(bbmReportPath(report.reimbursement_code)),
    exportToExcel,
    exporting,
    /** What "Export to Excel" downloads, for its tooltip. */
    exportHint: exportHint(matching, period, pageCount > 1),
    /** "Retry OCR on all", on the list of reports the OCR couldn't read (null elsewhere): ask() opens the dialog that
     *  confirms it, retry() runs it. */
    ocrRetry: retryable
      ? {
          ask: () => {
            setRetryError(null);
            setRetryAsked(urlQuery);
          },
          open: retryAsked === urlQuery,
          close: () => {
            if (!retrying) setRetryAsked(null);
          },
          retry: () => void retryAllOcr(),
          retrying,
          error: retryError,
          count: matching,
          /** The report, when the list has only one, to name it in the dialog. */
          code: matching === 1 && rows.length === 1 ? rows[0].reimbursement_code : null,
          /** e.g. "October 2026, every page" */
          scope: listScope(period, pageCount > 1),
          hint: retryHint(matching, listScope(period, pageCount > 1)),
        }
      : null,
  };
}

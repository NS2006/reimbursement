import { useMemo, useState } from "react";
import { language, t } from "../app/i18n";
import { navigate, withParams } from "../app/router";
import type { ReimbursementGroup, ReviewStatus } from "../types/reimbursement";
import type { User } from "../types/user";
import { formatDate, formatWeekday } from "../utils/format";
import { REVIEW_STATUSES, REVIEW_STATUS_ORDER } from "../utils/reviewStatus";
import { useApi } from "./api";
import {
  BBM_PATH,
  bbmReportPath,
  getBbmTotals,
  listQuery,
  periodLabel,
  periodOf,
  saveBbmQueue,
  type BbmList,
  type Period,
} from "./BbmController";

// Logic for the home page (pages/HomePage.tsx), where a reviewer starts:
// 1. what needs them: the reports that need review, oldest first. "Start reviewing" opens the oldest, and previous /
//    next on the report page go through the rest (the same review queue the BBM list keeps).
// 2. each reimbursement type at a glance (only BBM so far): its review statuses and its latest months, each opening
//    the BBM list of that month.
// The figures come from the backend's summary of the BBM reports (how many of each month and status, and their
// amount), not from the reports themselves, so the page loads as fast with years of reports.

export type StatusCounts = Record<ReviewStatus, number>;

function countStatuses(groups: ReimbursementGroup[]): StatusCounts {
  const counts = Object.fromEntries(REVIEW_STATUS_ORDER.map((status) => [status, 0])) as StatusCounts;
  for (const group of groups) counts[group.status] += group.reports;
  return counts;
}

function reportsOf(groups: ReimbursementGroup[]): number {
  return groups.reduce((total, group) => total + group.reports, 0);
}

function amountOf(groups: ReimbursementGroup[]): number {
  return groups.reduce((total, group) => total + group.amount, 0);
}

// ---------------------------------------------------------------------------
// Months: the other system sends reports a few times a month, and reviewers check them a month at a time
// ---------------------------------------------------------------------------

/** How many months the BBM overview lists; the rest are in the month picker of the BBM list. */
const MONTHS_SHOWN = 6;
/** How many months with reports that need review "Needs your review" shows (newest first); the rest are behind
 * one "more" link to the list. */
const MONTH_CHIPS_SHOWN = 6;

export interface MonthSummary {
  period: Period;
  /** "October 2026", "Oktober 2026" */
  label: string;
  /** The BBM list of this month. */
  path: string;
  /** The month we are in. */
  current: boolean;
  reports: number;
  amount: number;
  counts: StatusCounts;
  /** What the month still has, e.g. "2 need review", "3 processing" or "Nothing to review". */
  state: { text: string; tone: "attention" | "processing" | "clear" };
}

function monthsOf(groups: ReimbursementGroup[], currentPeriod: Period): MonthSummary[] {
  const byMonth = new Map<Period, ReimbursementGroup[]>();
  for (const group of groups) {
    const month = byMonth.get(group.period);
    if (month) month.push(group);
    else byMonth.set(group.period, [group]);
  }
  return [...byMonth]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([period, monthGroups]) => {
      const counts = countStatuses(monthGroups);
      return {
        period,
        label: periodLabel(period),
        path: withParams(BBM_PATH, { period }),
        current: period === currentPeriod,
        reports: reportsOf(monthGroups),
        amount: amountOf(monthGroups),
        counts,
        state:
          counts.needs_review > 0
            ? { text: t("home:month.needReview", { count: counts.needs_review }), tone: "attention" }
            : counts.processing > 0
              ? { text: t("home:month.processing", { count: counts.processing }), tone: "processing" }
              : { text: t("home:month.clear"), tone: "clear" },
      };
    });
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

/** The BBM list as the review queue: the reports that need review, oldest first. */
const REVIEW_QUEUE_PATH = withParams(BBM_PATH, { status: "needs_review", sort: "received" });

/** The part of the day a greeting names. Indonesian splits it in four (pagi, siang, sore, malam), English in three
 * (its "midday" text is "Good afternoon" too). */
function partOfDay(hour: number): "morning" | "midday" | "afternoon" | "evening" {
  if (language() === "id") {
    if (hour < 11) return "morning";
    if (hour < 15) return "midday";
    return hour < 18 ? "afternoon" : "evening";
  }
  if (hour < 12) return "morning";
  return hour < 18 ? "afternoon" : "evening";
}

export type HomeController = ReturnType<typeof useHomeController>;

export function useHomeController(user: User) {
  const [openedAt] = useState(() => Date.now());
  const reportsApi = useApi("home-totals", (signal) => getBbmTotals("", signal));

  const loadedAt = reportsApi.state.status === "ready" ? reportsApi.state.data.loadedAt : null;
  const now = loadedAt ?? openedAt;
  const groups = useMemo(
    () => (reportsApi.state.status === "ready" ? reportsApi.state.data.groups : []),
    [reportsApi.state],
  );
  const oldestCode = reportsApi.state.status === "ready" ? reportsApi.state.data.oldest_needs_review : null;
  const counts = useMemo(() => countStatuses(groups), [groups]);
  const months = useMemo(() => monthsOf(groups, periodOf(now)), [groups, now]);

  const monthsToReview = months.filter((month) => month.counts.needs_review > 0);
  const attention = {
    count: counts.needs_review,
    /** The first report "Start reviewing" opens. */
    oldest: oldestCode ? { code: oldestCode } : null,
    /** Where they are: the newest months with reports that need review, each opening that month's list. */
    months: monthsToReview.slice(0, MONTH_CHIPS_SHOWN).map((month) => ({
      period: month.period,
      label: month.label,
      count: month.counts.needs_review,
      path: withParams(BBM_PATH, { period: month.period, status: "needs_review" }),
    })),
    /** Older months with reports that need review, not shown (they are in the list, listPath). */
    moreMonths: Math.max(0, monthsToReview.length - MONTH_CHIPS_SHOWN),
    listPath: REVIEW_QUEUE_PATH,
    processing: counts.processing,
  };

  /** Opens the oldest report that needs review; previous / next on its page go through the others (the report page
   * loads their codes). */
  function startReviewing() {
    if (!oldestCode) return;
    const list: BbmList = {
      period: "all",
      status: "needs_review",
      by: null,
      search: "",
      sort: { key: "received", direction: "asc" },
    };
    saveBbmQueue({ url: REVIEW_QUEUE_PATH, list, query: listQuery(list) });
    navigate(bbmReportPath(oldestCode));
  }

  return {
    greeting: t(`home:greeting.${partOfDay(new Date(openedAt).getHours())}`, { name: user.name }),
    /** "Tuesday, 20-10-2026", "Selasa, 20-10-2026" */
    today: `${formatWeekday(openedAt)}, ${formatDate(openedAt)}`,
    loadedAt,
    refreshing: reportsApi.refreshing,
    reload: reportsApi.reload,
    /** How many reports there are of each month and status (for what needs review and the BBM overview). */
    reports: reportsApi.state,
    reloadReports: reportsApi.reload,
    attention,
    startReviewing,
    bbm: {
      path: BBM_PATH,
      reports: reportsOf(groups),
      amount: amountOf(groups),
      /** Approved reports (by the OCR or a reviewer), and their amount. */
      approved: counts.approved,
      approvedAmount: amountOf(groups.filter((group) => group.status === "approved")),
      counts,
      /** One link per status, to the BBM list filtered by it. */
      statuses: REVIEW_STATUS_ORDER.map((status) => ({
        status,
        label: REVIEW_STATUSES[status].label,
        meaning: REVIEW_STATUSES[status].meaning,
        count: counts[status],
        path: withParams(BBM_PATH, { status }),
      })),
      months: months.slice(0, MONTHS_SHOWN),
      /** Months with reports that are not listed. */
      moreMonths: Math.max(0, months.length - MONTHS_SHOWN),
    },
  };
}

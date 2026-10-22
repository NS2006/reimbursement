import { t } from "../app/i18n";
import { linkTo } from "../app/router";
import { BlueAlert } from "../components/blue/Alert";
import { BlueButton } from "../components/blue/Button";
import { BlueCard } from "../components/blue/Card";
import { BlueEmptyState } from "../components/blue/EmptyState";
import { BlueInput } from "../components/blue/Input";
import { BlueLink } from "../components/blue/Link";
import { BlueModal } from "../components/blue/Modal";
import { BluePagination } from "../components/blue/Pagination";
import { BlueSelect } from "../components/blue/Select";
import { BlueSpinner } from "../components/blue/Spinner";
import { BlueTable } from "../components/blue/Table";
import { BlueTag } from "../components/blue/Tag";
import type { BlueTableColumn } from "../components/blue/types";
import { ReviewStatusBadge } from "../components/ReviewStatusBadge";
import {
  PAGE_SIZE,
  STATUS_FILTERS,
  bbmReportPath,
  differingFields,
  totalDiffers,
  useBbmController,
  type BbmController,
} from "../controllers/BbmController";
import type { ReimbursementSummary } from "../types/reimbursement";
import { fieldLabel } from "../utils/bbmFields";
import { NULL_VALUE, formatMoney, formatMonth, formatTime } from "../utils/format";
import { REVIEW_STATUSES, STATUS_PARTS, approvedBy, type StatusPart } from "../utils/reviewStatus";
import "../styles/pages/BbmPage.css";

export default function BbmPage() {
  const controller = useBbmController();
  const { loadedAt, refreshing, reload } = controller;

  return (
    <div className="bbm-page">
      <header className="bbm-page__header">
        <div>
          <h1 className="page-title">{t("bbmList:title")}</h1>
          <p className="page-subtitle">{t("bbmList:subtitle")}</p>
        </div>
        <div className="bbm-page__tools">
          <MonthPicker controller={controller} />
          <div className="bbm-page__sync">
            {loadedAt !== null ? (
              <span className="bbm-page__updated" aria-live="polite">
                {refreshing ? t("actions.refreshing") : t("updatedAt", { time: formatTime(loadedAt) })}
              </span>
            ) : null}
            <BlueButton variant="secondary" size="sm" loading={refreshing} onClick={reload}>
              {t("actions.refresh")}
            </BlueButton>
          </div>
        </div>
      </header>
      <ReportList controller={controller} />
      <RetryOcrDialog controller={controller} />
    </div>
  );
}

/** Which month the page is about: the status counts, the list and the export all follow it. Its counts follow the
 *  status picked and the search, so it says which months have the reports looked for. */
function MonthPicker({ controller }: { controller: BbmController }) {
  const { state, period, setPeriod, months, monthsTotal } = controller;
  if (state.status !== "ready") return null;
  return (
    <BlueSelect
      className="bbm-page__month"
      label={t("bbmList:month.label")}
      aria-controls="bbm-page-reports"
      value={period}
      onChange={(event) => setPeriod(event.target.value)}
      options={[
        { value: "all", label: t("bbmList:month.all", { count: monthsTotal }) },
        ...months.map((month) => ({ value: month.period, label: `${month.label} (${month.count})` })),
      ]}
    />
  );
}

function ReportList({ controller }: { controller: BbmController }) {
  const { state, reload, search, setSearch, sort, setSort, rows, total, page, pageCount, periodLabel } = controller;

  if (state.status === "loading") {
    return (
      <BlueCard>
        <div className="bbm-page__centered">
          <BlueSpinner label={t("bbmList:loading")} />
        </div>
      </BlueCard>
    );
  }

  if (state.status === "error") {
    return (
      <div className="bbm-page__error">
        <BlueAlert variant="error" title={t("bbmList:loadError")}>
          {state.message}
        </BlueAlert>
        <BlueButton variant="secondary" onClick={reload}>
          {t("actions.tryAgain")}
        </BlueButton>
      </div>
    );
  }

  return (
    <>
      <StatusFilters controller={controller} />
      <StatusPartFilter controller={controller} />
      <BlueCard
        className="bbm-page__card"
        header={
          <div className="bbm-page__toolbar">
            <div className="bbm-page__search">
              <SearchIcon />
              <BlueInput
                type="search"
                placeholder={t("bbmList:search.label")}
                aria-label={t("bbmList:search.label")}
                aria-controls="bbm-page-reports"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <div className="bbm-page__actions">
              <p className="bbm-page__range" aria-live="polite">
                {controller.rangeText}
              </p>
              {controller.ocrRetry ? (
                <BlueButton
                  variant="secondary"
                  size="sm"
                  className="bbm-page__export"
                  loading={controller.ocrRetry.retrying}
                  disabled={controller.matching === 0}
                  title={controller.ocrRetry.hint}
                  onClick={controller.ocrRetry.ask}
                >
                  {controller.ocrRetry.retrying ? null : <RetryIcon />}
                  {controller.ocrRetry.retrying
                    ? t("bbmList:retry.retrying")
                    : controller.matching === 1
                      ? t("bbmList:retry.button")
                      : t("bbmList:retry.all", { count: controller.matching })}
                </BlueButton>
              ) : null}
              <BlueButton
                variant="secondary"
                size="sm"
                className="bbm-page__export"
                loading={controller.exporting}
                disabled={controller.matching === 0}
                title={controller.exportHint}
                onClick={controller.exportToExcel}
              >
                {controller.exporting ? null : <DownloadIcon />}
                {controller.exporting ? t("bbmList:export.exporting") : t("bbmList:export.button")}
              </BlueButton>
            </div>
          </div>
        }
        footer={
          pageCount > 1 ? (
            <BluePagination
              className="bbm-page__pagination"
              ariaLabel={t("bbmList:pages")}
              current={page}
              total={controller.matching}
              pageSize={PAGE_SIZE}
              onChange={controller.setPage}
            />
          ) : null
        }
      >
        <div
          id="bbm-page-reports"
          className={controller.refreshing ? "bbm-page__reports bbm-page__reports--loading" : "bbm-page__reports"}
          aria-busy={controller.refreshing}
        >
          <BlueTable
            caption={t("bbmList:table.caption")}
            columns={columnsFor()}
            data={rows}
            rowKey={(report) => report.reimbursement_code}
            rowClassName={(report) => `bbm-page__row--${report.review_status}`}
            onRowClick={controller.openReport}
            sort={sort}
            onSortChange={setSort}
            stackOnMobile
            empty={
              controller.totalAllMonths === 0 ? (
                <BlueEmptyState title={t("bbmList:empty.none")}>{t("bbmList:empty.noneText")}</BlueEmptyState>
              ) : total === 0 ? (
                <BlueEmptyState
                  title={t("bbmList:empty.month", { month: periodLabel })}
                  action={
                    <BlueButton variant="secondary" size="sm" onClick={() => controller.setPeriod("all")}>
                      {t("bbmList:empty.showAllMonths")}
                    </BlueButton>
                  }
                >
                  {t("bbmList:empty.monthText")}
                </BlueEmptyState>
              ) : (
                <BlueEmptyState
                  title={t("bbmList:empty.noMatch")}
                  action={
                    <BlueButton variant="secondary" size="sm" onClick={controller.clearFilters}>
                      {periodLabel ? t("bbmList:empty.showAllOf", { month: periodLabel }) : t("bbmList:empty.showAll")}
                    </BlueButton>
                  }
                >
                  {controller.noMatchText}
                </BlueEmptyState>
              )
            }
          />
        </div>
      </BlueCard>
    </>
  );
}

/** One card per status with its count; the cards filter the list. */
/** Confirms "Retry OCR on all": each file is a new read by Claude. */
function RetryOcrDialog({ controller }: { controller: BbmController }) {
  const retry = controller.ocrRetry;
  if (!retry) return null;
  const scope = retry.scope ? ` (${retry.scope})` : "";

  return (
    <BlueModal
      open={retry.open}
      onClose={retry.close}
      dismissible={!retry.retrying}
      size="sm"
      title={
        retry.code
          ? t("bbmList:retry.title", { code: retry.code })
          : t("bbmList:retry.titleCount", { count: retry.count })
      }
      footer={
        <>
          <BlueButton variant="secondary" data-autofocus disabled={retry.retrying} onClick={retry.close}>
            {t("actions.cancel")}
          </BlueButton>
          <BlueButton loading={retry.retrying} disabled={retry.count === 0} onClick={retry.retry}>
            {t("bbmList:retry.button")}
          </BlueButton>
        </>
      }
    >
      <p className="bbm-page__dialog-text">
        {retry.count === 1 ? t("bbmList:retry.text") : t("bbmList:retry.textAll", { count: retry.count, scope })}
      </p>
      <p className="bbm-page__dialog-text">{t("bbmList:retry.stillFails")}</p>
      {retry.error ? (
        <BlueAlert variant="error" title={t("bbmList:retry.failed")}>
          {retry.error}
        </BlueAlert>
      ) : null}
    </BlueModal>
  );
}

function StatusFilters({ controller }: { controller: BbmController }) {
  const { status, setStatus, counts, periodLabel } = controller;
  return (
    <div className="bbm-page__filters" role="group" aria-label={t("bbmList:filters.label")}>
      {STATUS_FILTERS.map((filter) => {
        const active = filter === status;
        const info =
          filter === "all"
            ? {
                label: t("bbmList:allReports"),
                hint: periodLabel ? t("bbmList:filters.receivedIn", { month: periodLabel }) : t("bbmList:filters.every"),
                meaning: undefined,
              }
            : REVIEW_STATUSES[filter];
        return (
          <button
            key={filter}
            type="button"
            className={[
              "bbm-page__filter",
              `bbm-page__filter--${filter}`,
              active ? "bbm-page__filter--active" : "",
              filter === "needs_review" && counts[filter] > 0 ? "bbm-page__filter--attention" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-pressed={active}
            aria-controls="bbm-page-reports"
            title={info.meaning}
            onClick={() => setStatus(filter)}
          >
            <span className="bbm-page__filter-label">
              {filter === "all" ? null : <span className="bbm-page__filter-dot" aria-hidden="true" />}
              {info.label}
            </span>
            <span className="bbm-page__filter-count">{counts[filter]}</span>
            <span className="bbm-page__filter-hint">{info.hint}</span>
          </button>
        );
      })}
    </div>
  );
}

/** What to keep in mind about the reports of a part (read when shown, in the current language). */
const PART_HINTS: Partial<Record<StatusPart, () => string>> = {
  proceed: () => t("bbmList:partHints.proceed"),
  failed: () => t("bbmList:partHints.failed"),
};

/** With Needs review: why they need review; with Approved: how they were approved. "OCR couldn't read" sets apart
 * what went wrong on Claude's side from what the OCR found on the receipt; "Proceed" is where to spot-check the OCR. */
function StatusPartFilter({ controller }: { controller: BbmController }) {
  const { status, statusPart: by, setStatusPart, partCounts, counts } = controller;
  const parts = status === "all" ? undefined : STATUS_PARTS[status];
  if (status === "all" || !parts) return null;
  const options = [{ value: null, ...parts.all }, ...parts.options];
  const hint = by ? PART_HINTS[by]?.() : undefined;
  return (
    <div className="bbm-page__by">
      <div
        className="bbm-page__by-options"
        role="group"
        aria-label={t("bbmList:filters.parts", { status: REVIEW_STATUSES[status].label })}
      >
        {options.map((option) => (
          <button
            key={option.value ?? "all"}
            type="button"
            className="bbm-page__by-option"
            aria-pressed={option.value === by}
            aria-controls="bbm-page-reports"
            title={option.text}
            onClick={() => setStatusPart(option.value)}
          >
            {option.label}
            <span className="bbm-page__by-count">{option.value ? (partCounts[option.value] ?? 0) : counts[status]}</span>
          </button>
        ))}
      </div>
      {hint ? <p className="bbm-page__by-hint">{hint}</p> : null}
    </div>
  );
}

function columnsFor(): BlueTableColumn<ReimbursementSummary>[] {
  return [
    {
      key: "code",
      header: t("bbmList:table.report"),
      nowrap: true,
      sortable: true,
      render: (report) => (
        <span className="bbm-page__stack">
          <BlueLink className="bbm-page__code" {...linkTo(bbmReportPath(report.reimbursement_code))}>
            {report.reimbursement_code}
          </BlueLink>
          <ReportExtras report={report} />
          {report.previously_approved ? <RevisedAfterApproval /> : null}
        </span>
      ),
    },
    {
      key: "employee",
      header: t("bbmList:table.employee"),
      sortable: true,
      render: (report) => (
        <span className="bbm-page__stack">
          <span>{report.employee_name}</span>
          <span className="bbm-page__muted">{report.employee_no}</span>
        </span>
      ),
    },
    {
      key: "received",
      header: t("bbmList:table.received"),
      nowrap: true,
      sortable: true,
      firstSortDirection: "desc",
      // The month only: the other system sends the reports in batches (Darwinbox about once a week), so the day they
      // arrive is not when the employee submitted them. A report belongs to the month it was received in.
      render: (report) => formatMonth(report.received_at),
    },
    {
      key: "total",
      header: t("bbmList:table.total"),
      align: "right",
      nowrap: true,
      sortable: true,
      firstSortDirection: "desc",
      render: (report) => (
        <span className="bbm-page__stack">
          <span className="bbm-page__amount">{formatMoney(report.grand_total)}</span>
          <OcrTotal report={report} />
        </span>
      ),
    },
    {
      key: "differences",
      header: t("bbmList:table.differences"),
      sortable: true,
      firstSortDirection: "desc",
      render: (report) => <DifferingFields report={report} />,
    },
    {
      key: "status",
      header: t("bbmList:table.status"),
      nowrap: true,
      sortable: true,
      render: (report) => (
        <span className="bbm-page__stack bbm-page__status">
          <ReviewStatusBadge status={report.review_status} />
          <StatusNote report={report} />
        </span>
      ),
      cellTitle: (report) => report.decision?.reason ?? REVIEW_STATUSES[report.review_status].meaning,
    },
    {
      key: "open",
      header: <span className="blue-visually-hidden">{t("bbmList:table.open")}</span>,
      width: "40px",
      cellClassName: "bbm-page__chevron",
      render: () => <ChevronIcon />,
    },
  ];
}

/** "Revision 2 · 2 photos" under the code, when the report was revised or has more than one photo. */
function ReportExtras({ report }: { report: ReimbursementSummary }) {
  const extras = [
    report.revision_no > 1 ? t("bbmList:report.revision", { number: report.revision_no }) : null,
    report.photo_count > 1 ? t("bbmList:report.files", { count: report.photo_count }) : null,
  ].filter(Boolean);
  return extras.length ? <span className="bbm-page__muted">{extras.join(" · ")}</span> : null;
}

/** The mark of a report revised after an earlier revision was approved: the approved data changed. */
function RevisedAfterApproval() {
  return (
    <BlueTag
      className="bbm-page__revised"
      variant="warning"
      title={t("bbmList:report.revisedAfterApprovalHint")}
    >
      {t("bbmList:report.revisedAfterApproval")}
    </BlueTag>
  );
}

/** Under the status: who approved or rejected it, or that it came back after a rejection. */
function StatusNote({ report }: { report: ReimbursementSummary }) {
  const way = approvedBy(report);
  const text = report.decision
    ? t("bbmList:report.by", { name: report.decision.user_name })
    : way === "proceed"
      ? t("bbmList:report.byOcrProceed")
      : way === "matched"
        ? t("bbmList:report.byOcrMatched")
        : report.review_status === "needs_review" && report.previously_rejected
          ? t("bbmList:report.sentAgain")
          : null;
  return text ? <span className="bbm-page__muted">{text}</span> : null;
}

/** What the OCR read as the total, under the submitted one. */
function OcrTotal({ report }: { report: ReimbursementSummary }) {
  if (report.ocr_status === "processing") return <span className="bbm-page__muted">{t("bbmList:ocr.processing")}</span>;
  if (report.ocr_status === "failed") return <span className="bbm-page__muted">{t("bbmList:ocr.failed")}</span>;
  if (report.ocr_grand_total === null) {
    return (
      <span className="bbm-page__muted">
        {t("bbmList:ocr.label")} <span className="bbm-page__null">{NULL_VALUE}</span>
      </span>
    );
  }
  if (!totalDiffers(report)) return <span className="bbm-page__muted">{t("bbmList:ocr.same")}</span>;
  const gap = report.ocr_grand_total - report.grand_total;
  return (
    <span
      className="bbm-page__ocr-differs"
      title={t(gap < 0 ? "bbmList:ocr.less" : "bbmList:ocr.more", { amount: formatMoney(Math.abs(gap)) })}
    >
      {t("bbmList:ocr.label")} {formatMoney(report.ocr_grand_total)}
    </span>
  );
}

/** The fields the OCR found differences in, as chips ("Volume (L) ×2"). */
function DifferingFields({ report }: { report: ReimbursementSummary }) {
  if (report.ocr_status === "processing") return <span className="bbm-page__muted">{t("bbmList:differences.notYet")}</span>;
  if (report.ocr_status === "failed") return <span className="bbm-page__muted">{t("bbmList:differences.notCompared")}</span>;
  const fields = differingFields(report);
  if (fields.length === 0) return <span className="bbm-page__muted">{t("bbmList:differences.none")}</span>;
  return (
    <span className="bbm-page__fields">
      {fields.map(({ field, count }) => (
        <BlueTag key={field} title={t("bbmList:differences.count", { count, field: fieldLabel(field) })}>
          {fieldLabel(field)}
          {count > 1 ? <span className="bbm-page__field-count"> ×{count}</span> : null}
        </BlueTag>
      ))}
    </span>
  );
}

function SearchIcon() {
  return (
    <svg className="bbm-page__search-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <circle cx="7" cy="7" r="4.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="m10.5 10.5 3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg className="bbm-page__export-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M8 2.5v7.25M5 6.75l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2.75 10.5v1.75c0 .69.56 1.25 1.25 1.25h8c.69 0 1.25-.56 1.25-1.25V10.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg className="bbm-page__export-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M13 8a5 5 0 1 1-1.46-3.54" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M13 2.75v2.5h-2.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

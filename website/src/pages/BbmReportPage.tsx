import type { ReactNode } from "react";
import { t } from "../app/i18n";
import { linkTo } from "../app/router";
import { BlueAlert } from "../components/blue/Alert";
import { BlueButton } from "../components/blue/Button";
import { BlueCard } from "../components/blue/Card";
import { BlueEmptyState } from "../components/blue/EmptyState";
import { BlueLink } from "../components/blue/Link";
import { BlueModal } from "../components/blue/Modal";
import { BlueSpinner } from "../components/blue/Spinner";
import { BlueTable } from "../components/blue/Table";
import { BlueTextarea } from "../components/blue/Textarea";
import type { BlueTableColumn, BlueTableFooterRow } from "../components/blue/types";
import { CommentThread } from "../components/CommentThread";
import { OcrStatusBadge } from "../components/OcrStatusBadge";
import { FileViewer } from "../components/FileViewer";
import { ReviewStatusBadge } from "../components/ReviewStatusBadge";
import {
  COMMENT_MAX_LENGTH,
  CONFIDENT,
  REASON_MAX_LENGTH,
  hasCells,
  useBbmReportController,
  type BbmReportController,
  type DifferenceSide,
  type DifferenceView,
  type FileTotals,
  FUEL_PRICE_TOLERANCE,
  type FuelPriceCell,
  type HistoryEvent,
  type ItemFuelPriceRow,
  type ReviewDifference,
  type SameReceiptRow,
  SAME_RECEIPT_ID,
  doubleClaims,
} from "../controllers/BbmReportController";
import { FUEL_PRICES_PATH } from "../controllers/FuelPriceController";
import type { BbmItem, BbmOcrLine, BbmPhoto, BbmReimbursement, OcrStatus, ReviewDecision } from "../types/reimbursement";
import type { User } from "../types/user";
import { fieldLabel, formatField, priceToleranceText } from "../utils/bbmFields";
import {
  EMPTY,
  NULL_VALUE,
  formatDateTime,
  formatMoney,
  formatMonth,
  formatPercent,
  formatSeconds,
  formatTime,
} from "../utils/format";
import { OCR_STATUSES } from "../utils/ocrStatus";
import { REVIEW_STATUSES } from "../utils/reviewStatus";
import "../styles/pages/BbmReportPage.css";

interface BbmReportPageProps {
  code: string;
  user: User;
}

// One BBM report, laid out for reviewing it: what the OCR found on top, the receipt files next to it (in view
// while scrolling), then the submitted items and the OCR reading of each file in the same columns, the history and
// the comments.
// The decision (approve / reject) stays in view at the bottom; after it, the next report of the list opens.
export default function BbmReportPage({ code, user }: BbmReportPageProps) {
  const controller = useBbmReportController(code, user);

  return (
    <div className="bbm-report">
      <ReportNavigation controller={controller} />
      <ReportContent code={code} controller={controller} />
    </div>
  );
}

/** Back to the list as the reviewer left it, and the previous / next report in it. */
function ReportNavigation({ controller }: { controller: BbmReportController }) {
  const { backPath, backLabel, position, previousPath, nextPath } = controller.navigation;
  return (
    <nav className="bbm-report__nav" aria-label={t("report:nav.label")}>
      <BlueLink className="bbm-report__back" {...linkTo(backPath)}>
        <Icon name="back" />
        {backLabel}
      </BlueLink>
      {position ? (
        <div className="bbm-report__pager">
          <PagerLink path={previousPath} label={t("report:nav.previous")} icon="previous" />
          <span className="bbm-report__position">
            {t("report:nav.position", { number: position.number, total: position.count })}
          </span>
          <PagerLink path={nextPath} label={t("report:nav.next")} icon="next" />
        </div>
      ) : null}
    </nav>
  );
}

function PagerLink({ path, label, icon }: { path: string | null; label: string; icon: "previous" | "next" }) {
  const ariaLabel = icon === "previous" ? t("report:nav.previousReport") : t("report:nav.nextReport");
  const content = (
    <>
      {icon === "previous" ? <Icon name="previous" /> : null}
      <span>{label}</span>
      {icon === "next" ? <Icon name="next" /> : null}
    </>
  );
  if (!path) {
    return (
      <span className="bbm-report__pager-link bbm-report__pager-link--off" aria-disabled="true">
        {content}
      </span>
    );
  }
  return (
    <a className="bbm-report__pager-link" aria-label={ariaLabel} {...linkTo(path)}>
      {content}
    </a>
  );
}

function ReportContent({ code, controller }: { code: string; controller: BbmReportController }) {
  const { state, refreshing, reload, loadedAt, report, review } = controller;

  if (state.status === "loading") {
    return (
      <div className="bbm-report__centered">
        <BlueSpinner label={t("report:loading")} />
      </div>
    );
  }

  if (state.status === "error") {
    if (state.notFound) {
      return (
        <BlueCard>
          <BlueEmptyState
            title={t("report:notFound.title", { code })}
            action={<BackToList controller={controller} />}
          >
            {t("report:notFound.text")}
          </BlueEmptyState>
        </BlueCard>
      );
    }
    return (
      <div className="bbm-report__error">
        <BlueAlert variant="error" title={t("report:loadError")}>
          {state.message}
        </BlueAlert>
        <BlueButton variant="secondary" onClick={reload}>
          {t("actions.tryAgain")}
        </BlueButton>
      </div>
    );
  }

  if (!report || !review || loadedAt === null) return null;

  const manyPhotos = report.photos.length > 1;

  return (
    <>
      <header className="bbm-report__header">
        <div>
          <div className="bbm-report__title">
            <h1 className="page-title">{report.reimbursement_code}</h1>
            <ReviewStatusBadge status={report.review_status} />
          </div>
          <p className="page-subtitle">
            {report.employee_name} · {report.employee_no} ·{" "}
            {t("report:header.received", { month: formatMonth(report.received_at) })}
          </p>
        </div>
        <div className="bbm-report__sync">
          <span className="bbm-report__updated" aria-live="polite">
            {refreshing ? t("actions.refreshing") : t("updatedAt", { time: formatTime(loadedAt) })}
          </span>
          <BlueButton variant="secondary" size="sm" loading={refreshing} onClick={reload}>
            {t("actions.refresh")}
          </BlueButton>
        </div>
      </header>

      <div className="bbm-report__grid">
        <ReviewSummary controller={controller} report={report} />

        <aside className="bbm-report__photos" aria-label={manyPhotos ? t("report:files.many") : t("report:files.one")}>
          <BlueCard
            title={manyPhotos ? t("report:files.manyCount", { number: report.photos.length }) : t("report:files.one")}
          >
            <FileViewer key={report.reimbursement_code} label={t("report:receipt")} files={controller.files} />
          </BlueCard>
        </aside>

        <div className="bbm-report__main">
          <SameReceiptCard controller={controller} />
          <SubmittedItems controller={controller} items={review.items} manyPhotos={manyPhotos} />
          {report.photos.map((photo) =>
            photo.ocr ? <OcrReading key={photo.id} controller={controller} photo={photo} manyPhotos={manyPhotos} /> : null,
          )}
          <AllFilesTotal controller={controller} />
          <FuelPrices controller={controller} />
          <History controller={controller} />
          <Comments controller={controller} />
        </div>
      </div>

      <DecisionBar controller={controller} />
      <RejectDialog controller={controller} />
    </>
  );
}

function BackToList({ controller }: { controller: BbmReportController }) {
  return <BlueLink {...linkTo(controller.navigation.backPath)}>{t("report:nav.backToBbmList")}</BlueLink>;
}

// ---------------------------------------------------------------------------
// The decision: always in view at the bottom of the page
// ---------------------------------------------------------------------------

/** The decision was made by the signed-in user ("you"), not by someone else (named). */
function isMine(decision: Pick<ReviewDecision, "user_email">, userEmail: string): boolean {
  return decision.user_email === userEmail;
}

function decidedText(decision: ReviewDecision, userEmail: string): string {
  const mine = isMine(decision, userEmail);
  const name = decision.user_name;
  switch (decision.decision) {
    case "approved":
      return mine ? t("report:decision.approvedByYou") : t("report:decision.approvedBy", { name });
    case "rejected":
      return mine ? t("report:decision.rejectedByYou") : t("report:decision.rejectedBy", { name });
    case "reopened":
      return mine ? t("report:decision.reopenedByYou") : t("report:decision.reopenedBy", { name });
  }
}

/** When, and why. */
function decisionDetail(decision: ReviewDecision): ReactNode {
  return (
    <>
      {formatDateTime(decision.decided_at)}
      {decision.reason ? <> · “{decision.reason}”</> : null}
    </>
  );
}

type DecisionTone = "attention" | "processing" | "approved" | "rejected";

/** A link that looks like a button. */
function ButtonLink({ path, variant, children }: { path: string; variant: "primary" | "secondary"; children: ReactNode }) {
  return (
    <a className={`blue-button blue-button--${variant} blue-button--md bbm-decision__link`} {...linkTo(path)}>
      <span className="blue-button__label">{children}</span>
    </a>
  );
}

function DecisionBar({ controller }: { controller: BbmReportController }) {
  const { decision, review, report, navigation, userEmail } = controller;
  const { panel, deciding, advance } = decision;
  if (!panel || !review || !report) return null;
  const busy = deciding !== null;
  const count = review.differences.length;
  const earlier = doubleClaims(report);

  const rejectButton = (label: string) => (
    <BlueButton variant="secondary" disabled={busy} onClick={decision.openReject}>
      {label}
    </BlueButton>
  );
  // After a decision outside the "Needs review" list, or on a report decided before: on to the next one
  const onwards = navigation.nextPath ? (
    <ButtonLink path={navigation.nextPath} variant="primary">
      {t("report:nav.nextReport")}
      <Icon name="next" />
    </ButtonLink>
  ) : navigation.position ? (
    <ButtonLink path={navigation.backPath} variant="secondary">
      {t("report:nav.backToList")}
    </ButtonLink>
  ) : null;

  let tone: DecisionTone;
  let icon: IconName;
  let title: string;
  let detail: ReactNode;
  let actions: ReactNode;
  switch (panel.kind) {
    case "open":
      tone = panel.status === "processing" ? "processing" : "attention";
      icon = panel.status;
      title = panel.status === "processing" ? t("report:decision.open.processingTitle") : t("report:decision.open.title");
      detail =
        earlier.length > 0
          ? earlier.length === 1
            ? t("report:decision.open.doubleClaim", { code: earlier[0].reimbursement_code })
            : t("report:decision.open.doubleClaimMany", { count: earlier.length })
          : panel.status === "processing"
          ? t("report:decision.open.processing")
          : report.ocr_status === "failed"
            ? report.photos.some((photo) => photo.ocr_status === "failed" && photo.ocr_error_reason === "file_missing")
              ? t("report:decision.open.fileMissing")
              : t("report:decision.open.failed")
            : count > 0
              ? count === 1
                ? t("report:decision.open.oneDifference")
                : t("report:decision.open.differences", { n: count })
              : t("report:decision.open.noDifference");
      actions = (
        <>
          {rejectButton(t("report:decision.reject"))}
          <BlueButton variant="primary" loading={deciding === "approved"} disabled={busy} onClick={decision.approve}>
            {t("report:decision.approve")}
          </BlueButton>
        </>
      );
      break;
    case "auto":
      tone = "approved";
      icon = "matched";
      title = t("report:decision.auto.title");
      detail =
        panel.by === "matched"
          ? t("report:decision.auto.matched")
          : count === 1
            ? t("report:decision.auto.oneMisread")
            : t("report:decision.auto.misreads", { n: count });
      actions = (
        <>
          {rejectButton(t("report:decision.reject"))}
          {advance ? null : onwards}
        </>
      );
      break;
    case "decided": {
      const { decision: made, afterTakeBack } = panel;
      tone = made.decision;
      icon = made.decision === "approved" ? "matched" : "rejected";
      title = decidedText(made, userEmail);
      detail = decisionDetail(made);
      actions = (
        <>
          <BlueButton
            variant="ghost"
            loading={deciding === "reopened"}
            disabled={busy}
            title={t("report:decision.takeBackTitle", { status: REVIEW_STATUSES[afterTakeBack].label })}
            onClick={decision.takeBack}
          >
            {t("report:decision.takeBack")}
          </BlueButton>
          {made.decision === "approved" ? (
            rejectButton(t("report:decision.rejectInstead"))
          ) : (
            <BlueButton variant="secondary" loading={deciding === "approved"} disabled={busy} onClick={decision.approve}>
              {t("report:decision.approveInstead")}
            </BlueButton>
          )}
          {onwards}
        </>
      );
      break;
    }
  }

  const caption =
    advance && (panel.kind === "open" || panel.kind === "auto")
      ? t("report:decision.opensNext", { code: advance.code, number: advance.number, total: advance.count })
      : null;

  return (
    <section ref={decision.barRef} className={`bbm-decision bbm-decision--${tone}`} aria-label={t("report:decision.label")}>
      <span className="bbm-decision__icon">
        <Icon name={icon} />
      </span>
      <div className="bbm-decision__text">
        <p className="bbm-decision__title">{title}</p>
        <p className="bbm-decision__detail">{detail}</p>
      </div>
      <div className="bbm-decision__side">
        <div className="bbm-decision__actions">{actions}</div>
        {caption ? <p className="bbm-decision__caption">{caption}</p> : null}
      </div>
    </section>
  );
}

/** Rejecting needs a reason: ready-made ones come from the differences the OCR found. */
function RejectDialog({ controller }: { controller: BbmReportController }) {
  const { rejectDialog: dialog, report } = controller;
  if (!report) return null;
  const length = dialog.reason.trim().length;

  function addSuggestion(suggestion: string) {
    dialog.add(suggestion);
    // Back to typing, after the added reason
    requestAnimationFrame(() => {
      const field = document.getElementById("bbm-reject-reason");
      if (!(field instanceof HTMLTextAreaElement)) return;
      field.focus();
      field.setSelectionRange(field.value.length, field.value.length);
    });
  }

  return (
    <BlueModal
      open={dialog.open}
      onClose={dialog.close}
      dismissible={!dialog.saving}
      title={t("report:rejectDialog.title", { code: report.reimbursement_code })}
      footer={
        <>
          <BlueButton variant="secondary" disabled={dialog.saving} onClick={dialog.close}>
            {t("actions.cancel")}
          </BlueButton>
          <BlueButton variant="danger" loading={dialog.saving} onClick={dialog.submit}>
            {t("report:rejectDialog.submit")}
          </BlueButton>
        </>
      }
    >
      <p className="bbm-reject__text">
        {t("report:rejectDialog.text", { name: report.employee_name })}
      </p>
      <BlueTextarea
        id="bbm-reject-reason"
        label={t("report:rejectDialog.reasonLabel")}
        rows={4}
        required
        data-autofocus
        value={dialog.reason}
        maxLength={REASON_MAX_LENGTH}
        readOnly={dialog.saving}
        error={dialog.error ?? undefined}
        helperText={t("report:rejectDialog.reasonHelp", { length, max: REASON_MAX_LENGTH })}
        onChange={(event) => dialog.change(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) dialog.submit();
        }}
      />
      <div className="bbm-reject__suggestions" role="group" aria-labelledby="bbm-reject-suggestions">
        <span id="bbm-reject-suggestions" className="bbm-reject__suggestions-label">
          {t("report:rejectDialog.addReason")}
        </span>
        {dialog.suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="bbm-reject__chip"
            disabled={dialog.saving || dialog.reason.includes(suggestion)}
            onClick={() => addSuggestion(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </BlueModal>
  );
}

// ---------------------------------------------------------------------------
// History of the report: received, OCR readings, decisions
// ---------------------------------------------------------------------------

type HistoryTone = "neutral" | "attention" | "info" | "approved" | "rejected";

function historyLine(event: HistoryEvent, userEmail: string): { tone: HistoryTone; text: string; reason: string | null } {
  switch (event.kind) {
    case "received":
      return { tone: "neutral", text: t("report:history.received"), reason: null };
    case "read": {
      const { label, hint } = OCR_STATUSES[event.status];
      const tone =
        event.status === "proceed" ? "info" : event.status === "matched" ? "approved" : "attention";
      // Only the first letter is lowered, so "OCR" stays as it is
      const lowered = hint.charAt(0).toLowerCase() + hint.slice(1);
      return { tone, text: t("report:history.read", { status: label, hint: lowered }), reason: null };
    }
    case "decision": {
      const made = event.decision;
      const tone = made.decision === "reopened" ? "neutral" : made.decision;
      return { tone, text: decidedText(made, userEmail), reason: made.reason };
    }
  }
}

function History({ controller }: { controller: BbmReportController }) {
  const { history, report, userEmail } = controller;
  if (!report) return null;

  return (
    <BlueCard header={<CardHeader title={t("report:history.title")} meta={t("report:history.newestFirst")} />}>
      <ol className="bbm-history">
        {history.map((event) => {
          const { tone, text, reason } = historyLine(event, userEmail);
          const key = `${event.kind}-${event.kind === "decision" ? event.decision.id : ""}`;
          return (
            <li key={key} className={`bbm-history__event bbm-history__event--${tone}`}>
              <span className="bbm-history__dot" aria-hidden="true" />
              <div className="bbm-history__body">
                <span className="bbm-history__text">{text}</span>
                <span className="bbm-history__meta">
                  {/* Received: the month only (the other system sends reports in batches, see the BBM list) */}
                  {event.kind === "received" ? formatMonth(event.at) : formatDateTime(event.at)}
                </span>
                {reason ? <q className="bbm-history__reason">{reason}</q> : null}
              </div>
            </li>
          );
        })}
      </ol>
    </BlueCard>
  );
}

// ---------------------------------------------------------------------------
// The review summary: what the OCR found and what to check
// ---------------------------------------------------------------------------

/** The line under the headline once a reviewer decided. */
function decidedSummary(): string {
  return t("report:summary.decided");
}

/** The headline and the line under it, for the status of the report (decided: a reviewer already looked at it). */
function summaryText(status: OcrStatus, decided: boolean, differences: number, photosRead: number, photos: number) {
  switch (status) {
    case "needs_review":
      if (decided) {
        return {
          title:
            differences === 0
              ? t("report:summary.askedForCheck")
              : t("report:summary.unexplained", { count: differences }),
          text: decidedSummary(),
        };
      }
      return {
        title: differences === 0 ? t("report:summary.checkFile") : t("report:summary.toCheck", { count: differences }),
        text: differences === 0 ? OCR_STATUSES.needs_review.meaning : t("report:summary.explainedBelow"),
      };
    case "proceed":
      return {
        title: differences === 1 ? t("report:summary.oneMisread") : t("report:summary.misreads", { n: differences }),
        text: OCR_STATUSES.proceed.meaning,
      };
    case "matched":
      return { title: t("report:summary.noDifferences"), text: OCR_STATUSES.matched.meaning };
    case "failed":
      return {
        title: photos === 1 ? t("report:summary.failedOne") : t("report:summary.failedSome"),
        // What to do depends on why: it is under each file's reason.
        text: decided ? decidedSummary() : t("report:summary.failedText"),
      };
    case "processing":
      return photosRead === 0
        ? { title: OCR_STATUSES.processing.label, text: t("report:summary.processing") }
        : { title: t("report:summary.partly"), text: t("report:summary.partlyText", { read: photosRead, count: photos }) };
  }
}

/** What the OCR found, in the order a reviewer needs it: what is wrong, then each difference with both values side
 *  by side and which one the other numbers on the receipt support. The totals are compared under the tables. */
function ReviewSummary({ controller, report }: { controller: BbmReportController; report: BbmReimbursement }) {
  const { review } = controller;
  if (!review) return null;
  const status = report.ocr_status;
  const decided = report.decision !== null;
  const { fieldViews } = review;
  const single = fieldViews.length === 1 ? fieldViews[0] : null;
  // One thing to check: name it. Several: count them (summaryText).
  const subject =
    status === "needs_review" || status === "proceed"
      ? single
        ? { title: single.title, summary: single.summary }
        : review.totalHeadline
      : null;
  // A receipt an earlier report claimed comes first, whatever the OCR found (not once decided: the card shows it then)
  const doubleClaim = controller.sameReceipt.doubleClaim;
  const { title, text } = doubleClaim
    ? doubleClaim
    : subject
      ? { title: subject.title, text: decided ? decidedSummary() : subject.summary }
      : summaryText(status, decided, fieldViews.length, review.photosRead, report.photos.length);
  const tone = decided ? "decided" : doubleClaim ? "needs_review" : status;

  return (
    <section className={`bbm-report__summary bbm-report__summary--${tone}`} aria-labelledby="bbm-report-summary-title">
      <div className="bbm-report__summary-head">
        <span className="bbm-report__summary-icon">
          <Icon name={doubleClaim ? "needs_review" : status} />
        </span>
        <div>
          <h2 id="bbm-report-summary-title" className="bbm-report__summary-title">
            {title}
          </h2>
          <p className="bbm-report__summary-text">{text}</p>
          {doubleClaim ? (
            <BlueButton
              className="bbm-report__summary-action"
              variant="secondary"
              size="sm"
              onClick={controller.sameReceipt.show}
            >
              {t("report:sameReceipt.compare")}
              <Icon name="down" />
            </BlueButton>
          ) : null}
          {review.failed.map((file) => (
            <p key={file.name} className="bbm-report__summary-reason">
              {report.photos.length > 1 ? `${file.name}: ` : ""}
              {t(`report:failure.${file.reason}.text`)} ({t("report:summary.tried", { count: file.attempts })})
              <span className="bbm-report__summary-todo">{t(`report:failure.${file.reason}.todo`)}</span>
            </p>
          ))}
          {controller.ocrRetry.available ? (
            <BlueButton
              className="bbm-report__summary-action"
              variant="secondary"
              size="sm"
              loading={controller.ocrRetry.retrying}
              onClick={controller.ocrRetry.retry}
              title={t("report:summary.retryTitle")}
            >
              {t("report:summary.retry")}
            </BlueButton>
          ) : null}
        </div>
      </div>

      {fieldViews.length > 0 && doubleClaim ? (
        <p className="bbm-report__summary-subtitle">{t("report:sameReceipt.ocrFound")}</p>
      ) : null}
      {fieldViews.length > 0 ? (
        <ul className="bbm-report__differences" aria-label={t("report:summary.differences")}>
          {fieldViews.map((view) => (
            <DifferenceRow
              key={view.difference.id}
              view={view}
              // The headline already says it when this is the only difference (not once decided: it says that then)
              hint={single && !decided && view.hint === single.summary ? null : view.hint}
              onShow={() => controller.showDifference(view.difference)}
            />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function DifferenceRow({ view, hint, onShow }: { view: DifferenceView; hint: string | null; onShow: () => void }) {
  return (
    <li className="bbm-difference">
      <div className="bbm-difference__head">
        <span className="bbm-difference__name">
          <span className="bbm-difference__label">{view.label}</span>
          {view.where ? <span className="bbm-report__muted">{view.where}</span> : null}
        </span>
        {hasCells(view.difference) ? (
          <BlueButton className="bbm-difference__show" variant="ghost" size="sm" onClick={onShow}>
            {t("report:difference.showInTables")}
            <Icon name="down" />
          </BlueButton>
        ) : null}
      </div>
      <div className="bbm-difference__sides">
        <SideTile
          caption={view.submittedCaption ?? t("report:difference.submitted")}
          side={view.submitted}
          source="submitted"
        />
        <SideTile caption={t("report:difference.onReceipt")} side={view.receipt} source="receipt" />
      </div>
      {hint ? <p className="bbm-difference__hint">{hint}</p> : null}
    </li>
  );
}

/** One value of a difference, and nothing else (why is under both values). Marked: the characters that differ from
 *  the other value. Coloured by what the other numbers on the receipt say: red when the submitted value doesn't fit
 *  them, amber when the OCR misread. */
function SideTile({ caption, side, source }: { caption: string; side: DifferenceSide; source: "submitted" | "receipt" }) {
  return (
    <div className={`bbm-side bbm-side--${side.tone} bbm-side--${source}`}>
      <span className="bbm-side__caption">{caption}</span>
      <span className={side.empty ? "bbm-side__value bbm-side__value--empty" : "bbm-side__value"}>
        {side.parts.map((part, index) =>
          part.changed ? (
            <mark key={index} className="bbm-side__changed">
              {part.text}
            </mark>
          ) : (
            <span key={index}>{part.text}</span>
          ),
        )}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The submitted items and the OCR reading, in the same columns so they can be compared top to bottom
// ---------------------------------------------------------------------------

/** Widths shared by both tables; the product column takes the rest. */
const WIDTHS = {
  ref: "84px",
  date_of_expense: "100px",
  price_per_liter: "108px",
  volume_liter: "88px",
  total_price: "120px",
  extra: "96px",
} as const;

const COMPARED_FIELDS = ["product_name", "date_of_expense", "price_per_liter", "volume_liter", "total_price"] as const;

function widthOf(field: string): string | undefined {
  return (WIDTHS as Record<string, string>)[field];
}

function alignOf(field: string): "right" | undefined {
  return field === "product_name" || field === "date_of_expense" ? undefined : "right";
}

// ---------------------------------------------------------------------------
// The same receipt in other reports: what a reviewer compares before deciding a double claim
// ---------------------------------------------------------------------------

/** Each other report claiming the same receipt: what it is to this one, how it was decided, who sent it and when,
 *  and what both have. It opens in a new tab, so this report stays where the reviewer left it. */
function SameReceiptCard({ controller }: { controller: BbmReportController }) {
  const { rows } = controller.sameReceipt;
  if (rows.length === 0) return null;
  return (
    <div id={SAME_RECEIPT_ID} className="bbm-report__same">
      <BlueCard
        className="bbm-report__table-card"
        header={
          <CardHeader title={t("report:sameReceipt.card")} count={rows.length} meta={t("report:sameReceipt.cardMeta")} />
        }
      >
        <ul className="bbm-same">
          {rows.map((row) => (
            <SameReceiptItem key={row.entry.reimbursement_code} row={row} />
          ))}
        </ul>
      </BlueCard>
    </div>
  );
}

function SameReceiptItem({ row }: { row: SameReceiptRow }) {
  const { entry } = row;
  return (
    <li className={row.problem ? "bbm-same__item bbm-same__item--problem" : "bbm-same__item"}>
      <div className="bbm-same__head">
        <span className={row.problem ? "bbm-same__kind bbm-same__kind--problem" : "bbm-same__kind"}>
          {t(`report:sameReceipt.kind.${entry.kind}`)}
        </span>
        <BlueLink
          className="bbm-same__code"
          href={row.path}
          external
          title={t("report:sameReceipt.open", { code: entry.reimbursement_code })}
        >
          {entry.reimbursement_code}
          <Icon name="external" />
        </BlueLink>
        <ReviewStatusBadge status={entry.review_status} />
        {row.decidedBy ? <span className="bbm-report__muted">{row.decidedBy}</span> : null}
      </div>
      <p className="bbm-same__text">{t(`report:sameReceipt.kindText.${entry.kind}`)}</p>
      {row.reason ? <q className="bbm-same__reason">{row.reason}</q> : null}
      <ul className="bbm-same__facts">
        <li className={row.otherEmployee ? "bbm-same__other-employee" : undefined}>
          {row.otherEmployee
            ? t("report:sameReceipt.otherEmployee", { name: entry.employee_name, number: entry.employee_no })
            : t("report:sameReceipt.sameEmployee")}
        </li>
        <li>{t("report:sameReceipt.received", { date: formatDateTime(entry.received_at) })}</li>
        {row.evidence.map((evidence) => (
          <li key={evidence} className="bbm-same__evidence">
            {evidence}
          </li>
        ))}
      </ul>
    </li>
  );
}

function CardHeader({ title, count, meta }: { title: string; count?: number; meta?: ReactNode }) {
  return (
    <div className="blue-card__header bbm-report__card-header">
      <span>
        {title}
        {count !== undefined ? <span className="bbm-report__count">{count}</span> : null}
      </span>
      {meta ? <span className="bbm-report__card-meta">{meta}</span> : null}
    </div>
  );
}

function differenceIds(differences: ReviewDifference[] | undefined): string | undefined {
  return differences?.map((difference) => difference.id).join(" ");
}

function SubmittedItems({
  controller,
  items,
  manyPhotos,
}: {
  controller: BbmReportController;
  items: BbmItem[];
  manyPhotos: boolean;
}) {
  const { itemDifferences, review } = controller;

  function itemCell(field: Exclude<keyof BbmItem, "id" | "item_id" | "photo_ids" | "fuel_price">): BlueTableColumn<BbmItem> {
    // The price per liter is not submitted: the amount divided by the volume, compared with the price on the receipt
    const computed = field === "price_per_liter";
    return {
      key: field,
      header: computed ? (
        <span className="bbm-report__stack">
          <span>{fieldLabel(field)}</span>
          <span className="bbm-report__computed">{t("report:items.computed")}</span>
        </span>
      ) : (
        fieldLabel(field)
      ),
      label: computed ? `${fieldLabel(field)} (${t("report:items.computed")})` : undefined,
      align: alignOf(field),
      width: widthOf(field) ?? (field === "kilometer" ? WIDTHS.extra : undefined),
      nowrap: field !== "product_name",
      render: (item) => (
        <span className="bbm-report__stack" data-differences={differenceIds(itemDifferences(item.id, field))}>
          <span>{formatField(field, item[field])}</span>
        </span>
      ),
      cellClassName: (item) =>
        [
          computed ? "bbm-report__cell--computed" : null,
          itemDifferences(item.id, field) ? "bbm-report__cell--differs" : null,
        ]
          .filter(Boolean)
          .join(" ") || undefined,
      cellTitle: (item) =>
        itemDifferences(item.id, field)
          ?.map((difference) => difference.description)
          .join("\n") ?? (computed ? t("report:items.computedTitle", { percent: priceToleranceText() }) : undefined),
    };
  }

  const columns: BlueTableColumn<BbmItem>[] = [
    {
      key: "item_id",
      header: t("report:items.item"),
      width: WIDTHS.ref,
      nowrap: true,
      // With several receipt files: the ones of the item, under its id
      render: (item) =>
        manyPhotos ? (
          <span className="bbm-report__stack">
            <span>{item.item_id}</span>
            <span className="bbm-report__item-files">{review?.fileNamesOf(item).join(", ")}</span>
          </span>
        ) : (
          item.item_id
        ),
    },
    ...COMPARED_FIELDS.map(itemCell),
    itemCell("kilometer"),
  ];
  const totals = controller.review?.totals.submitted;
  const differs = controller.review?.totals.differs ?? false;
  const footer: BlueTableFooterRow[] = totals
    ? [
        ...(totals.note
          ? [{ key: "amounts", label: t("report:totals.amounts"), cells: { total_price: formatMoney(totals.amounts) } }]
          : []),
        {
          key: "total",
          label: t("report:totals.toReimburse"),
          cells: { total_price: <TotalValue value={totals.total} /> },
          cellClassName: { total_price: differs ? "bbm-report__cell--differs" : undefined },
        },
      ]
    : [];

  return (
    <BlueCard
      className="bbm-report__table-card"
      header={<CardHeader title={t("report:items.title")} count={items.length} meta={t("report:items.meta")} />}
    >
      <BlueTable
        dense
        stackOnMobile
        className="bbm-report__aligned"
        caption={t("report:items.title")}
        columns={columns}
        data={items}
        rowKey={(item) => item.id}
        footer={footer}
      />
      {totals?.note ? <p className="bbm-report__table-note">{totals.note}</p> : null}
    </BlueCard>
  );
}

// ---------------------------------------------------------------------------
// The fuel price page's price of each item's fuel, next to the price per liter worked out from the item
// ---------------------------------------------------------------------------

function FuelPriceValue({ cell, gap }: { cell: FuelPriceCell; gap?: string | null }) {
  return (
    <span className="bbm-report__stack">
      <span className={cell.known ? "bbm-report__fuel-value" : "bbm-report__fuel-missing"}>{cell.value}</span>
      {cell.note ? <span className="bbm-report__muted">{cell.note}</span> : null}
      {gap ? <span className="bbm-report__fuel-gap">{gap}</span> : null}
    </span>
  );
}

function FuelPrices({ controller }: { controller: BbmReportController }) {
  const rows = controller.fuelPrices;
  if (rows.length === 0) return null;
  const columns: BlueTableColumn<ItemFuelPriceRow>[] = [
    { key: "item", header: t("report:items.item"), width: WIDTHS.ref, nowrap: true, render: (row) => row.item.item_id },
    {
      key: "fuel",
      header: t("report:fuelPrice.fuel"),
      render: (row) => (
        <span className="bbm-report__stack">
          <span className={row.fuelKnown ? "bbm-report__fuel-name" : "bbm-report__fuel-missing"}>{row.fuel}</span>
          <span className="bbm-report__muted">{row.fuelNote}</span>
        </span>
      ),
    },
    {
      key: "computed",
      header: (
        <span className="bbm-report__stack">
          <span>{fieldLabel("price_per_liter")}</span>
          <span className="bbm-report__computed">{t("report:items.computed")}</span>
        </span>
      ),
      label: `${fieldLabel("price_per_liter")} (${t("report:items.computed")})`,
      align: "right",
      width: "128px",
      nowrap: true,
      render: (row) => (
        <span className="bbm-report__stack">
          <span className="bbm-report__fuel-value">{formatMoney(row.item.price_per_liter)}</span>
          <span className="bbm-report__muted">{t("report:fuelPrice.computedNote")}</span>
        </span>
      ),
    },
    {
      key: "on_date",
      header: (
        <span className="bbm-report__stack">
          <span>{t("report:fuelPrice.onDate")}</span>
          <span className="bbm-report__computed">{t("report:fuelPrice.onDateHint")}</span>
        </span>
      ),
      label: t("report:fuelPrice.onDate"),
      align: "right",
      width: "176px",
      render: (row) => <FuelPriceValue cell={row.onDate} gap={row.gap} />,
      cellClassName: (row) => (row.gap ? "bbm-report__cell--differs" : undefined),
    },
    {
      key: "today",
      header: t("report:fuelPrice.today"),
      align: "right",
      width: "176px",
      render: (row) => <FuelPriceValue cell={row.today} />,
    },
  ];

  return (
    <BlueCard
      className="bbm-report__table-card"
      header={
        <CardHeader
          title={t("report:fuelPrice.title")}
          meta={
            <>
              {t("report:fuelPrice.meta")}
              <BlueLink {...linkTo(FUEL_PRICES_PATH)}>{t("report:fuelPrice.open")}</BlueLink>
            </>
          }
        />
      }
    >
      <BlueTable
        dense
        stackOnMobile
        caption={t("report:fuelPrice.title")}
        columns={columns}
        data={rows}
        rowKey={(row) => row.item.id}
      />
      <p className="bbm-report__table-note">
        {t("report:fuelPrice.note", { percent: formatPercent(FUEL_PRICE_TOLERANCE) })}
      </p>
    </BlueCard>
  );
}

type LineField = keyof BbmOcrLine["confidence"];

function OcrReading({
  controller,
  photo,
  manyPhotos,
}: {
  controller: BbmReportController;
  photo: BbmPhoto;
  manyPhotos: boolean;
}) {
  const { lineDifferences } = controller;
  const result = photo.ocr;
  if (!result) return null;
  const title = manyPhotos ? t("report:ocr.titleOf", { name: photo.name }) : t("report:ocr.title");
  // With several files: the items this one was compared with (the ones it was sent with)
  const comparedWith = manyPhotos ? (controller.review?.itemIdsOf(photo) ?? []) : [];

  function lineCell(field: LineField): BlueTableColumn<BbmOcrLine> {
    return {
      key: field,
      header: field === "date_of_expense" ? t("report:ocr.printedDate") : fieldLabel(field),
      align: alignOf(field),
      width: widthOf(field) ?? (field === "discount" ? WIDTHS.extra : undefined),
      // The printed date is free text ("Kamis, 08 Januari 2026"), so it may wrap like the product
      nowrap: field !== "product_name" && field !== "date_of_expense",
      render: (line) => {
        const value = line[field];
        const confidence = line.confidence[field];
        const unsure = typeof confidence === "number" && confidence < CONFIDENT;
        return (
          <span className="bbm-report__stack" data-differences={differenceIds(lineDifferences(line.id, field))}>
            {value === null && confidence === null ? (
              EMPTY
            ) : value === null ? (
              <span className="bbm-report__null">{NULL_VALUE}</span>
            ) : (
              <span>{formatField(field, value)}</span>
            )}
            {unsure ? (
              <span className="bbm-report__confidence" title={t("report:ocr.notSure")}>
                {t("report:ocr.sure", { percent: formatPercent(confidence) })}
              </span>
            ) : null}
          </span>
        );
      },
      cellClassName: (line) => (lineDifferences(line.id, field) ? "bbm-report__cell--differs" : undefined),
      cellTitle: (line) =>
        lineDifferences(line.id, field)
          ?.map((difference) => difference.description)
          .join("\n"),
    };
  }

  const columns: BlueTableColumn<BbmOcrLine>[] = [
    { key: "line", header: t("report:receipt"), width: WIDTHS.ref, render: (_line, index) => index + 1 },
    ...COMPARED_FIELDS.map(lineCell),
    lineCell("discount"),
  ];
  const totals = controller.review?.totals.files.get(photo.id);
  // With one file its total is the receipt total compared with the submitted one; with several, their sum is
  // (AllFilesTotal)
  const gap = manyPhotos ? null : (controller.review?.totals.gap ?? null);
  const footer: BlueTableFooterRow[] = totals ? ocrFooter(totals, gap) : [];

  return (
    <BlueCard
      className="bbm-report__table-card"
      header={
        <CardHeader
          title={title}
          count={result.lines.length}
          meta={
            <>
              {manyPhotos ? <OcrStatusBadge status={result.decision} /> : null}
              {comparedWith.length > 0 ? (
                <span>{t("report:ocr.comparedWith", { count: comparedWith.length, items: comparedWith.join(", ") })}</span>
              ) : null}
              {t("report:ocr.read", {
                date: formatDateTime(result.processed_at),
                duration: formatSeconds(result.elapsed_seconds),
              })}
            </>
          }
        />
      }
    >
      <BlueTable
        dense
        stackOnMobile
        className="bbm-report__aligned"
        caption={title}
        columns={columns}
        data={result.lines}
        rowKey={(line) => line.id}
        empty={<BlueEmptyState title={t("report:ocr.emptyTitle")}>{t("report:ocr.emptyText")}</BlueEmptyState>}
        footer={footer}
      />
      {totals?.note ? <p className="bbm-report__table-note bbm-report__table-note--warning">{totals.note}</p> : null}
      <p className="bbm-report__table-note">{t("report:ocr.sureNote", { percent: formatPercent(CONFIDENT) })}</p>
    </BlueCard>
  );
}

/** The footer of an OCR table: the amounts and discounts read (left out when there is no discount and the printed
 *  total is just the amounts), then the total paid printed on the receipts, with the submitted one next to it. */
function ocrFooter(totals: FileTotals, gap: string | null): BlueTableFooterRow[] {
  const paid: BlueTableFooterRow = {
    key: "paid",
    label: totals.simple ? t("report:totals.fromOcr") : t("report:totals.fromOcrPrinted"),
    cells: { total_price: <TotalValue value={totals.printed} confidence={totals.confidence} gap={gap} /> },
    cellClassName: { total_price: gap ? "bbm-report__cell--differs" : undefined },
  };
  if (totals.simple) return [paid];
  return [
    {
      key: "amounts",
      label: t("report:totals.amountsAndDiscounts"),
      cells: { total_price: formatMoney(totals.amounts), discount: formatMoney(totals.discounts) },
    },
    paid,
  ];
}

/** A total in a table footer, with how sure the OCR was (when unsure) and how far it
 *  is from the submitted total (when it isn't the same). */
function TotalValue({
  value,
  confidence = null,
  gap = null,
}: {
  value: number | null;
  confidence?: number | null;
  gap?: string | null;
}) {
  return (
    <span className="bbm-report__stack">
      {value === null ? <span className="bbm-report__null">{NULL_VALUE}</span> : <span>{formatMoney(value)}</span>}
      {confidence !== null && confidence < CONFIDENT ? (
        <span className="bbm-report__confidence">{t("report:ocr.sure", { percent: formatPercent(confidence) })}</span>
      ) : null}
      {gap ? <span className="bbm-report__gap">{gap}</span> : null}
    </span>
  );
}

/** With several receipt files: what their receipts printed as paid, added up, against the submitted total. */
function AllFilesTotal({ controller }: { controller: BbmReportController }) {
  const allFiles = controller.review?.totals.allFiles;
  if (!allFiles) return null;
  const { parts, total, gap } = allFiles;
  return (
    <section
      className={`bbm-report__all-files${gap ? " bbm-report__all-files--differs" : ""}`}
      aria-label={t("report:totals.allFiles")}
    >
      <span className="bbm-report__all-files-label">{t("report:totals.allFilesCount", { files: parts.length })}</span>
      <span className="bbm-report__all-files-sum">
        <span className="bbm-report__all-files-parts">
          {parts.map((part) => formatMoney(part.printed)).join(" + ")} =
        </span>
        <span className="bbm-report__stack">
          <strong>{formatMoney(total)}</strong>
          {gap ? <span className="bbm-report__gap">{gap}</span> : null}
        </span>
      </span>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Comments on the whole report
// ---------------------------------------------------------------------------

function Comments({ controller }: { controller: BbmReportController }) {
  const { report, userEmail, addComment, editComment, removeComment } = controller;
  if (!report) return null;

  return (
    <BlueCard
      header={
        <CardHeader title={t("report:comments.title")} count={report.comments.length} meta={t("report:comments.meta")} />
      }
    >
      <CommentThread
        comments={report.comments}
        currentUserEmail={userEmail}
        onAdd={addComment}
        onEdit={editComment}
        onDelete={removeComment}
        maxLength={COMMENT_MAX_LENGTH}
      />
    </BlueCard>
  );
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

type IconName = "back" | "previous" | "next" | "arrow" | "down" | "check" | "cross" | "rejected" | "external" | OcrStatus;

const ICON_PATHS: Record<IconName, ReactNode> = {
  back: <path d="M12.5 4 6.5 10l6 6" />,
  previous: <path d="M12.5 4 6.5 10l6 6" />,
  next: <path d="m7.5 4 6 6-6 6" />,
  arrow: <path d="M4 10h11m-4-4 4 4-4 4" />,
  down: <path d="M10 4v11m-4-4 4 4 4-4" />,
  check: <path d="m4.5 10.5 3.5 3.5 7.5-8" />,
  cross: <path d="m5.5 5.5 9 9m0-9-9 9" />,
  external: <path d="M11.5 3.5h5v5m0-5-7 7M14.5 11.5v4a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h4" />,
  rejected: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="m7.5 7.5 5 5m0-5-5 5" />
    </>
  ),
  needs_review: (
    <>
      <path d="M10 3.5 17.5 16.5h-15z" />
      <path d="M10 8.5v3.5m0 2.2v.1" />
    </>
  ),
  proceed: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 9v4.5m0-7v.1" />
    </>
  ),
  matched: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="m6.8 10.2 2.2 2.2 4.2-4.6" />
    </>
  ),
  processing: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4.2l2.8 1.8" />
    </>
  ),
  failed: (
    <>
      <path d="M5.5 2.5h6l3.5 3.5v11.5h-9.5z" />
      <path d="m8 9.5 4 4m0-4-4 4" />
    </>
  ),
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg className="bbm-report__icon" viewBox="0 0 20 20" aria-hidden="true">
      {ICON_PATHS[name]}
    </svg>
  );
}

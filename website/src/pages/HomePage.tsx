import type { ReactNode } from "react";
import { t } from "../app/i18n";
import { linkTo } from "../app/router";
import { BlueAlert } from "../components/blue/Alert";
import { BlueBadge } from "../components/blue/Badge";
import { BlueButton } from "../components/blue/Button";
import { BlueCard } from "../components/blue/Card";
import { BlueEmptyState } from "../components/blue/EmptyState";
import { BlueLink } from "../components/blue/Link";
import { StatusBar, StatusDot } from "../components/StatusBar";
import { useHomeController, type HomeController, type MonthSummary } from "../controllers/HomeController";
import type { User } from "../types/user";
import { formatMoney, formatTime } from "../utils/format";
import "../styles/pages/HomePage.css";

interface HomePageProps {
  user: User;
}

export default function HomePage({ user }: HomePageProps) {
  const home = useHomeController(user);

  return (
    <div className="home-page">
      <header className="home-page__header">
        <div>
          <p className="home-page__today">{home.today}</p>
          <h1 className="page-title">{home.greeting}</h1>
          <p className="page-subtitle">{t("home:subtitle")}</p>
        </div>
        <div className="home-page__sync">
          {home.loadedAt !== null ? (
            <span className="home-page__updated" aria-live="polite">
              {home.refreshing ? t("actions.refreshing") : t("updatedAt", { time: formatTime(home.loadedAt) })}
            </span>
          ) : null}
          <BlueButton variant="secondary" size="sm" loading={home.refreshing} onClick={home.reload}>
            {t("actions.refresh")}
          </BlueButton>
        </div>
      </header>

      <Attention home={home} />

      {home.reports.status !== "error" ? <BbmOverview home={home} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// What needs the reviewer
// ---------------------------------------------------------------------------

function Attention({ home }: { home: HomeController }) {
  const { reports, attention } = home;

  if (reports.status === "loading") {
    return (
      <BlueCard className="home-page__attention" bordered>
        <Placeholder lines={["40%", "65%", "30%"]} label={t("home:loadingReports")} />
      </BlueCard>
    );
  }

  if (reports.status === "error") {
    return (
      <div className="home-page__error">
        <BlueAlert variant="error" title={t("home:loadError")}>
          {reports.message}
        </BlueAlert>
        <BlueButton variant="secondary" onClick={home.reloadReports}>
          {t("actions.tryAgain")}
        </BlueButton>
      </div>
    );
  }

  if (home.bbm.reports === 0) {
    return (
      <BlueCard className="home-page__attention">
        <BlueEmptyState title={t("home:empty.title")}>{t("home:empty.text")}</BlueEmptyState>
      </BlueCard>
    );
  }

  if (attention.count === 0) {
    return (
      <BlueCard className="home-page__attention home-page__attention--clear">
        <div className="home-page__attention-body">
          <div className="home-page__attention-text">
            <p className="home-page__eyebrow home-page__eyebrow--clear">
              <CheckIcon /> {t("home:clear.eyebrow")}
            </p>
            <h2 className="home-page__attention-title">{t("home:clear.title")}</h2>
            <p className="home-page__attention-meta">
              {attention.processing > 0
                ? t("home:clear.processing", { count: attention.processing })
                : t("home:clear.done")}
            </p>
          </div>
        </div>
      </BlueCard>
    );
  }

  return (
    <BlueCard className="home-page__attention home-page__attention--review">
      <div className="home-page__attention-body">
        <div className="home-page__attention-text">
          <p className="home-page__eyebrow">
            <StatusDot status="needs_review" /> {t("home:attention.eyebrow")}
          </p>
          <h2 className="home-page__attention-title">
            <span className="home-page__attention-count">{attention.count}</span>{" "}
            {t("home:attention.title", { count: attention.count })}
          </h2>
          {attention.months.length > 0 ? (
            <div className="home-page__chips">
              <span className="home-page__chips-label">{t("home:attention.receivedIn")}</span>
              {attention.months.map((month) => (
                <a
                  key={month.period}
                  className="home-page__chip"
                  title={t("home:attention.chipTitle", { month: month.label })}
                  {...linkTo(month.path)}
                >
                  {month.label}
                  <span className="home-page__chip-count">{month.count}</span>
                </a>
              ))}
              {attention.moreMonths > 0 ? (
                <a
                  className="home-page__chip home-page__chip--more"
                  title={t("home:attention.moreMonthsTitle")}
                  {...linkTo(attention.listPath)}
                >
                  {t("home:attention.moreMonths", { count: attention.moreMonths })}
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="home-page__attention-actions">
          <BlueButton variant="primary" size="lg" onClick={home.startReviewing}>
            {t("home:attention.start")}
            <ArrowIcon />
          </BlueButton>
          {attention.oldest ? (
            <p className="home-page__attention-hint">{t("home:attention.oldestFrom", { code: attention.oldest.code })}</p>
          ) : null}
          <BlueLink {...linkTo(attention.listPath)}>{t("home:attention.seeList")}</BlueLink>
        </div>
      </div>
    </BlueCard>
  );
}

// ---------------------------------------------------------------------------
// BBM at a glance
// ---------------------------------------------------------------------------

function BbmOverview({ home }: { home: HomeController }) {
  const { reports, bbm } = home;
  const header = (
    <CardHeader title="BBM" subtitle={t("home:bbm.subtitle")}>
      <BlueLink {...linkTo(bbm.path)}>{t("home:bbm.open")}</BlueLink>
    </CardHeader>
  );

  if (reports.status !== "ready") {
    return (
      <BlueCard header={header}>
        <Placeholder lines={["100%", "55%", "100%", "100%", "100%"]} label={t("home:bbm.loading")} />
      </BlueCard>
    );
  }
  if (bbm.reports === 0) return null;

  return (
    <BlueCard className="home-page__bbm" header={header}>
      <dl className="home-page__figures">
        <div className="home-page__figure">
          <dt>{t("home:bbm.reports")}</dt>
          <dd>{bbm.reports}</dd>
        </div>
        <div className="home-page__figure">
          <dt>{t("home:bbm.submitted")}</dt>
          <dd>{formatMoney(bbm.amount)}</dd>
        </div>
        <div className="home-page__figure">
          <dt>{t("home:bbm.approved")}</dt>
          <dd title={t("home:bbm.approvedAmount", { amount: formatMoney(bbm.approvedAmount) })}>
            {bbm.approved}
            <span className="home-page__figure-of">{t("home:bbm.of", { total: bbm.reports })}</span>
          </dd>
        </div>
      </dl>

      <StatusBar counts={bbm.counts} className="home-page__bar" />
      <ul className="home-page__legend" aria-label={t("home:bbm.byStatus")}>
        {bbm.statuses.map((item) => (
          <li key={item.status}>
            <a className="home-page__legend-item" title={item.meaning} {...linkTo(item.path)}>
              <StatusDot status={item.status} />
              <span className="home-page__legend-label">{item.label}</span>
              <span className="home-page__legend-count">{item.count}</span>
            </a>
          </li>
        ))}
      </ul>

      <h3 className="home-page__section-title">{t("home:bbm.byMonth")}</h3>
      <ul className="home-page__months">
        {bbm.months.map((month) => (
          <li key={month.period}>
            <MonthRow month={month} />
          </li>
        ))}
      </ul>
      {bbm.moreMonths > 0 ? (
        <p className="home-page__more">
          {t("home:bbm.olderMonths", { count: bbm.moreMonths })}{" "}
          <BlueLink {...linkTo(bbm.path)}>{t("home:bbm.pickOnList")}</BlueLink>
        </p>
      ) : null}
    </BlueCard>
  );
}

function MonthRow({ month }: { month: MonthSummary }) {
  return (
    <a className="home-page__month" {...linkTo(month.path)}>
      <span className="home-page__month-name">
        <span className="home-page__month-label">{month.label}</span>
        {month.current ? <BlueBadge variant="info">{t("home:bbm.thisMonth")}</BlueBadge> : null}
      </span>
      <span className="home-page__month-meta">
        {t("reports", { count: month.reports })} · {formatMoney(month.amount)}
      </span>
      <StatusBar counts={month.counts} size="sm" className="home-page__month-bar" />
      <span className={`home-page__month-state home-page__month-state--${month.state.tone}`}>
        {month.state.tone === "clear" ? <CheckIcon /> : null}
        {month.state.text}
      </span>
      <ChevronIcon />
    </a>
  );
}

// ---------------------------------------------------------------------------
// Parts
// ---------------------------------------------------------------------------

function CardHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <header className="blue-card__header home-page__card-header">
      <div>
        <h2 className="home-page__card-title">{title}</h2>
        {subtitle ? <p className="home-page__card-subtitle">{subtitle}</p> : null}
      </div>
      {children}
    </header>
  );
}

/** Grey bars where content is loading, so the page does not jump when it arrives. */
function Placeholder({ lines, label }: { lines: string[]; label: string }) {
  return (
    <div className="home-page__placeholder" role="status" aria-label={label}>
      {lines.map((width, index) => (
        <span key={index} className="home-page__placeholder-line" style={{ width }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function CheckIcon() {
  return (
    <svg className="home-page__check" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="m3.5 8.5 3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg className="home-page__chevron" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

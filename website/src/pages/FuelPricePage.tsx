import { t } from "../app/i18n";
import { BlueAlert } from "../components/blue/Alert";
import { BlueBadge } from "../components/blue/Badge";
import { BlueButton } from "../components/blue/Button";
import { BlueCard } from "../components/blue/Card";
import { BlueEmptyState } from "../components/blue/EmptyState";
import { BlueInput } from "../components/blue/Input";
import { BlueLink } from "../components/blue/Link";
import { BlueModal } from "../components/blue/Modal";
import { BlueSelect } from "../components/blue/Select";
import { BlueSpinner } from "../components/blue/Spinner";
import { BlueTable } from "../components/blue/Table";
import { BlueTabs } from "../components/blue/Tabs";
import { BlueTag } from "../components/blue/Tag";
import type { BlueTableColumn } from "../components/blue/types";
import { PriceStepChart } from "../components/PriceStepChart";
import {
  useFuelPriceController,
  type ChangedView,
  type FuelPriceController,
  type HistoryEntry,
  type HistoryView,
  type PriceChange,
  type PriceRow,
  type SourceView,
} from "../controllers/FuelPriceController";
import type { User } from "../types/user";
import "../styles/pages/FuelPricePage.css";

interface FuelPricePageProps {
  user: User;
}

const TABLE_ID = "fuel-price-table";
const RECENT_ID = "fuel-price-recent";

export default function FuelPricePage({ user }: FuelPricePageProps) {
  const page = useFuelPriceController(user);

  return (
    <div className="fuel-price-page">
      <header className="fuel-price-page__header">
        <div>
          <h1 className="page-title">{t("fuelPrice:title")}</h1>
          <p className="page-subtitle">{t("fuelPrice:subtitle")}</p>
        </div>
        <RefreshStatus page={page} />
      </header>

      {page.prices.status === "error" ? (
        <div className="fuel-price-page__error">
          <BlueAlert variant="error" title={t("fuelPrice:loadError")}>
            {page.prices.message}
          </BlueAlert>
          <BlueButton variant="secondary" onClick={page.reload}>
            {t("actions.tryAgain")}
          </BlueButton>
        </div>
      ) : (
        <>
          <RecentChanges page={page} />
          <PriceList page={page} />
        </>
      )}

      <RefreshDetails page={page} />
      <ConfirmRefresh page={page} />
      <PriceHistory page={page} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// The refresh from the web: the button, and one line on the last one (its details in a dialog)
// ---------------------------------------------------------------------------

function RefreshStatus({ page }: { page: FuelPriceController }) {
  const { prices, run, refresh, details } = page;
  if (prices.status === "error") return null;

  return (
    <div className="fuel-price-page__refresh">
      <BlueButton
        variant="secondary"
        size="sm"
        loading={refresh.queuing}
        disabled={refresh.disabled || prices.status !== "ready"}
        onClick={refresh.ask}
      >
        {refresh.queuing ? null : <RefreshIcon />}
        {refresh.active ? t("fuelPrice:update.busy") : t("fuelPrice:update.button")}
      </BlueButton>
      {prices.status === "loading" ? (
        <Placeholder lines={["180px"]} label={t("fuelPrice:loading")} />
      ) : (
        <div className={`fuel-price-page__run fuel-price-page__run--${run?.status ?? "never"}`} aria-live="polite">
          <RunIcon status={run?.status ?? null} />
          <span>{run?.summary ?? t("fuelPrice:run.never")}</span>
          <BlueButton variant="ghost" size="sm" className="fuel-price-page__details-button" onClick={details.show}>
            {t("fuelPrice:update.details")}
          </BlueButton>
        </div>
      )}
      {refresh.reason ? <p className="fuel-price-page__cooldown">{refresh.reason}</p> : null}
    </div>
  );
}

function RefreshDetails({ page }: { page: FuelPriceController }) {
  const { run, refresh, details } = page;
  return (
    <BlueModal
      open={details.open}
      onClose={details.close}
      title={t("fuelPrice:details.title")}
      footer={
        <>
          {refresh.reason ? <span className="fuel-run__cooldown">{refresh.reason}</span> : null}
          <BlueButton variant="secondary" onClick={details.close} data-autofocus>
            {t("actions.close")}
          </BlueButton>
          <BlueButton
            variant="primary"
            loading={refresh.queuing}
            disabled={refresh.disabled || page.prices.status !== "ready"}
            onClick={refresh.ask}
          >
            {refresh.active ? t("fuelPrice:update.busy") : t("fuelPrice:update.button")}
          </BlueButton>
        </>
      }
    >
      <div className="fuel-run">
        {run ? (
          <>
            <section className={`fuel-run__outcome fuel-run__outcome--${run.outcome.tone}`} aria-live="polite">
              <RunIcon status={run.status} />
              <div className="fuel-run__outcome-body">
                <h3 className="fuel-run__outcome-title">{run.outcome.title}</h3>
                <p className="fuel-run__outcome-text">{run.outcome.text}</p>
                <p className="fuel-run__facts">{run.facts}</p>
              </div>
            </section>
            {run.changed.length > 0 ? (
              <section className="fuel-run__section" aria-labelledby="fuel-run-changed">
                <h3 id="fuel-run-changed" className="fuel-run__heading">
                  {t("fuelPrice:details.changedTitle")}
                  <span className="fuel-run__count">{run.changed.length}</span>
                </h3>
                <ul className="fuel-run__changed">
                  {run.changed.map((price) => (
                    <ChangedPrice key={price.key} price={price} />
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        ) : (
          <section className="fuel-run__outcome fuel-run__outcome--info">
            <div className="fuel-run__outcome-body">
              <h3 className="fuel-run__outcome-title">{t("fuelPrice:details.never")}</h3>
              <p className="fuel-run__outcome-text">{t("fuelPrice:details.neverText")}</p>
            </div>
          </section>
        )}
        <details className="fuel-run__how">
          <summary>{t("fuelPrice:details.how")}</summary>
          <ol>
            <li>{t("fuelPrice:details.howSearch")}</li>
            <li>{t("fuelPrice:details.howRead")}</li>
            <li>{t("fuelPrice:details.howQuote")}</li>
            <li>{t("fuelPrice:details.howNew")}</li>
            <li>{t("fuelPrice:details.howWhen")}</li>
          </ol>
        </details>
      </div>
    </BlueModal>
  );
}

/** Confirms "Update from the web": Claude reads the web, and the next refresh (from the button or a new batch of
 *  reports) can only start a day later. */
function ConfirmRefresh({ page }: { page: FuelPriceController }) {
  const { refresh } = page;
  const { confirm } = refresh;
  return (
    <BlueModal
      open={confirm.open}
      onClose={confirm.close}
      dismissible={!refresh.queuing}
      size="sm"
      title={t("fuelPrice:confirm.title")}
      footer={
        <>
          <BlueButton variant="secondary" data-autofocus disabled={refresh.queuing} onClick={confirm.close}>
            {t("actions.cancel")}
          </BlueButton>
          <BlueButton loading={refresh.queuing} onClick={confirm.start}>
            {t("fuelPrice:update.button")}
          </BlueButton>
        </>
      }
    >
      <p className="fuel-price-page__dialog-text">{t("fuelPrice:confirm.text")}</p>
      <p className="fuel-price-page__dialog-text">{t("fuelPrice:confirm.onceADay", { time: confirm.nextAt })}</p>
      {confirm.error ? (
        <BlueAlert variant="error" title={t("fuelPrice:toast.failed")}>
          {confirm.error}
        </BlueAlert>
      ) : null}
    </BlueModal>
  );
}

/** A price the refresh stored: the price before it next to the new one, the change, and where it came from. */
function ChangedPrice({ price }: { price: ChangedView }) {
  return (
    <li className="fuel-run__price">
      <p className="fuel-run__price-name">
        {price.product}
        <span className="fuel-run__price-merchant">{price.merchant}</span>
        {price.upcoming ? <BlueBadge variant="info">{t("fuelPrice:recent.announced")}</BlueBadge> : null}
      </p>
      <div className="fuel-run__compare">
        <div className="fuel-run__value">
          <span className="fuel-run__value-label">{t("fuelPrice:details.before")}</span>
          {price.before ? (
            <>
              <strong className="fuel-run__value-price">{price.before.price}</strong>
              <span className="fuel-run__value-note">{t("fuelPrice:details.since", { date: price.before.since })}</span>
            </>
          ) : (
            <span className="fuel-run__value-price fuel-price-page__muted">{t("fuelPrice:price.none")}</span>
          )}
        </div>
        <div className="fuel-run__value fuel-run__value--new">
          <span className="fuel-run__value-label">{t("fuelPrice:details.after")}</span>
          <strong className="fuel-run__value-price">{price.after.price}</strong>
          <span className="fuel-run__value-note">{t("fuelPrice:details.from", { date: price.after.from })}</span>
        </div>
      </div>
      {price.change ? <ChangeChip change={price.change} /> : null}
      <span className="fuel-price-page__stack">
        <SourceLine source={price.source} />
        {price.source.quote ? <q className="fuel-run__quote">{price.source.quote}</q> : null}
      </span>
    </li>
  );
}

function RecentChanges({ page }: { page: FuelPriceController }) {
  const { prices, recent, moreRecent, recentDays } = page;

  return (
    <section className="fuel-price-page__recent" aria-labelledby="fuel-price-recent-title">
      <div className="fuel-price-page__section-head">
        <h2 id="fuel-price-recent-title" className="fuel-price-page__section-title">
          {t("fuelPrice:recent.title")}
        </h2>
        <p className="fuel-price-page__section-subtitle">{t("fuelPrice:recent.subtitle", { days: recentDays })}</p>
      </div>

      {prices.status === "loading" ? (
        <div className="fuel-price-page__changes">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="fuel-price-page__change fuel-price-page__change--placeholder">
              <Placeholder lines={["60%", "40%", "80%"]} label={t("fuelPrice:loading")} />
            </div>
          ))}
        </div>
      ) : recent.length === 0 ? (
        <p className="fuel-price-page__no-changes">{t("fuelPrice:recent.none", { days: recentDays })}</p>
      ) : (
        <>
          <ul id={RECENT_ID} className="fuel-price-page__changes">
            {recent.map((change) => (
              <li key={change.key}>
                <button
                  type="button"
                  className={`fuel-price-page__change ${change.upcoming ? "fuel-price-page__change--upcoming" : ""}`.trim()}
                  aria-label={`${t("fuelPrice:recent.open", { name: change.name })}: ${change.from} → ${change.to}, ${change.change.label}, ${change.when}`}
                  onClick={() => page.openHistory(change.productId)}
                >
                  <span className="fuel-price-page__change-head">
                    <span className="fuel-price-page__change-name">{change.name}</span>
                    {change.upcoming ? <BlueBadge variant="info">{t("fuelPrice:recent.announced")}</BlueBadge> : null}
                  </span>
                  <span className="fuel-price-page__change-meta">{change.meta}</span>
                  <span className="fuel-price-page__change-prices">
                    <span className="fuel-price-page__change-from">{change.from}</span>
                    <ArrowRightIcon />
                    <span className="fuel-price-page__change-to">{change.to}</span>
                  </span>
                  <span className="fuel-price-page__change-foot">
                    <ChangeChip change={change.change} />
                    <span>{change.when}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {moreRecent > 0 ? (
            <p className="fuel-price-page__more">
              <span>{t("fuelPrice:recent.more", { count: moreRecent })}</span>
              <BlueButton variant="ghost" size="sm" onClick={page.showAllRecent} aria-controls={RECENT_ID}>
                {t("fuelPrice:recent.showAll")}
              </BlueButton>
            </p>
          ) : page.allRecentShown ? (
            <p className="fuel-price-page__more">
              <BlueButton variant="ghost" size="sm" onClick={page.showFewerRecent} aria-controls={RECENT_ID}>
                {t("fuelPrice:recent.showFewer")}
              </BlueButton>
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Every fuel: merchant tabs, a search and the fuel kind on top; sortable headers; a row opens its history
// ---------------------------------------------------------------------------

function PriceList({ page }: { page: FuelPriceController }) {
  const { prices } = page;

  return (
    <BlueCard
      className="fuel-price-page__card"
      header={
        <div className="fuel-price-page__filters">
          <BlueTabs
            items={page.merchantTabs}
            activeKey={page.merchant}
            onChange={page.setMerchant}
            ariaLabel={t("fuelPrice:filter.merchants")}
            controls={TABLE_ID}
            className="fuel-price-page__tabs"
          />
          <div className="fuel-price-page__toolbar">
            <div className="fuel-price-page__search">
              <SearchIcon />
              <BlueInput
                type="search"
                placeholder={t("fuelPrice:filter.search")}
                aria-label={t("fuelPrice:filter.search")}
                aria-controls={TABLE_ID}
                value={page.search}
                onChange={(event) => page.setSearch(event.target.value)}
              />
            </div>
            <BlueSelect
              className="fuel-price-page__kind"
              aria-label={t("fuelPrice:filter.kind")}
              aria-controls={TABLE_ID}
              options={page.kindOptions}
              value={page.kind}
              onChange={(event) => page.setKind(event.target.value)}
            />
            <p className="fuel-price-page__count" aria-live="polite">
              {prices.status === "ready" ? page.countText : null}
            </p>
          </div>
        </div>
      }
    >
      {prices.status === "loading" ? (
        <Placeholder lines={["100%", "100%", "100%", "100%", "100%"]} label={t("fuelPrice:loading")} />
      ) : (
        <div id={TABLE_ID}>
          <BlueTable
            stackOnMobile
            columns={priceColumns(page)}
            data={page.rows}
            rowKey={(row) => row.id}
            caption={t("fuelPrice:table.caption")}
            sort={page.sort}
            onSortChange={page.setSort}
            onRowClick={(row) => page.openHistory(row.id)}
            rowClassName={(row) => (row.fresh ? "fuel-price-page__row--fresh" : undefined)}
            empty={
              page.noProducts ? (
                <BlueEmptyState title={t("fuelPrice:empty.title")}>
                  {page.refresh.active ? t("fuelPrice:empty.running") : t("fuelPrice:empty.text")}
                </BlueEmptyState>
              ) : (
                <BlueEmptyState
                  title={t("fuelPrice:filter.noMatch")}
                  action={
                    page.filtered ? (
                      <BlueButton variant="secondary" size="sm" onClick={page.clearFilters}>
                        {t("fuelPrice:filter.clear")}
                      </BlueButton>
                    ) : undefined
                  }
                >
                  {t("fuelPrice:filter.noMatchText")}
                </BlueEmptyState>
              )
            }
          />
        </div>
      )}
    </BlueCard>
  );
}

function priceColumns(page: FuelPriceController): BlueTableColumn<PriceRow>[] {
  return [
    {
      key: "product",
      header: t("fuelPrice:table.product"),
      sortable: true,
      render: (row) => (
        <span className="fuel-price-page__stack">
          <span className="fuel-price-page__product">
            <span className="fuel-price-page__product-name">{row.name}</span>
            {row.fresh ? <BlueBadge variant="info">{row.fresh}</BlueBadge> : null}
          </span>
          <span className="fuel-price-page__muted">{row.kind}</span>
        </span>
      ),
    },
    {
      key: "merchant",
      header: t("fuelPrice:table.merchant"),
      sortable: true,
      nowrap: true,
      render: (row) => row.merchant,
    },
    {
      key: "price",
      header: t("fuelPrice:table.price"),
      sortable: true,
      align: "right",
      cellTitle: (row) => row.price.title,
      render: (row) => (
        <span className="fuel-price-page__stack fuel-price-page__stack--right">
          <span className={row.price.missing ? "fuel-price-page__muted" : "fuel-price-page__price"}>
            {row.price.text}
          </span>
          {row.since ? (
            <span className="fuel-price-page__muted">{t("fuelPrice:table.since", { date: row.since })}</span>
          ) : null}
          {row.upcoming ? (
            <span className="fuel-price-page__upcoming" title={row.upcoming.change?.label}>
              {t("fuelPrice:table.upcoming", { price: row.upcoming.text, date: row.upcoming.from })}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: "source",
      header: t("fuelPrice:table.source"),
      render: (row) => (row.source ? <SourceLine source={row.source} /> : <span className="fuel-price-page__muted">–</span>),
    },
    {
      key: "history",
      header: <span className="blue-visually-hidden">{t("fuelPrice:table.history")}</span>,
      label: t("fuelPrice:table.history"),
      align: "right",
      nowrap: true,
      render: (row) => (
        <BlueButton
          variant="ghost"
          size="sm"
          className="fuel-price-page__history-button"
          aria-label={t("fuelPrice:table.historyOf", { name: `${row.merchant} ${row.name}` })}
          onClick={() => page.openHistory(row.id)}
        >
          <ChartIcon />
          {t("fuelPrice:table.history")}
        </BlueButton>
      ),
    },
  ];
}

// ---------------------------------------------------------------------------
// One product's history: today's price, a step chart, and every price with its source
// ---------------------------------------------------------------------------

function PriceHistory({ page }: { page: FuelPriceController }) {
  const { history } = page;
  return (
    <BlueModal
      open={history !== null}
      onClose={page.closeHistory}
      size="lg"
      title={history ? t("fuelPrice:table.historyOf", { name: history.name }) : ""}
      className="fuel-history-modal"
    >
      {history ? <HistoryBody history={history} /> : null}
    </BlueModal>
  );
}

function HistoryBody({ history }: { history: HistoryView }) {
  const { row } = history;
  return (
    <div className="fuel-history">
      <div className="fuel-history__summary">
        <div className="fuel-history__now">
          <span className="fuel-history__label">{t("fuelPrice:history.now")}</span>
          <span className={row.price.missing ? "fuel-history__price fuel-price-page__muted" : "fuel-history__price"}>
            {row.price.text}
          </span>
          <span className="fuel-price-page__muted">
            {history.meta}
            {row.since ? ` · ${t("fuelPrice:history.since", { date: row.since })}` : ""}
          </span>
        </div>
        {row.change && row.previous ? (
          <div className="fuel-history__was">
            <ChangeChip change={row.change} />
            <span className="fuel-price-page__muted">
              {row.previous.text} {t("fuelPrice:table.until", { date: row.previous.until })}
            </span>
          </div>
        ) : null}
        {row.upcoming ? (
          <div className="fuel-history__next">
            <BlueBadge variant="info">{t("fuelPrice:recent.announced")}</BlueBadge>
            <span>{t("fuelPrice:table.upcoming", { price: row.upcoming.text, date: row.upcoming.from })}</span>
            {row.upcoming.change ? <ChangeChip change={row.upcoming.change} /> : null}
          </div>
        ) : null}
      </div>

      {history.steps && history.today !== null ? (
        <PriceStepChart
          className="fuel-history__chart"
          steps={history.steps}
          today={history.today}
          todayLabel={t("fuelPrice:history.today")}
          label={t("fuelPrice:history.chart", { name: `${row.merchant} ${history.name}` })}
        />
      ) : (
        <p className="fuel-history__single">{t("fuelPrice:history.single")}</p>
      )}

      <h3 className="fuel-history__heading">{t("fuelPrice:history.prices")}</h3>
      <BlueTable
        dense
        stackOnMobile
        columns={historyColumns()}
        data={history.entries}
        rowKey={(entry) => entry.id}
        caption={t("fuelPrice:table.historyOf", { name: history.name })}
        rowClassName={(entry) => `fuel-history__row--${entry.state}`}
      />
    </div>
  );
}

function historyColumns(): BlueTableColumn<HistoryEntry>[] {
  return [
    {
      key: "period",
      header: t("fuelPrice:history.period"),
      render: (entry) => (
        <span className="fuel-history__period">
          <span>{entry.period}</span>
          {entry.state === "current" ? <BlueTag variant="success">{t("fuelPrice:history.current")}</BlueTag> : null}
          {entry.state === "upcoming" ? <BlueTag variant="info">{t("fuelPrice:history.upcoming")}</BlueTag> : null}
        </span>
      ),
    },
    {
      key: "price",
      header: t("fuelPrice:history.price"),
      align: "right",
      nowrap: true,
      cellTitle: (entry) => entry.price.title,
      render: (entry) => (
        <span className={entry.price.missing ? "fuel-price-page__muted" : "fuel-price-page__price"}>{entry.price.text}</span>
      ),
    },
    {
      key: "change",
      header: t("fuelPrice:history.change"),
      nowrap: true,
      render: (entry) =>
        entry.change ? <ChangeChip change={entry.change} /> : <span className="fuel-price-page__muted">–</span>,
    },
    {
      key: "source",
      header: t("fuelPrice:history.source"),
      render: (entry) => (
        <span className="fuel-price-page__stack">
          <SourceLine source={entry.source} />
          {entry.source.quote ? (
            <q className="fuel-history__quote" title={entry.source.quote}>
              {entry.source.quote}
            </q>
          ) : null}
          <span className="fuel-price-page__muted">{entry.source.fetched}</span>
        </span>
      ),
    },
  ];
}

// ---------------------------------------------------------------------------
// Parts
// ---------------------------------------------------------------------------

/** "▲ Rp 250 · 1,6%": up in red (it costs more), down in green; the arrow and the words say it without the colour. */
function ChangeChip({ change }: { change: PriceChange }) {
  return (
    <span className={`fuel-change fuel-change--${change.direction}`} title={change.label}>
      {change.direction === "same" ? (
        <span>{change.label}</span>
      ) : (
        <>
          <ChangeArrow direction={change.direction} />
          <span className="blue-visually-hidden">{change.label}</span>
          <span aria-hidden="true">
            {change.amount}
            <span className="fuel-change__percent"> · {change.percent}</span>
          </span>
        </>
      )}
    </span>
  );
}

function SourceLine({ source }: { source: SourceView }) {
  return (
    <span className="fuel-price-page__source" title={source.fetched}>
      <BlueBadge variant={source.kind === "official" ? "info" : "default"}>{source.label}</BlueBadge>
      {source.link ? (
        <BlueLink href={source.link.url} external title={source.link.url}>
          {source.link.host}
        </BlueLink>
      ) : null}
    </span>
  );
}

function RunIcon({ status }: { status: string | null }) {
  if (status === "queued" || status === "running") return <BlueSpinner size="sm" className="fuel-price-page__run-icon" />;
  if (status === "done") {
    return (
      <svg className="fuel-price-page__run-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
        <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="m5.25 8.25 1.9 1.9 3.6-3.9" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg className="fuel-price-page__run-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
        <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 4.75v3.75" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11" r="0.9" fill="currentColor" />
      </svg>
    );
  }
  return null;
}

function ChangeArrow({ direction }: { direction: "up" | "down" }) {
  return (
    <svg className="fuel-change__arrow" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
      <path d={direction === "up" ? "M6 2.5 10 8.5H2z" : "M6 9.5 2 3.5h8z"} fill="currentColor" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg className="fuel-price-page__search-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <circle cx="7" cy="7" r="4.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="m10.5 10.5 3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg className="fuel-price-page__button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M13 8a5 5 0 1 1-1.46-3.54" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M13 2.75v2.5h-2.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg className="fuel-price-page__button-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M2.5 12.5h3v-3h3v-4h3v-2h2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2.5 14h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg className="fuel-price-page__change-arrow" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Grey bars where content is loading, so the page does not jump when it arrives. */
function Placeholder({ lines, label }: { lines: string[]; label: string }) {
  return (
    <div className="fuel-price-page__placeholder" role="status" aria-label={label}>
      {lines.map((width, index) => (
        <span key={index} className="fuel-price-page__placeholder-line" style={{ width }} />
      ))}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { t } from "../app/i18n";
import { navigate, useLocation, withParams } from "../app/router";
import { useBlueToast } from "../components/blue/useBlueToast";
import type { PriceStep } from "../components/PriceStepChart";
import type {
  FuelKind,
  FuelMerchant,
  FuelPrice,
  FuelPriceList,
  FuelPriceRun,
  FuelPriceSource,
  FuelProduct,
} from "../types/fuelPrice";
import type { User } from "../types/user";
import { EMPTY, formatDateTime, formatMoney } from "../utils/format";
import { errorMessage, jsonBody, request, useApi } from "./api";

// Logic for the fuel price page (pages/FuelPricePage.tsx): the price per liter in DKI Jakarta of every fuel the
// merchants sell, how it changed (the price before, the change, a price announced for a later day, the whole history
// of a product), filtered by merchant, fuel kind and a search, and sorted by a column; the filter and sort live in
// the URL. "Update from the web" queues a refresh: the OCR worker has Claude find recent articles about the prices
// and read them, and stores the prices that pass the checks. A new batch of reports queues one too (once a day).

export const FUEL_PRICES_PATH = "/fuel-prices";

/** The merchants in the order the page shows them, with their names as they write them. */
const MERCHANTS: { key: FuelMerchant; name: string }[] = [
  { key: "pertamina", name: "Pertamina" },
  { key: "shell", name: "Shell" },
  { key: "bp", name: "BP" },
  { key: "vivo", name: "Vivo" },
];

/** Price changes of the last RECENT_DAYS days (and the ones announced) are listed on top of the page. */
const RECENT_DAYS = 30;
/** At most this many of them; the rest are in the table (sorted by change). */
const RECENT_SHOWN = 8;
/** A price that changed in the last NEW_DAYS days is marked "New" in the table. */
const NEW_DAYS = 7;
/** A refresh, from the button or a new batch of reports, waits this long after the last one (the backend's
 *  REFRESH_COOLDOWN in fuel_price_service.py). */
const REFRESH_COOLDOWN_MS = 24 * 60 * 60 * 1000;

/** While a refresh is queued or running, the page asks for the prices again this often. */
const POLL_MS = 15_000;

function getFuelPrices(signal: AbortSignal): Promise<FuelPriceList> {
  return request<FuelPriceList>("/fuel-prices", { signal });
}

/** Queues a refresh; the backend answers with it (409 while one is queued or running, 429 too soon after the last). */
async function queueRefresh(userEmail: string): Promise<FuelPriceRun> {
  const body = await request<{ run: FuelPriceRun }>("/fuel-prices/refresh", jsonBody("POST", { user_email: userEmail }));
  return body.run;
}

export function merchantName(merchant: string | null): string {
  return MERCHANTS.find((item) => item.key === merchant)?.name ?? merchant ?? EMPTY;
}

// ---------------------------------------------------------------------------
// Days: the backend writes them DD-MM-YYYY (WIB); here they are counted as day numbers (days since 01-01-1970)
// ---------------------------------------------------------------------------

const DAY_MS = 86_400_000;

/** "02-09-2026" -> its day number, or null when it is not a date. */
function dayNumber(value: string): number | null {
  const match = /^(\d{2})-(\d{2})-(\d{4})$/.exec(value);
  if (!match) return null;
  const [day, month, year] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const time = Date.UTC(year, month - 1, day);
  const date = new Date(time);
  return date.getUTCDate() === day && date.getUTCMonth() === month - 1 ? time / DAY_MS : null;
}

/** A day number -> "02-09-2026". */
function dayText(day: number): string {
  const date = new Date(day * DAY_MS);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(date.getUTCDate())}-${pad(date.getUTCMonth() + 1)}-${date.getUTCFullYear()}`;
}

// ---------------------------------------------------------------------------
// Prices and changes
// ---------------------------------------------------------------------------

const changePercent = new Intl.NumberFormat("id-ID", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export interface PriceText {
  /** "Rp 15.950", or why there is no price. */
  text: string;
  /** No price: not listed, or none yet. */
  missing: boolean;
  title: string | undefined;
}

function priceText(price: FuelPrice | null): PriceText {
  if (!price) return { text: t("fuelPrice:price.none"), missing: true, title: undefined };
  if (price.price_per_liter === null) {
    return { text: t("fuelPrice:price.notListed"), missing: true, title: t("fuelPrice:price.notListedTitle") };
  }
  return { text: formatMoney(price.price_per_liter), missing: false, title: undefined };
}

export interface PriceChange {
  direction: "up" | "down" | "same";
  /** "Rp 250" (without a sign: direction says which way) */
  amount: string;
  /** "1,6%" */
  percent: string;
  /** "Up Rp 250 (1,6%)", for screen readers and tooltips. */
  label: string;
}

function changeOf(from: FuelPrice | null, to: FuelPrice | null): PriceChange | null {
  const before = from?.price_per_liter;
  const after = to?.price_per_liter;
  if (before == null || after == null || before === 0) return null;
  const difference = after - before;
  const direction = difference > 0 ? "up" : difference < 0 ? "down" : "same";
  const amount = formatMoney(Math.abs(difference));
  const percent = changePercent.format(Math.abs(difference) / before);
  return {
    direction,
    amount,
    percent,
    label: t(`fuelPrice:change.${direction}`, { amount, percent }),
  };
}

function kindOf(product: FuelProduct): string {
  if (product.fuel_kind === "diesel") return t("fuelPrice:kind.diesel");
  return product.ron ? t("fuelPrice:kind.ron", { ron: product.ron }) : t("fuelPrice:kind.gasoline");
}

/** A link to a source page: only http(s) addresses are links (the address comes from the web, through Claude). */
export interface SourceLink {
  url: string;
  /** "mypertamina.id" */
  host: string;
}

function sourceLink(url: string | null): SourceLink | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
    return { url: parsed.href, host: parsed.hostname.replace(/^www\./, "") };
  } catch {
    return null;
  }
}

export interface SourceView {
  kind: FuelPriceSource;
  label: string;
  link: SourceLink | null;
  /** The sentence on the page that gives the price. */
  quote: string | null;
  /** "Fetched 23-10-2026 17:00" */
  fetched: string;
}

function sourceView(price: FuelPrice): SourceView {
  return {
    kind: price.source,
    label: t(`fuelPrice:source.${price.source}`),
    link: sourceLink(price.source_url),
    quote: price.source_text?.trim() || null,
    fetched: t("fuelPrice:source.fetched", { time: formatDateTime(price.fetched_at) }),
  };
}

// ---------------------------------------------------------------------------
// The table: one row per product
// ---------------------------------------------------------------------------

export interface PriceRow {
  id: number;
  name: string;
  merchant: string;
  /** "RON 92", "Diesel" */
  kind: string;
  price: PriceText;
  /** The day today's price applies from, "01-10-2026"; null without a price. */
  since: string | null;
  /** "Today" or "New": the price changed today, or in the last NEW_DAYS days. */
  fresh: string | null;
  /** The price before today's: until the day before today's started. */
  previous: (PriceText & { until: string }) | null;
  change: PriceChange | null;
  /** A price announced for a later day. */
  upcoming: { text: string; from: string; change: PriceChange | null } | null;
  source: SourceView | null;
  /** For filtering and sorting. */
  product: FuelProduct;
  order: number;
}

function rowOf(product: FuelProduct, order: number, today: number | null): PriceRow {
  const sinceDay = product.price ? dayNumber(product.price.valid_from) : null;
  const age = sinceDay !== null && today !== null ? today - sinceDay : null;
  const changed = product.previous !== null;
  return {
    id: product.id,
    name: product.name,
    merchant: merchantName(product.merchant),
    kind: kindOf(product),
    price: priceText(product.price),
    since: product.price?.valid_from ?? null,
    fresh:
      changed && age === 0
        ? t("fuelPrice:fresh.today")
        : changed && age !== null && age > 0 && age < NEW_DAYS
          ? t("fuelPrice:fresh.new")
          : null,
    previous:
      product.previous && sinceDay !== null
        ? { ...priceText(product.previous), until: dayText(sinceDay - 1) }
        : null,
    change: changeOf(product.previous, product.price),
    upcoming: product.upcoming
      ? {
          text: priceText(product.upcoming).text,
          from: product.upcoming.valid_from,
          change: changeOf(product.price, product.upcoming),
        }
      : null,
    source: product.price ? sourceView(product.price) : null,
    product,
    order,
  };
}

// ---------------------------------------------------------------------------
// Filter and sort (in the URL: ?merchant=shell&kind=diesel&q=power&sort=-price)
// ---------------------------------------------------------------------------

export type MerchantFilter = "all" | FuelMerchant;
export type KindFilter = "all" | FuelKind;

const SORT_KEYS = ["product", "merchant", "price"] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export type SortDirection = "asc" | "desc";
export interface PriceSort {
  key: SortKey;
  direction: SortDirection;
}

function toMerchant(value: string | null): MerchantFilter {
  return MERCHANTS.find((merchant) => merchant.key === value)?.key ?? "all";
}

function toKind(value: string | null): KindFilter {
  return value === "gasoline" || value === "diesel" ? value : "all";
}

/** "price" -> price ascending, "-price" -> descending; anything else -> null: the merchants' own order. */
function toSort(value: string | null): PriceSort | null {
  const key = SORT_KEYS.find((item) => item === value?.replace(/^-/, ""));
  return key ? { key, direction: value?.startsWith("-") ? "desc" : "asc" } : null;
}

function sortParam(sort: PriceSort | null): string | null {
  return sort ? `${sort.direction === "desc" ? "-" : ""}${sort.key}` : null;
}

/** Every word of the search is in the product's name, merchant or kind ("shell 95", "dex", "ron 92"). */
function matchesSearch(row: PriceRow, search: string): boolean {
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  const text = `${row.name} ${row.merchant} ${row.kind} ${t(`fuelPrice:kind.${row.product.fuel_kind}`)}`.toLowerCase();
  return words.every((word) => text.includes(word));
}

const names = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function sortValue(row: PriceRow, key: SortKey): string | number | null {
  switch (key) {
    case "product":
      return row.name;
    case "merchant":
      return row.merchant;
    case "price":
      return row.product.price?.price_per_liter ?? null;
  }
}

/** Compares two rows by the sort; an empty value (no price) is always last; ties keep the merchants' order. */
function compareRows(a: PriceRow, b: PriceRow, sort: PriceSort): number {
  const x = sortValue(a, sort.key);
  const y = sortValue(b, sort.key);
  if (x === null || y === null) return x === y ? a.order - b.order : x === null ? 1 : -1;
  const compared = typeof x === "string" || typeof y === "string" ? names.compare(String(x), String(y)) : x - y;
  return compared !== 0 ? (sort.direction === "asc" ? compared : -compared) : a.order - b.order;
}

// ---------------------------------------------------------------------------
// Recent changes (the strip on top)
// ---------------------------------------------------------------------------

export interface RecentChange {
  key: string;
  productId: number;
  name: string;
  /** "Pertamina · RON 92" */
  meta: string;
  from: string;
  to: string;
  change: PriceChange;
  /** "Since 01-10-2026", "Today", "From 01-11-2026" */
  when: string;
  /** Announced for a later day. */
  upcoming: boolean;
}

function recentChanges(rows: PriceRow[], today: number | null): RecentChange[] {
  if (today === null) return [];
  const upcoming: (RecentChange & { day: number })[] = [];
  const recent: (RecentChange & { day: number })[] = [];
  for (const row of rows) {
    const { product } = row;
    const meta = `${row.merchant} · ${row.kind}`;
    const nextDay = product.upcoming ? dayNumber(product.upcoming.valid_from) : null;
    if (product.upcoming && row.upcoming?.change && row.upcoming.change.direction !== "same" && nextDay !== null) {
      upcoming.push({
        key: `upcoming-${product.id}`,
        productId: product.id,
        name: row.name,
        meta,
        from: row.price.text,
        to: row.upcoming.text,
        change: row.upcoming.change,
        when: t("fuelPrice:recent.from", { date: product.upcoming.valid_from }),
        upcoming: true,
        day: nextDay,
      });
    }
    const sinceDay = product.price ? dayNumber(product.price.valid_from) : null;
    if (row.change && row.change.direction !== "same" && row.previous && sinceDay !== null && today - sinceDay < RECENT_DAYS) {
      recent.push({
        key: `recent-${product.id}`,
        productId: product.id,
        name: row.name,
        meta,
        from: row.previous.text,
        to: row.price.text,
        change: row.change,
        when: sinceDay === today ? t("fuelPrice:recent.today") : t("fuelPrice:recent.since", { date: row.since }),
        upcoming: false,
        day: sinceDay,
      });
    }
  }
  upcoming.sort((a, b) => a.day - b.day);
  recent.sort((a, b) => b.day - a.day);
  return [...upcoming, ...recent];
}

// ---------------------------------------------------------------------------
// One product's history (the dialog)
// ---------------------------------------------------------------------------

export interface HistoryEntry {
  id: number;
  /** "02-09-2026 – 30-09-2026", "Since 01-10-2026", "From 01-11-2026" */
  period: string;
  state: "upcoming" | "current" | "past";
  price: PriceText;
  /** Against the price before it. */
  change: PriceChange | null;
  source: SourceView;
}

export interface HistoryView {
  productId: number;
  name: string;
  /** "Pertamina · RON 92" */
  meta: string;
  row: PriceRow;
  /** Newest first. */
  entries: HistoryEntry[];
  /** The steps of the chart, oldest first; null when there are less than two prices to draw. */
  steps: PriceStep[] | null;
  today: number | null;
}

function historyOf(row: PriceRow, today: number | null): HistoryView {
  const { product } = row;
  const newestFirst = product.history;
  const entries = newestFirst.map((price, index): HistoryEntry => {
    const newer = index > 0 ? newestFirst[index - 1] : null;
    const newerDay = newer ? dayNumber(newer.valid_from) : null;
    const day = dayNumber(price.valid_from);
    const state =
      price.id === product.price?.id ? "current" : day !== null && today !== null && day > today ? "upcoming" : "past";
    return {
      id: price.id,
      period:
        state === "upcoming"
          ? t("fuelPrice:history.from", { date: price.valid_from })
          : state === "current" || newerDay === null
            ? t("fuelPrice:history.since", { date: price.valid_from })
            : t("fuelPrice:history.range", { from: price.valid_from, to: dayText(newerDay - 1) }),
      state,
      price: priceText(price),
      change: changeOf(newestFirst[index + 1] ?? null, price),
      source: sourceView(price),
    };
  });
  return {
    productId: product.id,
    name: row.name,
    meta: `${row.merchant} · ${row.kind}`,
    row,
    entries,
    steps: stepsOf(product, entries, today),
    today,
  };
}

/** The history as chart steps, oldest first: each price from its day to the next one's. The last one runs a little
 * past today (or past the day an announced price starts). */
function stepsOf(product: FuelProduct, entries: HistoryEntry[], today: number | null): PriceStep[] | null {
  const oldestFirst = [...product.history].reverse();
  const days = oldestFirst.map((price) => dayNumber(price.valid_from));
  if (today === null || days.some((day) => day === null)) return null;
  if (oldestFirst.filter((price) => price.price_per_liter !== null).length < 2) return null;
  const first = days[0] as number;
  const last = Math.max(today, days[days.length - 1] as number);
  const end = last + Math.max(7, Math.round((last - first) * 0.06));
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  return oldestFirst.map((price, index) => {
    const entry = byId.get(price.id);
    return {
      key: price.id,
      from: days[index] as number,
      to: index + 1 < days.length ? (days[index + 1] as number) : end,
      price: price.price_per_liter,
      upcoming: entry?.state === "upcoming",
      valueText: priceText(price).text,
      rangeText: entry?.period ?? price.valid_from,
    };
  });
}

// ---------------------------------------------------------------------------
// The refresh from the web
// ---------------------------------------------------------------------------

/** Why a refresh failed (the worker's and the repository's codes); another code is shown as it is. */
const RUN_ERRORS = [
  "claude_unavailable",
  "timeout",
  "no_answer",
  "over_budget",
  "no_articles",
  "worker_error",
  "not_started",
  "stale",
] as const;

function isOneOf<T extends string>(list: readonly T[], value: string | null): value is T {
  return value !== null && (list as readonly string[]).includes(value);
}

function runError(error: string | null): string {
  if (error === null) return t("fuelPrice:run.noError");
  return isOneOf(RUN_ERRORS, error) ? t(`fuelPrice:error.${error}`) : t("fuelPrice:error.unknown", { code: error });
}

export type RunTone = "info" | "success" | "warning" | "error";

/** What a refresh came to, in words: the dialog's headline and what it means. */
export interface RunOutcome {
  tone: RunTone;
  /** "All prices are still the same", "2 new prices saved", "The update failed", ... */
  title: string;
  text: string;
}

/** A price the refresh stored, next to the price before it. */
export interface ChangedView {
  key: number;
  productId: number;
  /** "Pertamax Green 95" */
  product: string;
  /** "Pertamina" */
  merchant: string;
  /** The price before it and the day that one started; null when it is the product's first price. */
  before: { price: string; since: string } | null;
  /** The new price and the day it starts. */
  after: { price: string; from: string };
  change: PriceChange | null;
  /** It starts on a later day (announced). */
  upcoming: boolean;
  source: SourceView;
}

export interface RunView {
  status: FuelPriceRun["status"];
  /** The line under the button: "Checked the web 26-10-2026 12:13: nothing changed", "Update queued ...", ... */
  summary: string;
  outcome: RunOutcome;
  /** "26-10-2026 12:11 · took 2 minutes · by Siti Rahma" */
  facts: string;
  /** The prices it stored (the ones it found unchanged or didn't use are not listed). */
  changed: ChangedView[];
}

function runSummary(run: FuelPriceRun): string {
  switch (run.status) {
    case "queued":
      return t("fuelPrice:run.queuedSummary", { time: formatDateTime(run.requested_at) });
    case "running":
      return t("fuelPrice:run.runningSummary", { time: formatDateTime(run.started_at) });
    case "done":
      return run.prices_stored
        ? t("fuelPrice:run.doneStored", { time: formatDateTime(run.finished_at), count: run.prices_stored })
        : t("fuelPrice:run.doneUnchanged", { time: formatDateTime(run.finished_at) });
    case "failed":
      return t("fuelPrice:run.failedSummary", { time: formatDateTime(run.finished_at) });
  }
}

function runOutcome(run: FuelPriceRun): RunOutcome {
  const outcome = (tone: RunTone, title: string, text: string): RunOutcome => ({ tone, title, text });
  switch (run.status) {
    case "queued":
      return outcome("info", t("fuelPrice:details.outcome.queued"), t("fuelPrice:details.outcome.queuedText"));
    case "running":
      return outcome("info", t("fuelPrice:details.outcome.running"), t("fuelPrice:details.outcome.runningText"));
    case "failed":
      return outcome(
        "error",
        t("fuelPrice:details.outcome.failed"),
        `${runError(run.error)} ${t("fuelPrice:details.outcome.failedRetry")}`,
      );
    case "done": {
      const found = run.prices_found ?? 0;
      const stored = run.prices_stored ?? 0;
      if (stored > 0) {
        return outcome(
          "success",
          t("fuelPrice:details.outcome.stored", { count: stored }),
          t("fuelPrice:details.outcome.storedText", { count: found }),
        );
      }
      if (found === 0) {
        return outcome("warning", t("fuelPrice:details.outcome.nothingFound"), t("fuelPrice:details.outcome.nothingFoundText"));
      }
      return outcome(
        "success",
        t("fuelPrice:details.outcome.unchanged"),
        t("fuelPrice:details.outcome.unchangedText", { count: found }),
      );
    }
  }
}

/** "took 2 minutes"; null while it hasn't finished. */
function runDuration(run: FuelPriceRun): string | null {
  if (!run.started_at || !run.finished_at) return null;
  const milliseconds = Date.parse(run.finished_at) - Date.parse(run.started_at);
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return null;
  if (milliseconds < 60_000) return t("fuelPrice:details.tookUnderMinute");
  return t("fuelPrice:details.took", { count: Math.round(milliseconds / 60_000) });
}

function runFacts(run: FuelPriceRun): string {
  const by =
    run.trigger === "button" && run.requested_by
      ? t("fuelPrice:details.by", { name: run.requested_by.name })
      : t("fuelPrice:details.byBatch");
  return [formatDateTime(run.requested_at), runDuration(run), by].filter(Boolean).join(" · ");
}

/** The prices the refresh stored (the products' history entries it wrote), each next to the price before it. */
function changedPrices(run: FuelPriceRun, products: FuelProduct[], today: number | null): ChangedView[] {
  if (run.status !== "done" || !run.prices_stored) return [];
  return products.flatMap((product) =>
    product.history.flatMap((price, index): ChangedView[] => {
      if (price.fuel_price_run_id !== run.id) return [];
      const before = product.history[index + 1] ?? null;
      const day = dayNumber(price.valid_from);
      return [
        {
          key: price.id,
          productId: product.id,
          product: product.name,
          merchant: merchantName(product.merchant),
          before: before ? { price: priceText(before).text, since: before.valid_from } : null,
          after: { price: priceText(price).text, from: price.valid_from },
          change: changeOf(before, price),
          upcoming: day !== null && today !== null && day > today,
          source: sourceView(price),
        },
      ];
    }),
  );
}

function runView(run: FuelPriceRun, products: FuelProduct[], today: number | null): RunView {
  return {
    status: run.status,
    summary: runSummary(run),
    outcome: runOutcome(run),
    facts: runFacts(run),
    changed: changedPrices(run, products, today),
  };
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

export type FuelPriceController = ReturnType<typeof useFuelPriceController>;

export function useFuelPriceController(user: User) {
  const toast = useBlueToast();
  const { params } = useLocation();
  const merchant = toMerchant(params.get("merchant"));
  const kind = toKind(params.get("kind"));
  const search = params.get("q") ?? "";
  const sort = toSort(params.get("sort"));

  const pricesApi = useApi("fuel-prices", getFuelPrices);
  const { reload, update } = pricesApi;
  const [queuing, setQueuing] = useState(false);
  /** The dialog confirming a refresh is open; with why queuing it failed, if it did. */
  const [confirming, setConfirming] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [historyId, setHistoryId] = useState<number | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [allRecent, setAllRecent] = useState(false);
  /** The time the cooldown is checked against: moved on when it ends (see below). */
  const [now, setNow] = useState(() => Date.now());

  const data = pricesApi.state.status === "ready" ? pricesApi.state.data : null;
  const run = data?.last_run ?? null;
  const active = run?.status === "queued" || run?.status === "running";
  const parsedNext = data?.next_refresh_at ? Date.parse(data.next_refresh_at) : NaN;
  const nextRefreshAt = Number.isFinite(parsedNext) ? parsedNext : null;
  const tooSoon = nextRefreshAt !== null && nextRefreshAt > now;

  // While a refresh is queued or running, ask again now and then: its result shows when it is done.
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [active, reload]);

  // The button comes back by itself when the cooldown ends.
  useEffect(() => {
    if (nextRefreshAt === null) return;
    const timer = window.setTimeout(() => setNow(Date.now()), Math.max(0, nextRefreshAt - Date.now()) + 1000);
    return () => window.clearTimeout(timer);
  }, [nextRefreshAt]);

  const today = data ? dayNumber(data.today) : null;
  const allRows = useMemo(
    () => (data ? data.products.map((product, index) => rowOf(product, index, today)) : []),
    [data, today],
  );
  const recent = useMemo(() => recentChanges(allRows, today), [allRows, today]);

  // The merchant tabs count the products that pass the kind filter and the search; the table also the merchant.
  const searched = useMemo(
    () => allRows.filter((row) => (kind === "all" || row.product.fuel_kind === kind) && matchesSearch(row, search)),
    [allRows, kind, search],
  );
  const rows = useMemo(() => {
    const shown = searched.filter((row) => merchant === "all" || row.product.merchant === merchant);
    return sort ? [...shown].sort((a, b) => compareRows(a, b, sort)) : shown;
  }, [searched, merchant, sort]);

  const historyRow = historyId === null ? null : (allRows.find((row) => row.id === historyId) ?? null);
  const history = useMemo(() => (historyRow ? historyOf(historyRow, today) : null), [historyRow, today]);

  function show(next: { merchant?: MerchantFilter; kind?: KindFilter; search?: string; sort?: PriceSort | null }) {
    const nextMerchant = next.merchant ?? merchant;
    const nextKind = next.kind ?? kind;
    navigate(
      withParams(FUEL_PRICES_PATH, {
        merchant: nextMerchant === "all" ? null : nextMerchant,
        kind: nextKind === "all" ? null : nextKind,
        q: next.search ?? search,
        sort: sortParam(next.sort !== undefined ? next.sort : sort),
      }),
      { replace: true },
    );
  }

  async function startRefresh() {
    if (queuing || active || tooSoon) return;
    setQueuing(true);
    setQueueError(null);
    try {
      const queued = await queueRefresh(user.email);
      update((current) => ({ ...current, last_run: queued }));
      setConfirming(false);
      toast.show({ variant: "success", title: t("fuelPrice:toast.queued"), message: t("fuelPrice:toast.queuedText") });
    } catch (error) {
      setQueueError(errorMessage(error));
    } finally {
      setQueuing(false);
      reload(); // the cooldown, or a refresh someone else queued meanwhile
    }
  }

  const filtered = merchant !== "all" || kind !== "all" || search.trim() !== "";

  return {
    prices: pricesApi.state,
    /** The prices are being loaded again (after a refresh was queued, or while one runs). */
    refreshing: pricesApi.refreshing,
    reload,

    // The refresh from the web
    run: run && data ? runView(run, data.products, today) : null,
    refresh: {
      /** The request to queue one is on its way. */
      queuing,
      /** One is queued or running. */
      active,
      disabled: queuing || active || tooSoon,
      /** Why it can't be pressed now (the cooldown). */
      reason:
        tooSoon && !active && nextRefreshAt !== null
          ? t("fuelPrice:update.tooSoon", { time: formatDateTime(new Date(nextRefreshAt).toISOString()) })
          : null,
      /** Asks first (the confirm dialog): a refresh has Claude read the web, and blocks the next one for a day. */
      ask: () => {
        if (queuing || active || tooSoon) return;
        setQueueError(null);
        setConfirming(true);
      },
      confirm: {
        open: confirming,
        /** Why queuing it failed (409: one is already queued or running; 429: too soon). */
        error: queueError,
        /** When the button can be pressed again after this refresh: a day from now. */
        nextAt: formatDateTime(new Date(Date.now() + REFRESH_COOLDOWN_MS).toISOString()),
        start: () => void startRefresh(),
        close: () => {
          if (!queuing) setConfirming(false);
        },
      },
    },
    details: { open: detailsOpen, show: () => setDetailsOpen(true), close: () => setDetailsOpen(false) },

    // Recent changes
    recent: allRecent ? recent : recent.slice(0, RECENT_SHOWN),
    /** Recent changes not shown on top (until they are all shown). */
    moreRecent: allRecent ? 0 : Math.max(0, recent.length - RECENT_SHOWN),
    /** All of them are shown, and there are more than RECENT_SHOWN. */
    allRecentShown: allRecent && recent.length > RECENT_SHOWN,
    recentDays: RECENT_DAYS,
    showAllRecent: () => setAllRecent(true),
    showFewerRecent: () => setAllRecent(false),

    // Filter and sort
    merchant,
    merchantTabs: [
      { key: "all", label: t("fuelPrice:filter.allMerchants"), count: searched.length },
      ...MERCHANTS.map((item) => ({
        key: item.key,
        label: item.name,
        count: searched.filter((row) => row.product.merchant === item.key).length,
      })),
    ],
    setMerchant: (next: string) => show({ merchant: toMerchant(next) }),
    kind,
    kindOptions: [
      { value: "all", label: t("fuelPrice:filter.allKinds") },
      { value: "gasoline", label: t("fuelPrice:kind.gasoline") },
      { value: "diesel", label: t("fuelPrice:kind.diesel") },
    ],
    setKind: (next: string) => show({ kind: toKind(next) }),
    search,
    setSearch: (next: string) => show({ search: next }),
    sort: sort ?? undefined,
    setSort: (next: { key: string; direction: SortDirection }) => {
      const key = SORT_KEYS.find((item) => item === next.key);
      if (key) show({ sort: { key, direction: next.direction } });
    },
    filtered,
    /** No fuel at all (a first deploy, or an emptied database): the next refresh adds them. */
    noProducts: allRows.length === 0,
    clearFilters: () => show({ merchant: "all", kind: "all", search: "" }),
    rows,
    /** "19 products", "3 of 19 products" */
    countText: filtered
      ? t("fuelPrice:filter.someOf", { count: allRows.length, shown: rows.length })
      : t("fuelPrice:filter.all", { count: allRows.length }),

    // One product's history
    history,
    openHistory: (productId: number) => setHistoryId(productId),
    closeHistory: () => setHistoryId(null),
  };
}

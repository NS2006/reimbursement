// What the backend sends for the fuel prices (GET /api/fuel-prices, POST /api/fuel-prices/refresh).
// Amounts are numbers, dates are "DD-MM-YYYY" text (days in WIB), timestamps ISO 8601 text.

export type FuelMerchant = "pertamina" | "shell" | "bp" | "vivo";

export type FuelKind = "gasoline" | "diesel";

/** official: the merchant's own page; news: a news site; manual: entered by hand. */
export type FuelPriceSource = "official" | "news" | "manual";

/** A product's price in DKI Jakarta from one day on, until the next one. */
export interface FuelPrice {
  id: number;
  /** null: the source listed no price for it from valid_from on (not sold, or not listed). */
  price_per_liter: number | null;
  valid_from: string;
  source: FuelPriceSource;
  source_url: string | null;
  /** The sentence on the source page that gives the price, as quoted. */
  source_text: string | null;
  fetched_at: string;
  /** The refresh from the web that stored it; null for a manual or seeded price. */
  fuel_price_run_id: number | null;
}

export interface FuelProduct {
  id: number;
  merchant: FuelMerchant;
  /** As the merchant writes it: Pertamax, Shell V-Power, Revvo 92, ... */
  name: string;
  fuel_kind: FuelKind;
  /** Octane, for gasoline. */
  ron: number | null;
  /** The price today; null: no price yet. */
  price: FuelPrice | null;
  /** The (different) price before it; null when today's is the first. */
  previous: FuelPrice | null;
  /** The next price, announced for a later day; null when none is. */
  upcoming: FuelPrice | null;
  /** Every price change, the newest valid_from first (an upcoming one too). A price equal to the one before it is
   * left out: it only goes on with it. */
  history: FuelPrice[];
}

export type FuelPriceRunStatus = "queued" | "running" | "done" | "failed";

/** A price the checks refused, so it was not stored. A value the worker wrote in another shape is null. */
/** A price the refresh found but didn't use. */
export interface RejectedFuelPrice {
  merchant: string | null;
  product: string | null;
  price_per_liter: number | null;
  /** The day it would start, DD-MM-YYYY; null when the page gave none. */
  valid_from: string | null;
  source_url: string | null;
  /** Why: implausible_price, one_site_only, quote_not_on_page, ... (the page explains each). */
  reason: string | null;
}

/** A refresh of the prices from the web (Claude finds recent articles about the prices and reads them). */
export interface FuelPriceRun {
  id: number;
  /** button: someone pressed it on this page; batch: a new batch of reports was read. */
  trigger: "button" | "batch";
  requested_by: { email: string; name: string } | null;
  status: FuelPriceRunStatus;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  prices_found: number | null;
  prices_stored: number | null;
  rejected_prices: RejectedFuelPrice[] | null;
}

export interface FuelPriceList {
  /** Today in WIB, DD-MM-YYYY: the day "price" is for. */
  today: string;
  /** The active products of every merchant, in the merchants' order (gasoline by RON, then diesel). */
  products: FuelProduct[];
  /** The newest refresh; null before the first one. */
  last_run: FuelPriceRun | null;
  /** When the button can be pressed again (one refresh a day); null: now, unless one is queued or running. */
  next_refresh_at: string | null;
}

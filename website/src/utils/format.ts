import { dateLocale } from "../app/i18n";

// How values are shown on the website: amounts in rupiah and numbers in the Indonesian style (Rp 1.358.170, 28,5),
// dates as DD-MM-YYYY (the backend already sends dates that way) and times as DD-MM-YYYY HH:mm in local time, in
// both languages. Words (day and month names) follow the language.

/** Shown for an empty value. */
export const EMPTY = "-";

/** Shown where the OCR returned null for a field (it found no value there). */
export const NULL_VALUE = "NULL";

const money = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const decimal = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });
const percent = new Intl.NumberFormat("id-ID", { style: "percent", maximumFractionDigits: 0 });
const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
// Per locale, made when first needed
/** The months are in WIB for everyone (as the backend's report_filter.MONTH_ZONE): a report belongs to the month it
 * was received in, in Jakarta, whatever the reviewer's own time zone. */
export const MONTH_TIME_ZONE = "Asia/Jakarta";

const monthFormats = new Map<string, Intl.DateTimeFormat>();
const weekdayFormats = new Map<string, Intl.DateTimeFormat>();

function isNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function formatMoney(value: number | null | undefined): string {
  return isNumber(value) ? money.format(value) : EMPTY;
}

export function formatNumber(value: number | null | undefined): string {
  return isNumber(value) ? decimal.format(value) : EMPTY;
}

/** 0.93 -> "93%" */
export function formatPercent(value: number | null | undefined): string {
  return isNumber(value) ? percent.format(value) : EMPTY;
}

export function formatSeconds(value: number | null | undefined): string {
  return isNumber(value) ? `${decimal.format(Math.round(value * 10) / 10)} s` : EMPTY;
}

/** An ISO 8601 timestamp from the backend -> "14-10-2026 09:30" in the browser's time zone. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const moment = new Date(value);
  if (Number.isNaN(moment.getTime())) return value;
  const parts = Object.fromEntries(dateTime.formatToParts(moment).map((part) => [part.type, part.value]));
  return `${parts.day}-${parts.month}-${parts.year} ${parts.hour}:${parts.minute}`;
}

/** A moment (milliseconds) -> "20-10-2026" in the browser's time zone. */
/** The month of a moment, in WIB: "October 2026" ("Oktober 2026" in Indonesian). */
export function formatMonth(value: string | number | Date): string {
  const locale = dateLocale();
  let format = monthFormats.get(locale);
  if (!format) {
    format = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: MONTH_TIME_ZONE });
    monthFormats.set(locale, format);
  }
  return format.format(new Date(value));
}

export function formatDate(value: number): string {
  const parts = Object.fromEntries(dateTime.formatToParts(new Date(value)).map((part) => [part.type, part.value]));
  return `${parts.day}-${parts.month}-${parts.year}`;
}

/** A moment (milliseconds) -> "09:30" in the browser's time zone. */
export function formatTime(value: number): string {
  const parts = Object.fromEntries(dateTime.formatToParts(new Date(value)).map((part) => [part.type, part.value]));
  return `${parts.hour}:${parts.minute}`;
}

/** A moment (milliseconds) -> its day name in the current language: "Thursday", "Kamis". */
export function formatWeekday(value: number): string {
  const locale = dateLocale();
  let format = weekdayFormats.get(locale);
  if (!format) {
    format = new Intl.DateTimeFormat(locale, { weekday: "long" });
    weekdayFormats.set(locale, format);
  }
  return format.format(value);
}

/** Text as it is, or EMPTY when there is none. */
export function formatText(value: string | null | undefined): string {
  return value ? value : EMPTY;
}

import { t } from "../app/i18n";
import { EMPTY, formatMoney, formatNumber } from "./format";

// BBM fields: their names on the page and how their values are shown (the BBM list and the BBM report page).

type FieldKind = "text" | "money" | "number";

type BbmField =
  | "product_name"
  | "date_of_expense"
  | "price_per_liter"
  | "volume_liter"
  | "kilometer"
  | "total_price"
  | "discount"
  | "grand_total";

/** Also used for the field_name of an OCR difference (grand_total and discount only appear there). Their names, in
 * the current language, come from fieldLabel(). */
export const BBM_FIELDS: Record<string, { kind: FieldKind }> = {
  product_name: { kind: "text" },
  date_of_expense: { kind: "text" },
  price_per_liter: { kind: "money" },
  volume_liter: { kind: "number" },
  kilometer: { kind: "number" },
  total_price: { kind: "money" },
  discount: { kind: "money" },
  grand_total: { kind: "money" },
};

/** The name of a field in the current language ("Price per liter", "Harga per liter"). */
export function fieldLabel(field: string): string {
  return field in BBM_FIELDS ? t(`fields.${field as BbmField}`) : field.replaceAll("_", " ");
}

/** A field's value as text: amounts in rupiah, other numbers Indonesian style, text (or unreadable numbers) as it is. */
export function formatField(field: string, value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return EMPTY;
  const kind = BBM_FIELDS[field]?.kind ?? "text";
  const number = typeof value === "number" ? value : Number(value);
  if (kind === "text" || !Number.isFinite(number)) return String(value);
  return kind === "money" ? formatMoney(number) : formatNumber(number);
}

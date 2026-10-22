import { t } from "../app/i18n";

// Where two values of the same field differ, so the reviewer sees it at once: the characters that differ, and the
// kind of slip it looks like (two digits swapped, a decimal point or a zero out of place, day and month swapped).

/** A piece of a value as shown; changed: it differs from the other value. */
export interface ValuePart {
  text: string;
  changed: boolean;
}

/**
 * `value` in parts, marking where it differs from `other`. Values of the same length are compared character by
 * character ("Rp 401.466" / "Rp 404.166": the 1 and the 4); otherwise what they share at the start and at the end
 * is kept and the middle is marked ("Rp 10.000" / "Rp 100.000": the extra 0). Gives the same split for both values.
 */
export function changedParts(value: string, other: string): ValuePart[] {
  const parts: ValuePart[] = [];
  const add = (text: string, changed: boolean) => {
    if (!text) return;
    const last = parts.at(-1);
    if (last && last.changed === changed) last.text += text;
    else parts.push({ text, changed });
  };
  if (value.length === other.length) {
    for (let i = 0; i < value.length; i++) add(value[i], value[i] !== other[i]);
    return parts;
  }
  let start = 0;
  while (start < value.length && start < other.length && value[start] === other[start]) start++;
  let end = 0;
  while (
    end < value.length - start &&
    end < other.length - start &&
    value[value.length - 1 - end] === other[other.length - 1 - end]
  ) {
    end++;
  }
  add(value.slice(0, start), false);
  add(value.slice(start, value.length - end), true);
  add(value.slice(value.length - end), false);
  return parts;
}

/** The digits of a number as the backend writes it ("28.5", "646180"), and where its decimal point is. */
function digitsOf(value: string): { digits: string; point: number } | null {
  if (!/^\d+(\.\d+)?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return { digits: whole + fraction, point: whole.length };
}

/** A slip between two numbers, or null: one digit off, two digits swapped, or a factor of 10 (point or zero). */
function numberSlip(a: string, b: string): string | null {
  const x = digitsOf(a);
  const y = digitsOf(b);
  if (!x || !y) return null;
  const big = Math.max(Number(a), Number(b));
  const small = Math.min(Number(a), Number(b));
  if (small > 0) {
    const power = Math.log10(big / small);
    if (power >= 1 && power <= 3 && Math.abs(power - Math.round(power)) < 1e-9) {
      const times = 10 ** Math.round(power);
      return x.digits.replace(/0+$/, "") === y.digits.replace(/0+$/, "")
        ? t("report:slip.times", { times: times.toLocaleString("id-ID") })
        : null;
    }
  }
  if (x.digits.length !== y.digits.length || x.point !== y.point) return null;
  const differing = [...x.digits].flatMap((digit, i) => (digit !== y.digits[i] ? [i] : []));
  if (differing.length === 1) {
    const [i] = differing;
    return t("report:slip.oneDigit", { a: x.digits[i], b: y.digits[i] });
  }
  if (differing.length === 2) {
    const [i, j] = differing;
    if (x.digits[i] === y.digits[j] && x.digits[j] === y.digits[i]) {
      return t("report:slip.swapped", { a: x.digits[i], b: x.digits[j] });
    }
  }
  return null;
}

/** A slip between two DD-MM-YYYY dates, or null: day and month swapped, or only one of day, month, year differs. */
function dateSlip(a: string, b: string): string | null {
  const x = a.split("-");
  const y = b.split("-");
  if (x.length !== 3 || y.length !== 3 || ![...x, ...y].every((part) => /^\d+$/.test(part))) return null;
  const [day, month, year] = x;
  if (day === y[1] && month === y[0] && year === y[2] && day !== month) return t("report:slip.dayMonth");
  const same = x.map((part, i) => part === y[i]);
  if (same.filter(Boolean).length !== 2) return null;
  return [t("report:slip.day"), t("report:slip.month"), t("report:slip.year")][same.indexOf(false)];
}

/** The kind of slip that turns one raw value into the other ("Two digits are swapped (1 and 4)"), when it is a
 *  common one; null otherwise. `kind`: how the field is compared. */
export function slipBetween(kind: "number" | "date", a: string, b: string): string | null {
  return kind === "number" ? numberSlip(a, b) : dateSlip(a, b);
}

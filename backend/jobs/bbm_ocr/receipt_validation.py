"""
Validate employee-submitted receipt data against the OCR result.

Per image:
  1. Compare field by field with plain code (no LLM). Receipts and products are paired with the same
     logic receipt_evaluation.py uses, so several receipts in one image work too.
  2. Nothing differs                  -> status "matched"       (the user is not warned)
  3. One number differs               -> check it with arithmetic:
                                         the value that fits the other numbers on the receipt is the right one
                                         (quantity x unit_price = total_price, sum(total_price) - discount = total)
  4. Every difference was harmless    -> status "proceed"
     Anything else                    -> status "needs_review"  (the user must check this receipt)

Fail-safe rule: when in doubt (name or date mismatch, several numbers differ, the math cannot decide, missing or extra receipts/products) the receipt is flagged.

A field the submitted data does not have (no key in its receipt or product) is not compared, and the arithmetic takes
it from the OCR's reading of the same product (the reimbursement API sends no price per liter). The API sends no
discount or total per receipt either, only the grand total of the file (what was paid, after discounts): pass it as
grand_total and the file is checked as a whole instead, the totals the OCR read on its receipts against it (the same
arithmetic decides who misread when that is the only difference).

A submitted product without a price per liter still has one: its total_price / quantity. It is compared with the price
the OCR read, allowing PRODUCT_REL_TOLERANCE (_computed_price). A difference there is always flagged, never judged by
the arithmetic: a price the OCR misread and an amount or volume changed on the receipt look the same.

Product names are matched with names_match by default (the OCR against a receipt's own spelling, as in the ground
truth); pass names=product_labels.matches_fuel_type for the reimbursement API's fuel types.

With a grand total, "matched" and "proceed" also need the receipts to back it: the smaller of their printed total and
their amounts minus their discounts, an amount counting for no more than volume x price per liter (backed_amounts).
A claim above that -> "needs_review", whatever else matched: one changed number on the receipt can't approve it.
"""

import json
import math
from pathlib import Path

from backend.jobs.bbm_ocr.receipt_evaluation import (
    NUMERIC_MODE,
    assign,
    compare_receipt,
    names_match,
    product_similarity,
    to_float,
)

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
CONFIDENT = 0.90               # OCR confidence at or above this counts as "OCR read it clearly"

# products (the pump rounds the amount), while sum(total_price) - discount equals total exactly.
MATH_FIELDS = {"quantity", "unit_price", "total_price", "total", "discount"}
PRODUCT_REL_TOLERANCE = 0.005
PRODUCT_ABS_FLOOR = {"quantity": 0.01, "unit_price": 1.0, "total_price": 100.0}
RECEIPT_ABS_TOLERANCE = 1.0
MATH_RULES = {
    "quantity": "total_price / unit_price",
    "unit_price": "total_price / quantity",
    "total_price": "quantity x unit_price",
    "total": "sum of total_price - discount",
    "discount": "sum of total_price - total",
}

# --------------------------------------------------------------------------
# Pairing (same one-to-one assignment as receipt_evaluation.evaluate)
# --------------------------------------------------------------------------
def _pair_receipts(submitted, ocr, mode, names):
    """{submitted_index: ocr_index}"""
    sim = []
    for i, o in enumerate(ocr):
        row = []
        for j, s in enumerate(submitted):
            _, extras, correct, _ = compare_receipt(o, s, mode, names)
            row.append(correct - 0.5 * extras + (1e-3 if i == j else 0.0))
        sim.append(row)
    return {j: i for i, j in assign(sim)}


def _pair_products(ocr_products, submitted_products, mode, names):
    """{submitted_product_index: ocr_product_index}"""
    sim = [
        [product_similarity(p, s, mode, i, j, names) for j, s in enumerate(submitted_products)]
        for i, p in enumerate(ocr_products)
    ]
    return {j: i for i, j in assign(sim)}


# --------------------------------------------------------------------------
# Mismatch records
# --------------------------------------------------------------------------
def _confidence(container, field):
    value = ((container or {}).get("confidence") or {}).get(field)
    return value if isinstance(value, (int, float)) else None


def _base_hint(m):
    """Explanation for differences nobody judged. OCR confidence is shown as information, not as proof."""
    conf = m["ocr_confidence"]
    if m.get("issue") == "missing_in_ocr":
        return "A submitted product was not found on the receipt reading. Check the image."
    if m.get("issue") == "not_submitted":
        return "The receipt shows a product that was not submitted. Check the image."
    if m["ocr"] is None:
        return "The receipt reading is empty for this field (unreadable). Check the image."
    if conf is None:
        return "The values differ and no OCR confidence is available. Check the image."
    if conf >= CONFIDENT:
        return f"The values differ (OCR confidence is high: {conf:.2f}). Check the image to see which one is right."
    return f"The values differ and OCR confidence is low ({conf:.2f}), so it may be a misread. Check the image."


def _submitted_has(e, submitted_receipt, submitted_products):
    """Whether the submitted data has the field of this mismatch (a field it does not send is not compared)."""
    if e["type"] != "field_mismatch":
        return True
    if e["level"] == "receipt":
        return e["field"] in submitted_receipt
    return e["field"] in submitted_products[e["product_index"]]


def _collect_mismatches(submitted_receipt, ocr_receipt, mode, names):
    _, _, _, errors = compare_receipt(ocr_receipt, submitted_receipt, mode, names)
    ocr_products = ocr_receipt.get("products") or []
    submitted_products = submitted_receipt.get("products") or []
    product_pairs = _pair_products(ocr_products, submitted_products, mode, names)

    mismatches = []
    for e in errors:
        if not _submitted_has(e, submitted_receipt, submitted_products):
            continue
        if e["type"] == "field_mismatch" and e["level"] == "receipt":
            m = {"level": "receipt", "field": e["field"], "submitted": e["gt"], "ocr": e["pred"],
                 "ocr_confidence": _confidence(ocr_receipt, e["field"])}
        elif e["type"] == "field_mismatch":
            j = e["product_index"]
            i = product_pairs.get(j)
            ocr_product = ocr_products[i] if i is not None else {}
            m = {"level": "product", "field": e["field"], "product_index": j, "ocr_product_index": i,
                 "submitted": e["gt"], "ocr": e["pred"],
                 "ocr_confidence": _confidence(ocr_product, e["field"])}
        elif e["type"] == "missing_product":
            m = {"level": "product", "field": None, "issue": "missing_in_ocr", "product_index": e["product_index"],
                 "submitted": e["gt"], "ocr": None, "ocr_confidence": None}
        else:  # extra_product
            m = {"level": "product", "field": None, "issue": "not_submitted", "product_index": e["product_index"],
                 "submitted": None, "ocr": e["pred"], "ocr_confidence": None}
        if "diff" in e:
            m["difference_ocr_minus_submitted"] = e["diff"]
        m["resolved"] = False
        mismatches.append(m)

    for j, i in sorted(product_pairs.items()):
        m = _computed_price(submitted_products[j], ocr_products[i], j, i, mismatches)
        if m:
            mismatches.append(m)
    return mismatches


# --------------------------------------------------------------------------
# The price per liter the submitted numbers give
# --------------------------------------------------------------------------
PRICE_RULE = "total_price / quantity"


def _computed_price(submitted_product, ocr_product, j, i, mismatches):
    """
    A submitted product without a unit_price (the reimbursement API sends none) against the price per liter the OCR
    read on its product: its total_price / quantity should be that price, allowing the arithmetic's tolerance (_fits:
    PRODUCT_REL_TOLERANCE, at least PRODUCT_ABS_FLOOR). None when it is, else a mismatch (field "unit_price",
    "computed": True, with its own hint). Not compared when the OCR read no price: some receipts don't print one (the
    MyPertamina app's transaction screen shows liters and the amount only).

    Never judged by the arithmetic: the receipt's own numbers don't fit together (its volume x price is not its
    amount), and an OCR misread of the price looks just like an amount or volume changed on the receipt. Skipped
    when the product's quantity or total_price already differs: the price then differs because of it, and that
    difference is judged on its own (the OCR's price is one of the numbers it is judged with).
    """
    if "unit_price" in submitted_product:
        return None
    quantity, total_price = to_float(submitted_product.get("quantity")), to_float(submitted_product.get("total_price"))
    if not quantity or total_price is None:
        return None
    if any(m.get("product_index") == j and m["field"] in ("quantity", "total_price") for m in mismatches):
        return None
    computed = total_price / quantity
    ocr_price = to_float(ocr_product.get("unit_price"))
    if ocr_price is None or _fits("unit_price", ocr_price, computed):
        return None
    return {
        "level": "product", "field": "unit_price", "product_index": j, "ocr_product_index": i,
        "submitted": round(computed, 2), "ocr": ocr_product.get("unit_price"),
        "ocr_confidence": _confidence(ocr_product, "unit_price"),
        "difference_ocr_minus_submitted": round(ocr_price - computed, 6), "computed": True, "resolved": False,
        "hint": (f"The price per liter on the receipt ({_fmt(ocr_price)}) is not the one the submitted numbers give "
                 f"({PRICE_RULE} = {_fmt(computed)}), more than {PRODUCT_REL_TOLERANCE:.1%} apart. Either the OCR "
                 f"misread the price, or the amount or volume on the receipt was changed. Check the image."),
    }


# --------------------------------------------------------------------------
# Arithmetic check for a single number mismatch
# --------------------------------------------------------------------------
def _implied(field, receipt, product_index, fallback=None):
    """The value `field` should have according to the other numbers of the same receipt (None if not computable).
    fallback: a product whose numbers stand in for the ones the receipt's product does not have."""
    products = receipt.get("products") or []
    if field in PRODUCT_ABS_FLOOR:
        if product_index is None or product_index >= len(products):
            return None
        p = {**(fallback or {}), **products[product_index]}
        q, u, tp = to_float(p.get("quantity")), to_float(p.get("unit_price")), to_float(p.get("total_price"))
        if field == "total_price":
            return q * u if q is not None and u is not None else None
        if field == "quantity":
            return tp / u if tp is not None and u else None
        return tp / q if tp is not None and q else None  # unit_price
    prices = [to_float(p.get("total_price")) for p in products]
    discount, total = to_float(receipt.get("discount")), to_float(receipt.get("total"))
    if not prices or None in prices:
        return None
    gross = sum(prices)
    if field == "total":
        return gross - discount if discount is not None else None
    return gross - total if total is not None else None  # discount


def _fits(field, actual, implied):
    actual = to_float(actual)
    if actual is None or implied is None:
        return False
    if field in PRODUCT_ABS_FLOOR:
        tolerance = max(PRODUCT_ABS_FLOOR[field], PRODUCT_REL_TOLERANCE * abs(implied))
    else:
        tolerance = RECEIPT_ABS_TOLERANCE
    return abs(actual - implied) <= tolerance


def _fmt(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _judge_math(m, submitted_receipt, ocr_receipt):
    """
    Only ONE number differs, so the other numbers on the receipt were read the same by both sides.
    A real receipt is consistent with itself, so whichever value fits those other numbers is the right one.
    If the submitted value fits and the OCR value does not, the OCR misread it: harmless.
    A number the submitted side does not have (the price per liter) is the OCR's: both sides use the same one.
    """
    field, rule = m["field"], MATH_RULES[m["field"]]
    ocr_products, i = ocr_receipt.get("products") or [], m.get("ocr_product_index")
    ocr_product = ocr_products[i] if i is not None and i < len(ocr_products) else None
    s_implied = _implied(field, submitted_receipt, m.get("product_index"), fallback=ocr_product)
    o_implied = _implied(field, ocr_receipt, i)
    s_fits = _fits(field, m["submitted"], s_implied)
    o_fits = _fits(field, m["ocr"], o_implied)
    m["math"] = {"rule": rule, "submitted_implied": s_implied, "ocr_implied": o_implied,
                 "submitted_fits": s_fits, "ocr_fits": o_fits}

    if s_fits and not o_fits:
        m["resolved"] = True
        m["hint"] = (f"The submitted {field} ({_fmt(m['submitted'])}) fits the other numbers on the receipt "
                     f"({rule} = {_fmt(s_implied)}); the OCR value ({m['ocr']}) does not. Looks like an OCR misread.")
    elif o_fits and not s_fits:
        m["hint"] = (f"The OCR {field} ({_fmt(m['ocr'])}) fits the other numbers on the receipt "
                     f"({rule} = {_fmt(o_implied)}); the submitted value ({m['submitted']}) does not. "
                     f"The submitted value is probably wrong.")
    elif s_fits and o_fits:
        m["hint"] = "Both values fit the other numbers on the receipt, so the math cannot decide. Check the image."
    else:
        m["hint"] = "Neither value fits the other numbers on the receipt. Check the image."


# --------------------------------------------------------------------------
# The file as a whole: the grand total
# --------------------------------------------------------------------------
FILE_TOTAL_RULE = "sum of total_price - discount over the receipts"


def _check_file_total(submitted, ocr, grand_total, receipts, unpaired):
    """
    The submitted grand total (what was paid for every receipt of the file, after discounts) against the totals the
    OCR read on its receipts. [] when they agree, else one mismatch (level "file", field "grand_total").

    When it is the only number that differs (every receipt agrees with the OCR otherwise), the arithmetic decides as
    for one receipt: the discounts are printed on the receipts only, so both sides are checked against
    sum(total_price) - discount of the receipts the OCR read.
    """
    totals = [to_float(o.get("total")) for o in ocr]
    ocr_total = sum(totals) if ocr and None not in totals else None
    submitted_total = to_float(grand_total)
    if ocr_total is not None and abs(ocr_total - submitted_total) <= RECEIPT_ABS_TOLERANCE:
        return []

    confidences = [_confidence(o, "total") for o in ocr]
    m = {"level": "file", "field": "grand_total", "submitted": submitted_total, "ocr": ocr_total,
         "ocr_confidence": min(confidences) if confidences and None not in confidences else None, "resolved": False}
    numbers_differ = unpaired or any(
        x.get("field") in MATH_FIELDS or x.get("issue") for r in receipts for x in r["mismatches"]
    )
    if ocr_total is None:
        m["hint"] = "The OCR could not read the total of every receipt in the file. Check the image."
    elif numbers_differ:
        m["hint"] = "Several numbers differ in this file, so one OCR misread cannot explain it. " + _base_hint(m)
    else:
        _judge_file_total(m, submitted, ocr)
    return [m]


def _judge_file_total(m, submitted, ocr):
    def gross(receipts):
        return [to_float(p.get("total_price")) for r in receipts for p in (r.get("products") or [])]

    discounts = [to_float(o.get("discount")) or 0.0 for o in ocr]
    s_prices, o_prices = gross(submitted), gross(ocr)
    s_implied = sum(s_prices) - sum(discounts) if s_prices and None not in s_prices else None
    o_implied = sum(o_prices) - sum(discounts) if o_prices and None not in o_prices else None
    s_fits = s_implied is not None and abs(m["submitted"] - s_implied) <= RECEIPT_ABS_TOLERANCE
    o_fits = o_implied is not None and abs(m["ocr"] - o_implied) <= RECEIPT_ABS_TOLERANCE
    m["math"] = {"rule": FILE_TOTAL_RULE, "submitted_implied": s_implied, "ocr_implied": o_implied,
                 "submitted_fits": s_fits, "ocr_fits": o_fits}

    if s_fits and not o_fits:
        m["resolved"] = True
        m["hint"] = (f"The submitted grand total ({_fmt(m['submitted'])}) fits the receipts ({FILE_TOTAL_RULE} = "
                     f"{_fmt(s_implied)}); the OCR total ({_fmt(m['ocr'])}) does not. Looks like an OCR misread.")
    elif o_fits and not s_fits:
        m["hint"] = (f"The OCR total ({_fmt(m['ocr'])}) fits the receipts ({FILE_TOTAL_RULE} = {_fmt(o_implied)}); "
                     f"the submitted grand total ({_fmt(m['submitted'])}) does not. The submitted value is probably wrong.")
    elif s_fits and o_fits:
        m["hint"] = "Both values fit the other numbers on the receipts, so the math cannot decide. Check the image."
    else:
        m["hint"] = "Neither value fits the other numbers on the receipts. Check the image."


# --------------------------------------------------------------------------
# What the receipts back: an approval by the OCR never pays more
# --------------------------------------------------------------------------
# The receipt file comes from the person who claims: a changed total line, or text hidden in a PDF, could make the OCR
# read the claimed amount on it. So the amount is approved only when every number the OCR read on the receipts agrees
# with it, not only their printed total.

def _amount(value):
    """A number the OCR read, when it can be an amount of money: finite and not negative (else None)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def backed_amounts(ocr):
    """What the receipts the OCR read back, added up over them:

        printed  their printed totals
        lines    their amounts minus their discounts
        backed   per receipt the smaller of its printed total and its amounts minus its discount, an amount counting
                 for no more than its volume x price per liter (when both were read)

    None when a number they need is missing or impossible: no total or amount, a negative number, a discount above
    the amounts, a receipt without products."""
    printed = lines = backed = 0.0
    for receipt in ocr:
        total, discount = _amount(receipt.get("total")), receipt.get("discount")
        discount = 0.0 if discount is None else _amount(discount)
        products = receipt.get("products") or []
        if total is None or discount is None or not products:
            return None
        amounts = checked = 0.0
        for product in products:
            price = _amount(product.get("total_price"))
            if price is None:
                return None
            quantity, unit_price = _amount(product.get("quantity")), _amount(product.get("unit_price"))
            amounts += price
            if quantity is not None and unit_price is not None and not _fits("total_price", price, quantity * unit_price):
                price = min(price, quantity * unit_price)
            checked += price
        if discount > amounts:
            return None
        printed += total
        lines += amounts - discount
        backed += min(total, checked - discount)
    return {"printed": printed, "lines": lines, "backed": backed}


def _unbacked_claim(claimed, ocr):
    """A file mismatch (as _check_file_total gives) when the receipts don't back the claimed grand total, else None."""
    amounts = backed_amounts(ocr)
    if amounts is not None and claimed <= amounts["backed"] + RECEIPT_ABS_TOLERANCE:
        return None

    totals = [to_float(o.get("total")) for o in ocr]
    m = {"level": "file", "field": "grand_total", "submitted": claimed,
         "ocr": sum(totals) if ocr and None not in totals else None, "ocr_confidence": None, "resolved": False}
    if amounts is None:
        m["hint"] = ("Some numbers on the receipts are missing or impossible (an amount, a negative number, a discount "
                     "above the amounts), so they can't show what was paid. Check the image.")
        return m

    printed, lines, backed = amounts["printed"], amounts["lines"], amounts["backed"]
    if printed < claimed - RECEIPT_ABS_TOLERANCE:
        why = f"their total says {_fmt(printed)}"
    elif lines < printed - RECEIPT_ABS_TOLERANCE:
        why = f"their total says {_fmt(printed)}, but their amounts minus the discounts come to {_fmt(lines)}"
    else:
        why = "their amounts are more than volume x price per liter gives"
    m["hint"] = (f"The receipts don't back the {_fmt(claimed)} claimed: {why}. All their numbers back only "
                 f"{_fmt(backed)}. A number may have been changed, or the OCR misread one. Check the image.")
    return m


# --------------------------------------------------------------------------
# Public functions
# --------------------------------------------------------------------------
def validate_receipts(submitted, ocr, mode=NUMERIC_MODE, grand_total=None, names=names_match):
    """
    Validate the submitted receipts of ONE image against its OCR receipts.

    submitted, ocr : lists of receipt dicts (see module docstring)
    grand_total    : what was paid for the whole file, when the submitted receipts have no total of their own;
                     checked against the totals the OCR read (None: no file check)
    names          : names(ocr_name, submitted_name) -> whether two product names are the same product

    Returns {"status": "matched" | "proceed" | "needs_review",
             "receipts": [{submitted_index, ocr_index, status, mismatches: [...]}],
             "unpaired": [...],           # receipts that exist on only one side
             "file": [...]}               # the grand total, when it differs (at most one mismatch)
    """
    submitted, ocr = submitted or [], ocr or []
    pairs = _pair_receipts(submitted, ocr, mode, names)

    receipts = []
    for j, s in enumerate(submitted):
        if j not in pairs:
            continue
        o = ocr[pairs[j]]
        mismatches = _collect_mismatches(s, o, mode, names)

        structural = any(m.get("issue") for m in mismatches)
        numeric = [m for m in mismatches if m.get("field") in MATH_FIELDS and not m.get("issue") and not m.get("computed")]
        for m in mismatches:
            if m.get("computed"):
                continue  # the computed price per liter: its hint is set, and it is never judged
            if m in numeric and len(numeric) == 1 and not structural:
                _judge_math(m, s, o)
            else:
                m["hint"] = _base_hint(m)
                if m in numeric and len(numeric) > 1:
                    m["hint"] = "Several numbers differ on this receipt, so one OCR misread cannot explain it. " + m["hint"]

        if not mismatches:
            status = "matched"
        elif all(m["resolved"] for m in mismatches):
            status = "proceed"
        else:
            status = "needs_review"
        receipts.append({"submitted_index": j, "ocr_index": pairs[j], "status": status, "mismatches": mismatches})

    unpaired = [
        {"side": "submitted", "index": j, "issue": "receipt_not_found_in_ocr",
         "hint": "A submitted receipt was not found in the image. Check the image."}
        for j in range(len(submitted)) if j not in pairs
    ] + [
        {"side": "ocr", "index": i, "issue": "receipt_not_submitted",
         "hint": "The image shows a receipt that was not submitted. Check the image."}
        for i in range(len(ocr)) if i not in set(pairs.values())
    ]

    file_mismatches = [] if grand_total is None else _check_file_total(submitted, ocr, grand_total, receipts, unpaired)

    if (unpaired or any(r["status"] == "needs_review" for r in receipts)
            or any(not m["resolved"] for m in file_mismatches)):
        status = "needs_review"
    elif any(r["status"] == "proceed" for r in receipts) or file_mismatches:
        status = "proceed"
    else:
        status = "matched"

    # Approved only when the receipts back the amount: then a difference the arithmetic put down to an OCR misread
    # can't raise what is paid either. Else a reviewer checks, and this explains the grand total instead; a
    # difference put down to an OCR misread is no longer judged (the submitted side "fitting" is what would pay more).
    if status != "needs_review" and grand_total is not None:
        unbacked = _unbacked_claim(to_float(grand_total), ocr)
        if unbacked:
            for receipt in receipts:
                for m in receipt["mismatches"]:
                    if m["resolved"]:
                        m["resolved"] = False
                        m.pop("math", None)
                        m["hint"] = _base_hint(m)
                        receipt["status"] = "needs_review"
            status, file_mismatches = "needs_review", [unbacked]

    return {"status": status, "receipts": receipts, "unpaired": unpaired, "file": file_mismatches}


def validate_batch(submitted_by_image, ocr_by_image, mode=NUMERIC_MODE):
    """Both arguments are dicts keyed by image id, like ground_truth/gt.json and batch_results.json."""
    ocr_by_image = {str(k): v for k, v in ocr_by_image.items()}
    return {
        str(image_id): validate_receipts(submitted, ocr_by_image.get(str(image_id)) or [], mode)
        for image_id, submitted in submitted_by_image.items()
    }


# --------------------------------------------------------------------------
# Log every image that is not "matched" (stand-alone, delete this function to remove the feature)
# --------------------------------------------------------------------------
def log_unmatched_cases(results, path="unmatched_cases.json"):
    """
    Write every image whose status is not "matched" (so "proceed" and "needs_review") to a file,
    .json (default) or .txt, chosen by the file extension. Overwrites the file and returns the list of cases.
    """
    cases = []
    for image_id, result in results.items():
        if result["status"] == "matched":
            continue
        receipts = []
        for r in result["receipts"]:
            if r["status"] == "matched":
                continue
            differences = []
            for m in r["mismatches"]:
                decided_by = "math" if "math" in m else "code"
                differences.append({
                    "level": m["level"], "field": m["field"], "issue": m.get("issue"),
                    "submitted": m["submitted"], "ocr": m["ocr"], "ocr_confidence": m["ocr_confidence"],
                    "decided_by": decided_by, "resolved": m["resolved"], "hint": m["hint"],
                    **({"math": m["math"]} if "math" in m else {}),
                })
            receipts.append({"submitted_index": r["submitted_index"], "ocr_index": r["ocr_index"],
                             "status": r["status"], "differences": differences})
        cases.append({"image": image_id, "status": result["status"], "receipts": receipts,
                      "unpaired": result["unpaired"], "file": result.get("file", [])})

    if str(path).lower().endswith(".txt"):
        lines = [f"UNMATCHED: {len(cases)} image(s)", "=" * 64]
        for n, c in enumerate(cases, start=1):
            lines.append(f"[{n}] image {c['image']} -> {c['status']}")
            for r in c["receipts"]:
                lines.append(f"    receipt submitted #{r['submitted_index']} / OCR #{r['ocr_index']}: {r['status']}")
                for d in r["differences"]:
                    where = d["field"] or d["issue"]
                    lines.append(f"      - {d['level']}.{where}: submitted {d['submitted']!r} vs OCR {d['ocr']!r}"
                                 f" (OCR confidence {d['ocr_confidence']}) [{d['decided_by']}] "
                                 f"{'resolved' if d['resolved'] else 'FLAGGED'}")
                    lines.append(f"        {d['hint']}")
            for u in c["unpaired"]:
                lines.append(f"    unpaired {u['side']} receipt #{u['index']}: {u['hint']}")
            for m in c["file"]:
                lines.append(f"    file grand_total: submitted {m['submitted']!r} vs OCR {m['ocr']!r} "
                             f"{'resolved' if m['resolved'] else 'FLAGGED'}")
                lines.append(f"      {m['hint']}")
            lines.append("")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
    else:
        Path(path).write_text(json.dumps(cases, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return cases
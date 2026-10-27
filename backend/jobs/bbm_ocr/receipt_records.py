"""
Between the database and the OCR pipeline, for the OCR worker (worker.py): the submitted items as receipts for
receipt_validation.validate_receipts, and an OCR reading plus its validation as the rows stored for the website
(ocr_reimbursement, ocr_bbm_receipt, ocr_difference). Plain functions, no database access.

For now a BBM receipt has exactly one product, so each submitted item is one receipt. The items carry no discount
and no total per receipt: a report's only file is checked against the report's grand total instead (what was paid).
"""

from datetime import date
from decimal import Decimal, InvalidOperation

# Validation field -> the column (and the field_name of a difference) it is stored as
COLUMNS = {
    "name": "product_name",
    "quantity": "volume_liter",
    "unit_price": "price_per_liter",
    "total_price": "total_price",
    "date": "date_of_expense",
    "discount": "discount",
    "total": "grand_total",
    "grand_total": "grand_total",
}

# Column -> (digits, decimals) of its numeric type in schema.sql: a reading that does not fit is stored as NULL
NUMERIC_COLUMNS = {
    "price_per_liter": (12, 2),
    "volume_liter": (10, 3),
    "total_price": (14, 2),
    "discount": (14, 2),
    "grand_total": (14, 2),
}
TEXT_LENGTHS = {"product_name": 255, "date_of_expense": 100}


# ---------------------------------------------------------------------------
# Submitted data -> validation input
# ---------------------------------------------------------------------------

def submitted_receipts(items):
    """The submitted items (bbm_receipt rows) as receipts for validate_receipts: one receipt with one product per
    item, in the same order. Left out: the price per liter (not sent: validate_receipts works it out from the total
    and the volume, as the database does, and compares that with the receipt's), and a discount or total per receipt
    (not sent: the grand total is checked instead)."""
    receipts = []
    for item in items:
        product = {
            "name": item["product_name"],
            "quantity": _float(item["volume_liter"]),
            "total_price": _float(item["total_price"]),
        }
        receipts.append({
            "date": _date_text(item["date_of_expense"]),
            "products": [{key: value for key, value in product.items() if value is not None}],
        })
    return receipts


# ---------------------------------------------------------------------------
# OCR reading + validation -> rows
# ---------------------------------------------------------------------------

def reading_rows(receipts, validation, items):
    """What to store for one file the OCR read.

    receipts    the OCR reading (receipts with products and confidences, as the OCR schema returns them)
    validation  validate_receipts(submitted_receipts(items), receipts, grand_total=...)
    items       the submitted items (bbm_receipt rows with their id), in the order given to submitted_receipts

    Returns {"result": {decision, grand_total, confidence_grand_total},
             "lines": [ocr_bbm_receipt columns, in reading order],
             "differences": [{line (index into lines, or None), item_row_id (or None), field_name, ocr_value,
                              submitted_value, description, likely_wrong, expected_value}]}
    likely_wrong and expected_value come from the arithmetic check (see _verdict).
    """
    lines, first_line, line_of = _lines(receipts)
    totals = [_number(receipt.get("total"), "grand_total") for receipt in receipts]
    confidences = [_confidence(_get(receipt, "confidence", "total")) for receipt in receipts]
    result = {
        "decision": validation["status"],
        "grand_total": _number(sum(totals), "grand_total") if receipts and None not in totals else None,
        "confidence_grand_total": min(confidences) if confidences and None not in confidences else None,
    }

    differences = []

    def add(field, ocr_value, submitted_value, description, line=None, item=None, math=None):
        column = COLUMNS.get(field, field)
        differences.append({
            "line": line,
            "item_row_id": item["id"] if item else None,
            "field_name": column,
            "ocr_value": _text(ocr_value),
            "submitted_value": _text(submitted_value),
            "description": description,
            **_verdict(math, column),
        })

    for receipt in validation["receipts"]:
        i, item = receipt["ocr_index"], items[receipt["submitted_index"]]
        for m in receipt["mismatches"]:
            if m.get("issue") == "missing_in_ocr":
                add("name", None, (m["submitted"] or {}).get("name"), m["hint"], item=item)
            elif m.get("issue") == "not_submitted":
                add("name", (m["ocr"] or {}).get("name"), None, m["hint"], line=line_of.get((i, m["product_index"])))
            elif m["level"] == "receipt":
                add(m["field"], m["ocr"], m["submitted"], m["hint"], line=first_line[i], item=item, math=m.get("math"))
            else:
                line = line_of.get((i, m["ocr_product_index"]), first_line[i])
                add(m["field"], m["ocr"], m["submitted"], m["hint"], line=line, item=item, math=m.get("math"))

    for u in validation["unpaired"]:
        if u["side"] == "submitted":
            item = items[u["index"]]
            add("name", None, item["product_name"], u["hint"], item=item)
        else:
            products = receipts[u["index"]].get("products") or [{}]
            add("name", products[0].get("name"), None, u["hint"], line=first_line[u["index"]])

    for m in validation.get("file", []):
        add("grand_total", m["ocr"], m["submitted"], m["hint"], math=m.get("math"))

    return {"result": result, "lines": lines, "differences": differences}


def _verdict(math, column):
    """likely_wrong and expected_value of a difference, from the arithmetic check of receipt_validation (its "math":
    which side fits the other numbers on the receipt, and the value they give). When exactly one side fits, the
    other side is likely wrong and expected_value is what the numbers of the side that fits give; else both None."""
    if not math or math["submitted_fits"] == math["ocr_fits"]:
        return {"likely_wrong": None, "expected_value": None}
    likely_wrong = "ocr" if math["submitted_fits"] else "submitted"
    implied = math["submitted_implied"] if likely_wrong == "ocr" else math["ocr_implied"]
    expected = _number(implied, column) if column in NUMERIC_COLUMNS else None
    return {"likely_wrong": likely_wrong, "expected_value": expected}


def _lines(receipts):
    """One ocr_bbm_receipt row per product line, receipt by receipt. The receipt's date is repeated on each of its
    lines and its discount kept on its first line only; a receipt the OCR found without products still gets a line
    (its date and discount). Also returns the first line of each receipt and {(receipt, product): line}."""
    lines, first_line, line_of = [], [], {}
    for i, receipt in enumerate(receipts):
        first_line.append(len(lines))
        for k, product in enumerate(receipt.get("products") or [{}]):
            line_of[(i, k)] = len(lines)
            lines.append({
                "product_name": _string(product.get("name"), "product_name"),
                "date_of_expense": _string(receipt.get("date"), "date_of_expense"),
                "price_per_liter": _number(product.get("unit_price"), "price_per_liter"),
                "volume_liter": _number(product.get("quantity"), "volume_liter"),
                "total_price": _number(product.get("total_price"), "total_price"),
                "discount": _number(receipt.get("discount"), "discount") if k == 0 else None,
                "confidence_product_name": _confidence(_get(product, "confidence", "name")),
                "confidence_date_of_expense": _confidence(_get(receipt, "confidence", "date")),
                "confidence_price_per_liter": _confidence(_get(product, "confidence", "unit_price")),
                "confidence_volume_liter": _confidence(_get(product, "confidence", "quantity")),
                "confidence_total_price": _confidence(_get(product, "confidence", "total_price")),
                "confidence_discount": _confidence(_get(receipt, "confidence", "discount")) if k == 0 else None,
            })
    return lines, first_line, line_of


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _get(container, *keys):
    for key in keys:
        container = container.get(key) if isinstance(container, dict) else None
    return container


def _float(value):
    """A submitted number as the OCR gives numbers: a whole number as an int (17200, not 17200.0)."""
    if value is None:
        return None
    return int(value) if value == int(value) else float(value)


def _date_text(value):
    return value.strftime("%d-%m-%Y") if isinstance(value, date) else value


def _number(value, column):
    """A number the OCR read as a Decimal that fits the column; None when it is not a number or does not fit."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    digits, decimals = NUMERIC_COLUMNS[column]
    try:
        number = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals))
    except InvalidOperation:
        return None
    return number if abs(number) < Decimal(10) ** (digits - decimals) else None


def _string(value, column):
    if value is None:
        return None
    return str(value)[:TEXT_LENGTHS[column]]


def _confidence(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        return None
    return Decimal(str(value)).quantize(Decimal("0.001"))


def _text(value):
    """A value as the text of a difference: numbers without trailing zeros (28.5, 646180), dates as DD-MM-YYYY."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float, Decimal)):
        return format(Decimal(str(value)).normalize(), "f")
    return _date_text(value) if isinstance(value, date) else str(value)

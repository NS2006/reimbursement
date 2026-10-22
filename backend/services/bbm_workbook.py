"""The Excel workbook of the BBM export: one sheet with every report the reviewer had in the list (its current
revision), one row per receipt, the submitted values next to what the OCR read:

    Report         code (links to the report page), employee, received, revision, status, decision and the totals
                   (the totals on the report's first row only, so the totals row counts each report once)
    Receipt        the item and its photo, then each field as submitted and as the OCR read it
    What differs   the fields that differ, or "Not on receipt" / "Not submitted"

Amber cells differ, orange values are ones the OCR was unsure of, and the rows of a report share a band.
"""

import re
from collections import defaultdict
from decimal import Decimal
from urllib.parse import quote

from openpyxl import Workbook

from backend.services.report_filter import MONTH_ZONE
from backend.services.xlsx_style import (
    DIFFERS_FILL,
    FMT,
    MUTED,
    NEGATIVE,
    POSITIVE,
    TEXT,
    WARNING,
    Column,
    Styled,
    column_range,
    excel_month,
    excel_time,
    key,
    table,
    title_block,
)

# Review status (what is left to do): label and text colour (the colours of the website's badges)
STATUSES = {
    "needs_review": ("Needs review", NEGATIVE),
    "processing": ("Processing", MUTED),
    "approved": ("Approved", POSITIVE),
    "rejected": ("Rejected", TEXT),
}

# The parts of a status a list can show, for the filter label ("Approved · Proceed"): how an approved report was
# approved, and why a report needs review
STATUS_PARTS = {
    "approved": {
        "matched": "Matched",
        "proceed": "Proceed",
        "reviewer": "By a reviewer",
    },
    "needs_review": {
        "differences": "Differences",
        "failed": "OCR couldn't read",
    },
}

# BBM fields as the website names them, in the order of the columns
FIELD_LABELS = {
    "product_name": "Product",
    "date_of_expense": "Date",
    "price_per_liter": "Price per liter",
    "volume_liter": "Volume",
    "kilometer": "Kilometer",
    "total_price": "Amount",
    "discount": "Discount",
    "grand_total": "Grand total",
}

# Read on the receipt and compared with the submitted item, each shown as a Submitted / OCR pair
COMPARED = ["product_name", "date_of_expense", "price_per_liter", "volume_liter", "total_price"]

# The OCR is unsure of a value below this confidence (the website and the OCR validation use the same line)
CONFIDENT = Decimal("0.9")

HEADER_ROW = 5  # rows 1-3: title, subtitle and colour key; row 4: the field over each Submitted / OCR pair

COLUMNS = [
    Column("Report", 12),
    Column("Employee", 22),
    Column("Employee no", 15),
    # The month only: the other system sends reports in batches (Darwinbox about once a week), so the day they
    # arrive is not when the employee submitted them. A report belongs to the month (WIB) it was received in.
    Column("Received", 16, FMT["month"]),
    Column("Revision", 11, FMT["count"], "center"),
    Column("Status", 16),
    Column("Decision", 34, wrap=True),
    Column("Submitted total", 20, FMT["idr"], "right"),
    Column("OCR total", 16, FMT["idr"], "right"),
    Column("Gap", 14, FMT["idr_or_dash"], "right"),
    Column("Receipt", 13),
    Column("Photo", 14),
    Column("Submitted", 19, wrap=True, group="Product"),
    Column("OCR", 22, wrap=True, group="Product"),
    Column("Submitted", 14, FMT["date"], group="Date"),
    Column("OCR", 14, wrap=True, group="Date"),
    Column("Submitted", 14, FMT["idr"], "right", group="Price per liter"),
    Column("OCR", 13, FMT["idr"], "right", group="Price per liter"),
    Column("Submitted", 14, FMT["number"], "right", group="Volume (L)"),
    Column("OCR", 12, FMT["number"], "right", group="Volume (L)"),
    Column("Submitted", 15, FMT["idr"], "right", group="Amount"),
    Column("OCR", 15, FMT["idr"], "right", group="Amount"),
    Column("Submitted", 14, FMT["count"], "right", group="Kilometer"),
    Column("OCR", 13, FMT["idr_or_dash"], "right", group="Discount"),
    Column("What differs", 24, wrap=True),
]
TOTAL_COLUMNS = (8, 9, 10)  # Submitted total, OCR total, Gap


def build_bbm_workbook(reports, info):
    """reports: from reimbursement_repository.find_current_revisions, each with its "ocr_status", "review_status" and
    "decision" (the reviewer's decision in force, or None). info: "period"
    ("October 2026", or None for every month), "filter" (label), "search", "exported_at", "zone" (the reviewer's time
    zone) and "website_url" (for the links; or None)."""
    rows, bands = [], []
    receipt_count = 0
    for number, report in enumerate(reports):
        report_rows, receipts = _report_rows(report, info)
        rows += report_rows
        bands += [number % 2 == 1] * len(report_rows)
        receipt_count += receipts

    workbook = Workbook()
    ws = workbook.active
    ws.title = "BBM reimbursements"
    # Column A (the report code) stays in view when scrolling sideways: the title starts in column B.
    title_block(ws, _title(info), _subtitle(info, len(reports), receipt_count), column=2)
    key(ws, 3, 2, [
        Styled("■", color="FFD24D"), Styled(" Submitted and OCR differ   ·   "),
        Styled("Orange", color=WARNING, bold=True), Styled(" OCR unsure: point at it to see how sure   ·   "),
        Styled("NULL", color=NEGATIVE, italic=True), Styled(" OCR could not read it"),
    ])
    first = HEADER_ROW + 1
    last = HEADER_ROW + len(rows)
    table(
        ws,
        COLUMNS,
        rows,
        HEADER_ROW,
        "No reports.",
        bands=bands,
        # SUBTOTAL(109) adds only the rows left visible by the filters.
        totals={1: "Total", **{column: f"=SUBTOTAL(109,{column_range(column, first, last)})" for column in TOTAL_COLUMNS}},
    )
    workbook.properties.title = " - ".join(_name_parts(info))
    workbook.properties.creator = "Reimbursement website"
    return workbook


def file_name(info):
    """e.g. "BBM reimbursements - October 2026 - Needs review - 19-10-2026 15.30.xlsx" (no ":" so Windows accepts it)."""
    return " - ".join([*_name_parts(info), f"{info['exported_at']:%d-%m-%Y %H.%M}"]) + ".xlsx"


def _name_parts(info):
    # "Approved · Proceed" becomes "Approved - Proceed": the plain file name has no "·"
    return ["BBM reimbursements", *([info["period"]] if info["period"] else []), info["filter"].replace(" · ", " - ")]


def _title(info):
    """The sheet title, e.g. "BBM reimbursements · October 2026": the month is what the file is about."""
    return f"BBM reimbursements · {info['period']}" if info["period"] else "BBM reimbursements"


def _subtitle(info, report_count, receipt_count):
    parts = [info["filter"]]
    if info["search"]:
        parts.append(f"search “{info['search']}”")
    parts.append(_count(report_count, "report"))
    parts.append(_count(receipt_count, "receipt"))
    parts.append(f"exported {info['exported_at']:%d-%m-%Y %H:%M}")
    return " · ".join(parts)


def _count(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


# ---------------------------------------------------------------------------
# The rows of one report
# ---------------------------------------------------------------------------

def _report_rows(report, info):
    """The rows of a report (at least one) and how many receipts they show."""
    revision = report["revision"]
    photos = revision["photos"]
    read = [photo for photo in photos if photo["ocr"]]
    differences = [difference for photo in read for difference in photo["ocr"]["differences"]]
    receipts = _pair(revision["items"], read, differences)

    # Where each difference is: on an item, on an OCR line, or on the whole report (the grand total)
    item_fields, line_fields, report_fields = defaultdict(set), defaultdict(set), set()
    for difference in differences:
        field, item_id, line_id = difference["field_name"], difference["item_row_id"], difference["ocr_line_id"]
        if field == "grand_total" or (item_id is None and line_id is None):
            report_fields.add(field)
        if item_id is not None and field != "grand_total":
            item_fields[item_id].add(field)
        if line_id is not None and field != "grand_total":
            line_fields[line_id].add(field)

    report_cells = _report_cells(report, read, info)
    if not receipts:
        return [[*report_cells, None, None, *[None] * 12, _what_differs(report_fields, note="No receipts")]], 0

    rows = []
    for index, (item, photo, line) in enumerate(receipts):
        fields = (item_fields[item["id"]] if item else set()) | (line_fields[line["id"]] if line else set())
        if line is None:
            note = "No photo" if not photos else _unread_note(photos) if len(read) < len(photos) else "Not on receipt"
        elif item is None:
            note = "Not submitted"
        else:
            note = None
        photo = photo or (photos[0] if len(photos) == 1 else None)
        rows.append([
            *(report_cells if index == 0 else _repeated(report_cells)),
            item["item_id"] if item else Styled("—", color=MUTED),
            Styled(photo["name"], link=_photo_link(photo, info["website_url"])) if photo else None,
            *_compared_cells(item, line, fields),
            _submitted(item, "kilometer", fields),
            _ocr(line, "discount", fields),
            _what_differs(fields | (report_fields if index == 0 else set()), note),
        ])
    return rows, len(receipts)


def _pair(items, read_photos, differences):
    """Each submitted item next to the receipt the OCR read for it: [(item or None, photo or None, line or None)],
    items by date then item id, then the receipts nobody submitted.

    The OCR job stores which item it compared with which receipt only where a value differs. A pair without a
    difference agrees on every value, so each remaining item goes with the remaining receipt that has the most
    values in common with it."""
    lines = [(photo, line) for photo in read_photos for line in photo["ocr"]["lines"]]
    line_by_id = {line["id"]: (photo, line) for photo, line in lines}
    paired, used = {}, set()
    for difference in differences:
        item_id, line_id = difference["item_row_id"], difference["ocr_line_id"]
        if item_id is not None and line_id in line_by_id and item_id not in paired and line_id not in used:
            paired[item_id] = line_id
            used.add(line_id)

    items = sorted(items, key=lambda item: (item["date_of_expense"], _natural(item["item_id"])))
    for item in items:
        if item["id"] in paired:
            continue
        shared = [(_shared(item, line), line["id"]) for _, line in lines if line["id"] not in used]
        best = max(shared, key=lambda candidate: candidate[0], default=(0, None))
        if best[0] > 0:
            paired[item["id"]] = best[1]
            used.add(best[1])

    receipts = [(item, *line_by_id.get(paired.get(item["id"]), (None, None))) for item in items]
    return receipts + [(None, photo, line) for photo, line in lines if line["id"] not in used]


def _shared(item, line):
    """How many values an item and a receipt line have in common."""
    same = sum(item[field] is not None and item[field] == line[field]
               for field in ("price_per_liter", "volume_liter", "total_price"))
    same += _text(item["product_name"]) == _text(line["product_name"]) != ""
    return same


def _text(value):
    return " ".join(str(value or "").split()).casefold()


def _natural(text):
    """"RB-2" before "RB-10"."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

def _report_cells(report, read, info):
    """Code, employee, employee no, received, revision, status, decision, submitted total, OCR total and gap."""
    revision = report["revision"]
    code = report["reimbursement_code"]
    link = f"{info['website_url']}/bbm/{quote(code, safe='')}" if info["website_url"] else None
    label, color = STATUSES[report["review_status"]]

    totals = [result["ocr"]["grand_total"] for result in read]
    if read and len(read) == len(revision["photos"]) and all(total is not None for total in totals):
        ocr_total = sum(totals)
        gap = ocr_total - revision["grand_total"]
        unsure = [photo for photo in read if _unsure(photo["ocr"]["confidence_grand_total"])]
        ocr_cell = Styled(ocr_total, color=WARNING if unsure else None, bold=bool(unsure), note=_total_note(read, unsure))
        gap_cell = Styled(gap, color=NEGATIVE if gap else MUTED, bold=bool(gap))
    elif len(read) < len(revision["photos"]):
        ocr_cell, gap_cell = Styled(_unread_note(revision["photos"]), color=MUTED, italic=True), None
    else:
        ocr_cell, gap_cell = _null(), None

    return [
        Styled(code, bold=True, link=link),
        report["employee_name"],
        report["employee_no"],
        excel_month(revision["received_at"], MONTH_ZONE),
        revision["revision_no"],
        Styled(label, color=color, bold=True),
        _decision(report, info),
        revision["grand_total"],
        ocr_cell,
        gap_cell,
    ]


def _unread_note(photos):
    """Why the OCR has no reading for every photo yet: it could not read one, or it is still reading."""
    return "OCR couldn't read" if any(photo["ocr_status"] == "failed" for photo in photos) else "Processing"


def _repeated(report_cells):
    """The report's cells on its next rows: greyed out, still there so filters and sorting keep the rows together;
    the totals only once, on the first row."""
    values = [cell.value if isinstance(cell, Styled) else cell for cell in report_cells]
    return [Styled(value, color=MUTED) for value in values[:7]] + [None, None, None]


def _decision(report, info):
    """Who decided and why ("Rejected by Reviewer One, 20-10-2026 09:12: <reason>"), or how the OCR approved it."""
    decision = report["decision"]
    if decision:
        verb = "Approved" if decision["decision"] == "approved" else "Rejected"
        moment = excel_time(decision["decided_at"], info["zone"])
        text = f"{verb} by {decision['user_name']}, {moment:%d-%m-%Y %H:%M}"
        return f"{text}: {decision['reason']}" if decision["reason"] else text
    if report["review_status"] == "approved":
        return Styled("By the OCR: the receipt matches" if report["ocr_status"] == "matched"
                      else "By the OCR: the differences are OCR misreads", color=MUTED)
    if report["revision"]["previously_rejected"]:
        return Styled("Sent again after a rejection", color=MUTED)
    return None


def _compared_cells(item, line, fields):
    cells = []
    for field in COMPARED:
        cells.append(_submitted(item, field, fields))
        cells.append(_ocr(line, field, fields))
    return cells


def _submitted(item, field, fields):
    if item is None or item[field] is None:
        return None
    return Styled(item[field], fill=DIFFERS_FILL if field in fields else None)


def _ocr(line, field, fields):
    """What the OCR read: NULL when it could not read a value it looked for, orange when it was unsure."""
    if line is None:
        return None
    value, confidence = line[field], line["confidence"].get(field)
    differs = field in fields
    if value is None:
        cell = _null() if confidence is not None or differs else Styled(None)
        if _unsure(confidence):
            cell.note = f"OCR confidence: {_percent(confidence)}\nThe OCR could not read this.\nCheck the photo."
    else:
        # The date the OCR read, DD-MM-YYYY (it can be misread, so it is text, not a date)
        cell = Styled(str(value) if field == "date_of_expense" else value)
        if _unsure(confidence):
            cell.color, cell.bold = WARNING, True
            cell.note = _unsure_note(confidence)
    if differs:
        cell.fill = DIFFERS_FILL
    return cell


def _unsure(confidence):
    return confidence is not None and confidence < CONFIDENT


def _percent(confidence):
    return f"{round(confidence * 100)}%"


def _unsure_note(confidence):
    """The note on a value the OCR was unsure of: how sure it was and what to do."""
    return f"OCR confidence: {_percent(confidence)}\nBelow 90%, so it may be misread.\nCheck the photo."


def _total_note(read, unsure):
    """The note on an OCR total the OCR was unsure of (with several photos: how sure it was of each one's total)."""
    if not unsure:
        return None
    if len(read) == 1:
        return _unsure_note(unsure[0]["ocr"]["confidence_grand_total"])
    lines = [f"{photo['name']}: {_percent(photo['ocr']['confidence_grand_total'])}" for photo in unsure]
    return "\n".join(["OCR confidence of the total:", *lines, "Below 90%, so it may be misread.", "Check the photos."])


def _null():
    return Styled("NULL", color=NEGATIVE, italic=True)


def _what_differs(fields, note=None):
    """e.g. "Volume, Amount"; a note ("Not on receipt") first; empty when nothing differs."""
    labels = [label for field, label in FIELD_LABELS.items() if field in fields]
    labels += sorted(field.replace("_", " ").capitalize() for field in fields if field not in FIELD_LABELS)
    if note:
        return Styled(", ".join([note, *labels]), italic=True, color=MUTED if note == "Not read yet" else None)
    return ", ".join(labels) or None


def _photo_link(photo, website_url):
    """A link that opens the photo through the website (the backend serves it from our file storage; the link the
    other system sent it with has expired)."""
    return f"{website_url}/api/attachments/{photo['id']}/file" if website_url else None

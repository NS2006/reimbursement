"""The Excel workbook of the BBM export, in Indonesian (the reviewers' language), with three sheets:

"Perlu direview" and "Ditolak": every report of the list's month and search that needs a reviewer, and every rejected
one, whatever the list's status filter; one row per problem (a possible double claim, a file the OCR couldn't read, a
difference; not the differences the receipt's own numbers prove to be OCR misreads), with a hint of which value is
right. "Perlu direview" adds the money at stake and what to do; "Ditolak" who rejected it, when and why, and the
report resubmitting it.

"Sesuai filter": every report the reviewer had in the list, one row per receipt, the submitted values next to what
the OCR read:

    Report         code (links to the report page), employee, received, status, decision and the totals
                   (the totals on the report's first row only, so the totals row counts each report once)
    Receipt        the item and its photo, then each field as submitted and as the OCR read it (the price per liter is
                   not submitted: the computed one, amount / volume)
    What differs   the fields that differ, or "Tidak ada di struk" / "Tidak disubmit"

Amber cells differ, orange values are ones the OCR was unsure of, and the rows of a report share a band.
"""

import math
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from openpyxl import Workbook

from backend.jobs.bbm_ocr.product_labels import matches_fuel_type
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
    link_text,
    table,
    title_block,
)

# Review status (what is left to do): label and text colour (the colours of the website's badges)
STATUSES = {
    "needs_review": ("Perlu direview", NEGATIVE),
    "processing": ("Diproses", MUTED),
    "approved": ("Disetujui", POSITIVE),
    "rejected": ("Ditolak", TEXT),
}

# The parts of a status a list can show, for the filter label ("Disetujui · Proceed"): how an approved report was
# approved, and why a report needs review
STATUS_PARTS = {
    "approved": {
        "matched": "Sesuai",
        "proceed": "Proceed",
        "reviewer": "Oleh reviewer",
    },
    "needs_review": {
        "duplicate": "Kemungkinan klaim ganda",
        "differences": "Perbedaan",
        "failed": "OCR gagal membaca",
    },
}

# BBM fields as the website names them, in the order of the columns
FIELD_LABELS = {
    "product_name": "Produk",
    "date_of_expense": "Tanggal",
    "price_per_liter": "Harga per liter",
    "volume_liter": "Volume",
    "kilometer": "Kilometer",
    "total_price": "Jumlah",
    "discount": "Diskon",
    "grand_total": "Grand total",
}

# Read on the receipt and shown next to the submitted item, each as a Submitted / OCR pair (the price per liter as
# Computed / OCR: not submitted, the amount divided by the volume)
COMPARED = ["product_name", "date_of_expense", "price_per_liter", "volume_liter", "total_price"]

# The OCR is unsure of a value below this confidence (the website and the OCR validation use the same line)
CONFIDENT = Decimal("0.9")

HEADER_ROW = 5  # rows 1-3: title, subtitle and colour key; row 4: the field over each Submitted / OCR pair

COLUMNS = [
    Column("Laporan", 12),
    Column("Karyawan", 22),
    Column("No. karyawan", 15),
    # The month only: the other system sends reports in batches (Darwinbox about once a week), so the day they
    # arrive is not when the employee submitted them. A report belongs to the month (WIB) it was received in.
    Column("Diterima", 18, FMT["month_id"]),  # wide enough for "September 2026"
    Column("Status", 16),
    Column("Keputusan", 34, wrap=True),
    Column("Total disubmit", 20, FMT["idr"], "right"),
    Column("Total OCR", 16, FMT["idr"], "right"),
    Column("Selisih", 14, FMT["idr_or_dash"], "right"),
    Column("Item", 13),
    Column("Foto", 14),
    Column("Disubmit", 19, wrap=True, group="Produk"),
    Column("OCR", 22, wrap=True, group="Produk"),
    Column("Disubmit", 14, FMT["date"], group="Tanggal"),
    Column("OCR", 14, wrap=True, group="Tanggal"),
    Column("Dihitung", 14, FMT["idr"], "right", group="Harga per liter"),
    Column("OCR", 13, FMT["idr"], "right", group="Harga per liter"),
    Column("Disubmit", 14, FMT["number"], "right", group="Volume (L)"),
    Column("OCR", 12, FMT["number"], "right", group="Volume (L)"),
    Column("Disubmit", 15, FMT["idr"], "right", group="Jumlah"),
    Column("OCR", 15, FMT["idr"], "right", group="Jumlah"),
    Column("Disubmit", 14, FMT["count"], "right", group="Kilometer"),
    Column("OCR", 13, FMT["idr_or_dash"], "right", group="Diskon"),
    Column("Yang berbeda", 24, wrap=True),
]
TOTAL_COLUMNS = (7, 8, 9)  # Submitted total, OCR total, Gap


def build_bbm_workbook(reports, needs_review, rejected, info):
    """reports: the list, from reimbursement_repository.find_reports, each with its "ocr_status", "review_status" and
    "decision" (the reviewer's decision in force, or None); needs_review and rejected: every report of the list's month
    and search with that status, the same way and each also with "same_receipt"
    (reimbursement_service.add_same_receipts). info: "period" ("Oktober 2026", or None for every month), "filter"
    (label), "search", "exported_at", "zone" (the reviewer's time zone) and "website_url" (for the links; or None)."""
    rows, bands = [], []
    receipt_count = 0
    for number, report in enumerate(reports):
        report_rows, receipts = _report_rows(report, info)
        rows += report_rows
        bands += [number % 2 == 1] * len(report_rows)
        receipt_count += receipts

    workbook = Workbook()
    ws = workbook.active
    ws.title = "Sesuai filter"
    # Column A (the report code) stays in view when scrolling sideways: the title starts in column B.
    title_block(ws, _title("Reimbursement BBM", info), _subtitle(info, len(reports), receipt_count), column=2)
    key(ws, 3, 2, [
        Styled("■", color="FFD24D"), Styled(" Disubmit dan OCR berbeda   ·   "),
        Styled("Oranye", color=WARNING, bold=True), Styled(" OCR kurang yakin: arahkan kursor untuk melihat seberapa yakin   ·   "),
        Styled("NULL", color=NEGATIVE, italic=True), Styled(" OCR gagal membacanya"),
    ])
    first = HEADER_ROW + 1
    last = HEADER_ROW + len(rows)
    table(
        ws,
        COLUMNS,
        rows,
        HEADER_ROW,
        "Tidak ada laporan.",
        bands=bands,
        # SUBTOTAL(109) adds only the rows left visible by the filters.
        totals={1: "Total", **{column: f"=SUBTOTAL(109,{column_range(column, first, last)})" for column in TOTAL_COLUMNS}},
    )
    _needs_review_sheet(workbook.create_sheet("Perlu direview", 0), needs_review, info)
    _rejected_sheet(workbook.create_sheet("Ditolak", 1), rejected, info)
    # The file opens on the first sheet; only it selected (two selected tabs make Excel group the sheets)
    workbook.active = 0
    for index, sheet in enumerate(workbook.worksheets):
        sheet.sheet_view.tabSelected = index == 0
    workbook.properties.title = " - ".join(_name_parts(info))
    workbook.properties.creator = "Website reimbursement"
    return workbook


def file_name(info):
    """e.g. "Reimbursement BBM - Oktober 2026 - Perlu direview - 19-10-2026 15.30.xlsx" (no ":" so Windows accepts
    it)."""
    return " - ".join([*_name_parts(info), f"{info['exported_at']:%d-%m-%Y %H.%M}"]) + ".xlsx"


def _name_parts(info):
    # "Disetujui · Proceed" becomes "Disetujui - Proceed": the plain file name has no "·"
    return ["Reimbursement BBM", *([info["period"]] if info["period"] else []), info["filter"].replace(" · ", " - ")]


def _title(title, info):
    """A sheet's title with the month, e.g. "Reimbursement BBM · Oktober 2026": the month is what the file is about."""
    return f"{title} · {info['period']}" if info["period"] else title


def _subtitle(info, report_count, receipt_count):
    parts = [info["filter"]]
    if info["search"]:
        parts.append(f"pencarian “{info['search']}”")
    parts.append(f"{report_count} laporan")
    parts.append(f"{receipt_count} struk")
    parts.append(f"diekspor {info['exported_at']:%d-%m-%Y %H:%M}")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# The rows of one report
# ---------------------------------------------------------------------------

def _report_rows(report, info):
    """The rows of a report (at least one) and how many receipts they show."""
    photos = report["photos"]
    read = [photo for photo in photos if photo["ocr"]]
    differences = [difference for photo in read for difference in photo["ocr"]["differences"]]
    receipts = _pair(report["items"], read, differences)

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

    report_cells = _report_cells(report, read, info, total_differs="grand_total" in report_fields)
    if not receipts:
        return [[*report_cells, None, None, *[None] * 12, _what_differs(report_fields, note="Tidak ada struk")]], 0

    rows = []
    for index, (item, photo, line) in enumerate(receipts):
        fields = (item_fields[item["id"]] if item else set()) | (line_fields[line["id"]] if line else set())
        if line is None:
            note = "Tidak ada foto" if not photos else _unread_note(photos) if len(read) < len(photos) else "Tidak ada di struk"
        elif item is None:
            note = "Tidak disubmit"
        else:
            note = None
        photo = photo or _own_photo(item, photos)
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
    difference agrees on every value, so each remaining item goes with the remaining receipt of its own files that
    has the most values in common with it."""
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
        shared = [(_shared(item, line), line["id"]) for photo, line in lines
                  if line["id"] not in used and photo["id"] in item["photo_ids"]]
        best = max(shared, key=lambda candidate: candidate[0], default=(0, None))
        if best[0] > 0:
            paired[item["id"]] = best[1]
            used.add(best[1])

    receipts = [(item, *line_by_id.get(paired.get(item["id"]), (None, None))) for item in items]
    return receipts + [(None, photo, line) for photo, line in lines if line["id"] not in used]


def _shared(item, line):
    """How many values an item and a receipt line have in common."""
    same = sum(item[field] is not None and item[field] == line[field] for field in ("volume_liter", "total_price"))
    same += line["product_name"] is not None and matches_fuel_type(line["product_name"], item["product_name"])
    return same


def _own_photo(item, photos):
    """The photo of an item without a receipt line: its only file (or the report's only one), else None."""
    if item and len(item["photo_ids"]) == 1:
        return next((photo for photo in photos if photo["id"] == item["photo_ids"][0]), None)
    return photos[0] if len(photos) == 1 else None


def _natural(text):
    """"EREP_2" before "EREP_10"."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

def _report_cells(report, read, info, total_differs=False):
    """Code, employee, employee no, received, status, decision, submitted total, OCR total and gap. total_differs:
    the OCR found the grand total differs, so both totals are marked like the other values that differ."""
    code = report["reimbursement_code"]
    link = f"{info['website_url']}/bbm/{quote(code, safe='')}" if info["website_url"] else None
    label, color = STATUSES[report["review_status"]]

    totals = [result["ocr"]["grand_total"] for result in read]
    if read and len(read) == len(report["photos"]) and all(total is not None for total in totals):
        ocr_total = sum(totals)
        gap = ocr_total - report["grand_total"]
        unsure = [photo for photo in read if _unsure(photo["ocr"]["confidence_grand_total"])]
        ocr_cell = Styled(ocr_total, color=WARNING if unsure else None, bold=bool(unsure), note=_total_note(read, unsure))
        gap_cell = Styled(gap, color=NEGATIVE if gap else MUTED, bold=bool(gap))
    elif len(read) < len(report["photos"]):
        ocr_cell, gap_cell = Styled(_unread_note(report["photos"]), color=MUTED, italic=True), None
    else:
        ocr_cell, gap_cell = _null(), None
    fill = DIFFERS_FILL if total_differs else None
    ocr_cell.fill = fill

    return [
        Styled(code, bold=True, link=link),
        report["employee_name"],
        report["employee_no"],
        excel_month(report["received_at"], MONTH_ZONE),
        Styled(label, color=color, bold=True),
        _decision(report, info),
        Styled(report["grand_total"], fill=fill),
        ocr_cell,
        gap_cell,
    ]


def _unread_note(photos):
    """Why the OCR has no reading for every photo yet: it could not read one, or it is still reading."""
    return "OCR gagal membaca" if any(photo["ocr_status"] == "failed" for photo in photos) else "Diproses"


def _repeated(report_cells):
    """The report's cells on its next rows: greyed out, still there so filters and sorting keep the rows together;
    the totals only once, on the first row."""
    values = [cell.value if isinstance(cell, Styled) else cell for cell in report_cells]
    return [Styled(value, color=MUTED) for value in values[:6]] + [None, None, None]


def _decision(report, info):
    """Who decided and why ("Ditolak oleh Reviewer One, 20-10-2026 09:12: <reason>"), or how the OCR approved it."""
    decision = report["decision"]
    if decision:
        verb = "Disetujui" if decision["decision"] == "approved" else "Ditolak"
        moment = excel_time(decision["decided_at"], info["zone"])
        text = f"{verb} oleh {decision['user_name']}, {moment:%d-%m-%Y %H:%M}"
        return f"{text}: {decision['reason']}" if decision["reason"] else text
    if report["review_status"] == "approved":
        return Styled("Oleh OCR: struk sesuai" if report["ocr_status"] == "matched"
                      else "Oleh OCR: perbedaannya hanya salah baca OCR", color=MUTED)
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
            cell.note = f"Keyakinan OCR: {_percent(confidence)}\nOCR gagal membaca ini.\nCek fotonya."
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
    return f"Keyakinan OCR: {_percent(confidence)}\nDi bawah 90%, jadi mungkin salah baca.\nCek fotonya."


def _total_note(read, unsure):
    """The note on an OCR total the OCR was unsure of (with several photos: how sure it was of each one's total)."""
    if not unsure:
        return None
    if len(read) == 1:
        return _unsure_note(unsure[0]["ocr"]["confidence_grand_total"])
    lines = [f"{photo['name']}: {_percent(photo['ocr']['confidence_grand_total'])}" for photo in unsure]
    return "\n".join(["Keyakinan OCR atas totalnya:", *lines, "Di bawah 90%, jadi mungkin salah baca.", "Cek fotonya."])


def _null():
    return Styled("NULL", color=NEGATIVE, italic=True)


def _what_differs(fields, note=None):
    """e.g. "Volume, Jumlah"; a note ("Tidak ada di struk") first; empty when nothing differs."""
    labels = [label for field, label in FIELD_LABELS.items() if field in fields]
    labels += sorted(field.replace("_", " ").capitalize() for field in fields if field not in FIELD_LABELS)
    if note:
        return Styled(", ".join([note, *labels]), italic=True, color=MUTED if note == "Diproses" else None)
    return ", ".join(labels) or None


def _photo_link(photo, website_url):
    """A link that opens the photo through the website (the backend serves it from our file storage; the link the
    other system sent it with has expired)."""
    return f"{website_url}/api/attachments/{photo['id']}/file" if website_url else None


def _report_link(code, website_url):
    return f"{website_url}/bbm/{quote(code, safe='')}" if website_url else None


# ---------------------------------------------------------------------------
# Sheets "Perlu direview" and "Ditolak": what a reviewer has to look at, one row per problem
# ---------------------------------------------------------------------------

PROBLEM_HEADER_ROW = 5  # rows 1-3: title, subtitle and key

# The first columns of both sheets: the report, then the problem
PROBLEM_COLUMNS = [
    Column("Laporan", 13),
    Column("Karyawan", 22),
    Column("No. karyawan", 14),
    Column("Masalah", 24, wrap=True),
    Column("Item", 13, wrap=True),
    Column("Bagian", 15),
    Column("Disubmit", 17, wrap=True),
    Column("Di struk (OCR)", 17, wrap=True),
    Column("Petunjuk", 50, wrap=True),
    Column("Foto", 14),
]
NEEDS_REVIEW_COLUMNS = [
    *PROBLEM_COLUMNS,
    Column("Nilai berisiko", 17, FMT["idr_or_dash"], "right"),
    Column("Yang perlu dilakukan", 40, wrap=True),
]
REJECTED_COLUMNS = [
    *PROBLEM_COLUMNS,
    Column("Total disubmit", 17, FMT["idr"], "right"),
    Column("Ditolak oleh", 20),
    # "27-10-2026 09:57" in Segoe UI with the cell's indent; narrower, Excel shows ####
    Column("Tanggal ditolak", 21, FMT["datetime"]),
    Column("Alasan", 44, wrap=True),
    Column("Laporan pengganti", 24, wrap=True),
]
REPORT_COLUMNS = 3  # Laporan .. No. karyawan: on every row of a report, greyed after the first
MONEY_COLUMN = len(PROBLEM_COLUMNS) + 1  # Nilai berisiko / Total disubmit

MONEY_FIELDS = {"total_price", "grand_total", "price_per_liter", "discount"}
NUMBER_FIELDS = MONEY_FIELDS | {"volume_liter", "kilometer"}

# Why the OCR could not read a file (reimbursement_service.failure_reason): what it means and what to do, as the
# website says it
FAILURES = {
    "file_missing": ("File struk tidak ada di penyimpanan, jadi OCR dan reviewer tidak bisa membukanya.",
                     "Minta file-nya disubmit ulang, misalnya dengan menolak laporan ini."),
    "storage_unavailable": ("Penyimpanan file tidak bisa dihubungi saat OCR mencoba membacanya.",
                            "Coba Ulangi OCR di website beberapa saat lagi."),
    "pdf_too_large": ("PDF-nya terlalu besar untuk OCR.", "Cocokkan file dengan data yang disubmit secara manual."),
    "pdf_too_many_pages": ("PDF-nya terlalu banyak halaman untuk OCR.",
                           "Cocokkan file dengan data yang disubmit secara manual."),
    "timed_out": ("OCR terlalu lama membaca file ini, jadi dihentikan.",
                  "Coba Ulangi OCR di website. Jika tetap gagal, cocokkan file dengan data yang disubmit secara manual."),
    "unreadable": ("OCR tidak mendapat hasil yang bisa dipakai dari file ini (misalnya foto buram, atau bukan struk).",
                   "Coba Ulangi OCR di website. Jika tetap gagal, cocokkan file dengan data yang disubmit secara manual."),
    "ocr_unavailable": ("Layanan OCR sedang tidak bisa berjalan.",
                        "Coba Ulangi OCR di website nanti. Jika tetap gagal, hubungi admin."),
    "other": ("Terjadi kesalahan saat OCR membaca file ini.",
              "Coba Ulangi OCR di website nanti. Jika tetap gagal, hubungi admin."),
}
CHECK_WHICH = "Periksa struk untuk melihat mana yang benar."


def _needs_review_sheet(ws, reports, info):
    """Every report needing review, the most money at stake first (an unknown amount last), a row per problem with
    what to do."""
    at_stake = {report["reimbursement_code"]: _at_stake(report) for report in reports}
    reports = sorted(reports, key=lambda report: (at_stake[report["reimbursement_code"]] is None,
                                                  -(at_stake[report["reimbursement_code"]] or 0),
                                                  _natural(report["reimbursement_code"])))
    rows, bands = [], []
    for number, report in enumerate(reports):
        stake = at_stake[report["reimbursement_code"]]
        report_rows = [
            [*cells, (stake if stake is not None else Styled("?", color=MUTED, bold=True)) if index == 0 else None,
             _linked(problem.get("todo"), problem, info)]
            for index, (cells, problem) in enumerate(_problem_rows(report, info))
        ]
        rows += report_rows
        bands += [number % 2 == 1] * len(report_rows)

    known = sum(stake for stake in at_stake.values() if stake is not None)
    _problem_table(ws, "Perlu direview", info, f"{len(reports)} laporan · {_money_text(known)} berisiko", [
        Styled("Nilai berisiko", bold=True),
        Styled(": total disubmit dikurangi total di struk; untuk kemungkinan klaim ganda, seluruh klaim   ·   "),
        Styled("?", bold=True), Styled(" belum bisa dihitung   ·   "),
        Styled("Perbedaan yang hanya salah baca OCR tidak ditampilkan di sini"),
    ], NEEDS_REVIEW_COLUMNS, rows, bands, "Tidak ada laporan yang perlu direview.")


def _rejected_sheet(ws, reports, info):
    """Every rejected report, newest decision first, a row per problem the system found, with who rejected it, when
    and why, and the report resubmitting it."""
    reports = sorted(reports, key=lambda report: report["decision"]["decided_at"], reverse=True)
    rows, bands = [], []
    for number, report in enumerate(reports):
        decision = report["decision"]
        decided = [decision["user_name"], excel_time(decision["decided_at"], info["zone"]), decision["reason"]]
        replacement = _replacements(report, info)
        report_rows = [
            [*cells, report["grand_total"] if index == 0 else None,
             *(decided if index == 0 else [Styled(value, color=MUTED, fmt=FMT["datetime"]) for value in decided]),
             replacement if index == 0 else None]
            for index, (cells, _) in enumerate(_problem_rows(report, info))
        ]
        rows += report_rows
        bands += [number % 2 == 1] * len(report_rows)

    total = sum(report["grand_total"] for report in reports)
    _problem_table(ws, "Ditolak", info, f"{len(reports)} laporan · {_money_text(total)} disubmit", [
        Styled("Laporan pengganti", bold=True),
        Styled(": laporan karyawan yang sama, diterima kemudian, yang mengklaim struk yang sama   ·   "),
        Styled("Perbedaan yang hanya salah baca OCR tidak ditampilkan di sini"),
    ], REJECTED_COLUMNS, rows, bands, "Tidak ada laporan yang ditolak.")


def _problem_table(ws, title, info, counts, key_parts, columns, rows, bands, empty_text):
    """Title, subtitle, key and the table of a problem sheet, with the money column added up in the totals row."""
    parts = [*([f"pencarian “{info['search']}”"] if info["search"] else []), counts,
             f"diekspor {info['exported_at']:%d-%m-%Y %H:%M}"]
    title_block(ws, _title(title, info), " · ".join(parts), column=2)
    key(ws, 3, 2, key_parts)
    first = PROBLEM_HEADER_ROW + 1
    last = PROBLEM_HEADER_ROW + len(rows)
    table(ws, columns, rows, PROBLEM_HEADER_ROW, empty_text, bands=bands,
          totals={1: "Total", MONEY_COLUMN: f"=SUBTOTAL(109,{column_range(MONEY_COLUMN, first, last)})"})


def _at_stake(report):
    """The money a reviewer decides on: the whole claim for a possible double claim, else what was submitted above
    the receipts' total (0 when not above); None when it can't be told yet (a file not read)."""
    if any(entry["kind"] == "double_claim" for entry in report["same_receipt"]):
        return report["grand_total"]
    read = [photo for photo in report["photos"] if photo["ocr"]]
    totals = [photo["ocr"]["grand_total"] for photo in read]
    if not read or len(read) < len(report["photos"]) or any(total is None for total in totals):
        return None
    return max(report["grand_total"] - sum(totals), 0)


def _problem_rows(report, info):
    """[(cells, problem)] of one report, the cells of PROBLEM_COLUMNS: a row per problem, or one row saying the system
    found none. The report's columns are greyed after its first row (still there, so filters keep the context)."""
    problems = _problems(report)
    if not problems:
        problems = [{
            "problem": Styled("—", color=MUTED),
            "hint": "Tidak ada masalah yang terdeteksi OCR." if report["review_status"] == "rejected"
            else "Periksa file struk dan data yang disubmit.",
            "todo": "Cocokkan file struk dengan item yang disubmit.",
        }]
    code = report["reimbursement_code"]
    lead = [Styled(code, bold=True, link=_report_link(code, info["website_url"])), report["employee_name"],
            report["employee_no"]]
    rows = []
    for index, problem in enumerate(problems):
        photo = problem.get("photo")
        rows.append(([
            *(lead if index == 0 else [Styled(_plain(cell), color=MUTED) for cell in lead]),
            problem["problem"],
            problem.get("item") or Styled("—", color=MUTED),
            problem.get("field") or Styled("—", color=MUTED),
            problem.get("submitted"),
            problem.get("receipt"),
            _linked(problem.get("hint"), problem, info),
            Styled(photo["name"], link=_photo_link(photo, info["website_url"])) if photo else None,
        ], problem))
    return rows


def _plain(cell):
    return cell.value if isinstance(cell, Styled) else cell


def _replacements(report, info):
    """The same employee's later reports resubmitting this rejected one, with their status; or "Belum ada"."""
    later = [entry for entry in report["same_receipt"] if entry["kind"] == "resubmitted"]
    if not later:
        return Styled("Belum ada", color=MUTED, italic=True)
    text = "\n".join(f"{entry['reimbursement_code']} · {STATUSES[entry['review_status']][0]}" for entry in later)
    # A cell holds one link: to the first of them (nearly always the only one), the code that looks like a link
    first = later[0]["reimbursement_code"]
    return Styled(link_text(text, first), link=_report_link(first, info["website_url"]))


def _linked(text, problem, info):
    """A problem's text that names another report (a possible double claim) as a link to that report's page, only
    the report's code looking like a link."""
    other = problem.get("other_code")
    return Styled(link_text(text, other), link=_report_link(other, info["website_url"])) if text and other else text


def _problems(report):
    """Every problem of a report, as {problem, item, field, submitted, receipt, hint, photo, todo}: the earlier
    reports claiming the same receipt, the files the OCR couldn't read, then the differences (but not the ones the
    receipt's own numbers prove to be OCR misreads)."""
    items = {item["id"]: item for item in report["items"]}
    photos_by_name = {photo["name"]: photo for photo in report["photos"]}
    problems = []

    for entry in report["same_receipt"]:
        if entry["kind"] != "double_claim":
            continue
        photo = photos_by_name.get(entry["file_name"]) if entry["file_name"] else None
        how = f"Foto yang sama ({entry['file_name']})" if entry["file_name"] else "Tanggal, jumlah, dan volume yang sama"
        problems.append({
            "problem": Styled("Kemungkinan klaim ganda", color=NEGATIVE, bold=True),
            "item": _item_ids(photo, items) if photo else None,
            "hint": f"{how} sudah diklaim di {entry['reimbursement_code']} ({entry['employee_name']}, "
                    f"{_state_of(entry)}).",
            "photo": photo,
            "other_code": entry["reimbursement_code"],
            "todo": f"Bandingkan struknya dengan {entry['reimbursement_code']}: tolak jika struknya sama, setujui jika "
                    "ternyata berbeda.",
        })

    for photo in report["photos"]:
        if photo["ocr_status"] == "failed":
            text, todo = FAILURES.get(photo["ocr_error_reason"] or "other", FAILURES["other"])
            problems.append({"problem": "OCR gagal membaca", "item": _item_ids(photo, items), "hint": text,
                             "photo": photo, "todo": todo})

    for photo in report["photos"]:
        if not photo["ocr"]:
            continue
        lines = {line["id"]: line for line in photo["ocr"]["lines"]}
        for difference in photo["ocr"]["differences"]:
            if difference["likely_wrong"] == "ocr":
                continue
            problem = _difference_problem(difference, items.get(difference["item_row_id"]),
                                          lines.get(difference["ocr_line_id"]), photo)
            problems.append({**problem, "photo": photo})
    return problems


def _item_ids(photo, items):
    """The item ids a file is attached to, e.g. "EXP_10501, EXP_10502"."""
    ids = sorted((items[row_id]["item_id"] for row_id in photo["item_ids"] if row_id in items), key=_natural)
    return ", ".join(ids) or None


def _state_of(entry):
    """Where the other report claiming the receipt is: "disetujui oleh Reviewer One, 05-10-2026", "perlu direview"."""
    decision = entry["decision"]
    if decision:
        verb = "disetujui" if decision["decision"] == "approved" else "ditolak"
        return f"{verb} oleh {decision['user_name']}, {decision['decided_at']:%d-%m-%Y}"
    if entry["review_status"] == "approved":
        return "disetujui OCR"
    return STATUSES[entry["review_status"]][0].lower()


def _difference_problem(difference, item, line, photo):
    """One difference as a problem: a receipt on one side only, or a field whose values differ, with a hint of which
    value is right (as the website's report page says it)."""
    field = difference["field_name"]
    submitted, read, likely = difference["submitted_value"], difference["ocr_value"], difference["likely_wrong"]
    item_id = item["item_id"] if item else None

    if field == "product_name" and read is None and difference["ocr_line_id"] is None:
        return {
            "problem": "Tidak ada di struk", "item": item_id,
            "submitted": Styled(item["total_price"], fmt=FMT["idr"]) if item else submitted,
            "receipt": Styled("Tidak ditemukan", color=MUTED, italic=True),
            "hint": "OCR tidak menemukan struk untuk item ini di file. Periksa apakah item ini ada di file.",
            "todo": "Periksa apakah item ini ada di file struk.",
        }
    if field == "product_name" and submitted is None:
        amount = line["total_price"] if line else None
        return {
            "problem": "Struk tidak disubmit",
            "submitted": Styled("Tidak disubmit", color=MUTED, italic=True),
            "receipt": Styled(amount, fmt=FMT["idr"]) if amount is not None else read,
            "hint": "File berisi struk yang tidak disubmit (" + (read or "produk tidak terbaca") + ").",
            "todo": "Periksa apakah struk ini termasuk dalam laporan ini.",
        }

    slip = _slip(field, submitted, read)
    confidence = (photo["ocr"]["confidence_grand_total"] if field == "grand_total"
                  else line["confidence"].get(field) if line else None)
    unsure = (f"OCR hanya {_percent(confidence)} yakin membacanya dengan benar." if _unsure(confidence) else None)
    if field == "price_per_liter":
        computed = (f"Harga per liter yang disubmit dihitung dari {_shown('total_price', item['total_price'])} ÷ "
                    f"{_shown('volume_liter', item['volume_liter'])} L." if item else None)
        hint = _sentences(computed, "Bisa jadi OCR salah membaca harganya, atau jumlah atau volume di struk telah "
                                    "diubah.", unsure)
        todo = "Periksa harga per liter, jumlah, dan volume di struk."
    elif likely == "submitted":
        hint = _sentences(f"Kemungkinan OCR benar, karena {_because(field, difference, line, item)}.",
                          f"{slip}: kemungkinan salah ketik saat disubmit." if slip else None)
        todo = "Cek foto struk; tolak jika data yang disubmit memang salah."
    elif read is None:
        hint = "OCR gagal membaca nilai ini. Periksa di struk apakah nilainya sesuai dengan nilai yang disubmit."
        todo = "Periksa nilainya di struk."
    elif field == "grand_total" and _same_number(submitted, read):
        hint = ("Totalnya sama dengan jumlah yang diklaim, tetapi angka lainnya (jumlah, diskon, volume × harga per "
                "liter) tidak menghasilkan total itu. Total mungkin telah diubah atau salah baca.")
        todo = "Periksa struk."
    else:
        hint = _sentences(f"{slip}." if slip else None, unsure) or CHECK_WHICH
        todo = CHECK_WHICH
    return {
        "problem": "Perbedaan", "item": item_id, "field": FIELD_LABELS.get(field, field),
        "submitted": _value(field, submitted),
        "receipt": _value(field, read) if read is not None else Styled("Gagal dibaca", color=NEGATIVE, italic=True),
        "hint": hint, "todo": todo,
    }


def _because(field, difference, line, item):
    """Why the receipt's other numbers support what the OCR read, e.g. "35,29 L × Rp 11.477 hasilnya Rp 405.000, sama
    dengan yang dibaca OCR"."""
    expected = difference["expected_value"]
    side = "yang dibaca OCR"
    formula = _formula(field, line, item)
    if expected is None:
        return f"angka lain di struk sesuai dengan {side}"
    expected_text = _shown(field, round(expected) if field in MONEY_FIELDS else expected)
    if formula is None:
        return f"angka lain di struk menghasilkan {expected_text}, sesuai dengan {side}"
    if expected_text == _shown(field, difference["ocr_value"]):
        return f"{formula} hasilnya {expected_text}, sama dengan {side}"
    return f"{formula} hasilnya sekitar {expected_text}, sesuai dengan {side}"


def _formula(field, line, item):
    def value(key):
        found = line.get(key) if line else None
        return found if found is not None else item.get(key) if item else None

    volume, price, amount = value("volume_liter"), value("price_per_liter"), value("total_price")
    if field == "total_price" and volume is not None and price is not None:
        return f"{_shown('volume_liter', volume)} L × {_shown('price_per_liter', price)}"
    if field == "volume_liter" and amount is not None and price is not None:
        return f"{_shown('total_price', amount)} ÷ {_shown('price_per_liter', price)}"
    return None


def _sentences(*parts):
    return " ".join(part for part in parts if part) or None


def _number(text):
    try:
        return Decimal(str(text))
    except (InvalidOperation, ValueError):
        return None


def _same_number(a, b):
    x, y = _number(a), _number(b)
    return x is not None and y is not None and abs(x - y) < Decimal("0.01")


def _value(field, text):
    """A value of a difference (stored as text) as a cell: a number in its format, a date or a name as text."""
    if text is None:
        return None
    number = _number(text) if field in NUMBER_FIELDS else None
    if number is None:
        return str(text)
    fmt = FMT["idr"] if field in MONEY_FIELDS else FMT["count"] if field == "kilometer" else FMT["number"]
    return Styled(number, fmt=fmt)


def _shown(field, value):
    """A value as the website shows it: "Rp 405.000", "35,29" (liters), "18-12-2025"."""
    number = _number(value) if field in NUMBER_FIELDS else None
    if number is None:
        return str(value)
    if field in MONEY_FIELDS:
        return _money_text(number)
    text = f"{number.quantize(Decimal('0.001')).normalize():,f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _money_text(value):
    return "Rp " + f"{round(Decimal(value)):,}".replace(",", ".")


# The kind of slip that turns one value into the other, as the website names it (website/src/utils/valueDiff.ts)

_DIGITS = re.compile(r"\d+(\.\d+)?")


def _slip(field, a, b):
    """"Dua digit tertukar (5 dan 4)", "Tanggal dan bulan tertukar", ...; None when it isn't a common slip."""
    if a is None or b is None:
        return None
    if field == "date_of_expense":
        return _date_slip(str(a), str(b))
    return _number_slip(str(a), str(b)) if field in NUMBER_FIELDS else None


def _number_slip(a, b):
    """One digit off, two digits swapped, or a factor of 10, 100 or 1.000 (a decimal point or a zero)."""
    if not (_DIGITS.fullmatch(a) and _DIGITS.fullmatch(b)):
        return None
    x_whole, _, x_fraction = a.partition(".")
    y_whole, _, y_fraction = b.partition(".")
    x, y = x_whole + x_fraction, y_whole + y_fraction
    big, small = max(Decimal(a), Decimal(b)), min(Decimal(a), Decimal(b))
    if small > 0:
        power = math.log10(big / small)
        if 1 <= power <= 3 and abs(power - round(power)) < 1e-9:
            times = f"{10 ** round(power):,}".replace(",", ".")
            if x.rstrip("0") == y.rstrip("0"):
                return f"Nilai yang satu {times} kali nilai lainnya (salah letak titik desimal atau angka nol)"
            return None
    if len(x) != len(y) or len(x_whole) != len(y_whole):
        return None
    differing = [i for i, (p, q) in enumerate(zip(x, y)) if p != q]
    if len(differing) == 1:
        i = differing[0]
        return f"Hanya satu digit yang berbeda ({x[i]} dan {y[i]})"
    if len(differing) == 2:
        i, j = differing
        if x[i] == y[j] and x[j] == y[i]:
            return f"Dua digit tertukar ({x[i]} dan {x[j]})"
    return None


def _date_slip(a, b):
    """Day and month swapped, or only one of day, month, year differs (DD-MM-YYYY)."""
    x, y = a.split("-"), b.split("-")
    if len(x) != 3 or len(y) != 3 or not all(part.isdigit() for part in x + y):
        return None
    day, month, year = x
    if day == y[1] and month == y[0] and year == y[2] and day != month:
        return "Tanggal dan bulan tertukar"
    same = [p == q for p, q in zip(x, y)]
    if sum(same) != 2:
        return None
    return ["Hanya tanggalnya yang berbeda", "Hanya bulannya yang berbeda", "Hanya tahunnya yang berbeda"][same.index(False)]

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import jsonify, request, send_file

from backend.repositories import reimbursement_repository
from backend.services import report_filter
from backend.services.bbm_workbook import STATUS_PARTS, STATUSES, build_bbm_workbook, file_name
from backend.services.reimbursement_service import add_photo_status, add_same_receipts, current_decision, review_status

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_EXPORT_REPORTS = 5000
FOCUS_STATUSES = ("needs_review", "rejected")  # each in a sheet of its own, whatever the list's status filter
WEBSITE_URL = re.compile(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?")
PERIOD = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
# The export is in Indonesian (bbm_workbook)
MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni",
          "Juli", "Agustus", "September", "Oktober", "November", "Desember")


def export_reimbursements():
    """POST /api/reimbursements/export: the reports of a list as the reviewer has it, as an Excel workbook: every
    page, sorted as on screen; and, whatever its status filter, every report of its month and search that needs
    review and every rejected one (sheets of their own, see bbm_workbook).

    Body: the list's filter (see report_filter) and where the file links to:
          {"period": "2026-10", "status": "approved", "by": "proceed", "q": "EREP_100", "sort": "-total", "tz": 420,
           "website_url": "https://reimbursement.example.com"}
      period, status, by, q, sort  the list: the month, status filter, search and sort on screen (also the file's
                                   title, name and the line under each sheet's title)
      tz                           minutes east of UTC of the reviewer (420 = WIB), for the times (the months are WIB)
      website_url                  optional, the website's address (scheme, host, port): the report codes and photos
                                   in the file then link to the report page and the photo

    At most MAX_EXPORT_REPORTS reports in all (400 with more: choose a month). The X-Export-Count header says how
    many reports of the list the file holds.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error("invalid_body", 'Send a JSON object like {"period": "2026-10", "status": "approved"}.')
    try:
        found = report_filter.parse(body)
    except report_filter.FilterError as error:
        return _error(error.error, str(error))
    website_url = body.get("website_url")
    if website_url is not None and not (isinstance(website_url, str) and WEBSITE_URL.fullmatch(website_url)):
        return _error("invalid_website_url", "website_url must be like https://host or http://host:port, without a path.")

    codes = reimbursement_repository.find_report_codes(found.query, MAX_EXPORT_REPORTS + 1)
    # The sheets of the reports needing review and the rejected ones: the list's month and search, whatever its status
    focus_codes = [
        code
        for focus in FOCUS_STATUSES
        for code in reimbursement_repository.find_report_codes(replace(found.query, status=focus, part=None),
                                                               MAX_EXPORT_REPORTS + 1)
    ]
    all_codes = list(dict.fromkeys(codes + focus_codes))
    if len(all_codes) > MAX_EXPORT_REPORTS:
        return _error("too_many_reports", f"This export has more than {MAX_EXPORT_REPORTS} reports (the list, the "
                                          "reports needing review and the rejected ones). Choose a month or a status "
                                          "to export fewer at once.")
    status, by, parts = found.status, found.by, STATUS_PARTS.get(found.status, {})
    label = "Semua laporan" if status == "all" else STATUSES[status][0]
    if by:
        label = f"{label} · {parts[by]}"
    loaded = reimbursement_repository.find_reports(all_codes) if all_codes else []
    claimed = reimbursement_repository.find_claimed(all_codes)
    for report in loaded:
        report["ocr_status"] = add_photo_status(report["photos"])
        report["decision"] = current_decision(report["decisions"])
        report["double_claim"] = report["reimbursement_code"] in claimed
        report["review_status"] = review_status(report["ocr_status"], report["decision"], report["double_claim"])
    by_code = {report["reimbursement_code"]: report for report in loaded}
    reports = [by_code[code] for code in codes if code in by_code]
    if status != "all":
        # The list's status was worked out in SQL; a report whose status changed in the meantime is left out.
        reports = [report for report in reports
                   if report["review_status"] == status and by in (None, _part(report))]
    if not reports:
        return jsonify(
            error="empty_list",
            message=f"There are no reports in “{label}” to export any more. Refresh the list to see where they are now.",
        ), 409
    needs_review = [report for report in loaded if report["review_status"] == "needs_review"]
    rejected = [report for report in loaded if report["review_status"] == "rejected"]
    # The other reports claiming the same receipt, for those two sheets
    add_same_receipts(needs_review + rejected)

    month = PERIOD.fullmatch(found.period)
    zone = timezone(timedelta(minutes=found.utc_offset))
    info = {
        "period": f"{MONTHS[int(month[2]) - 1]} {month[1]}" if month else None,
        "filter": label,
        "search": found.search,
        "exported_at": datetime.now(zone),
        "zone": zone,
        "website_url": website_url,
    }
    workbook = build_bbm_workbook(reports, needs_review, rejected, info)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    response = send_file(output, mimetype=XLSX_TYPE, as_attachment=True, download_name=file_name(info))
    response.headers["X-Export-Count"] = str(len(reports))
    return response


def _part(report):
    """The part of its status a report is in: how an approved one was approved (matched / proceed / reviewer), why
    one needs review (duplicate: an earlier report claimed its receipt; failed: the OCR couldn't read the file;
    differences: the OCR read it and found some). As the website's needsReviewReason and approvedBy."""
    if report["review_status"] == "approved":
        return "reviewer" if report["decision"] else report["ocr_status"]
    if report["review_status"] == "needs_review":
        if report["double_claim"]:
            return "duplicate"
        return "failed" if report["ocr_status"] == "failed" else "differences"
    return None


def _error(error, message):
    return jsonify(error=error, message=message), 400

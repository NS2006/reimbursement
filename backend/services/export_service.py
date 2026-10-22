import re
from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import jsonify, request, send_file

from backend.repositories import reimbursement_repository
from backend.services import report_filter
from backend.services.bbm_workbook import STATUS_PARTS, STATUSES, build_bbm_workbook, file_name
from backend.services.reimbursement_service import add_photo_status, current_decision, review_status

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_EXPORT_REPORTS = 5000
WEBSITE_URL = re.compile(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?")
PERIOD = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")

# reimbursement_type -> how its workbook is built
WORKBOOK_BUILDERS = {
    "bbm": build_bbm_workbook,
}


def export_reimbursements():
    """POST /api/reimbursements/export?type=bbm: the reports of a list as the reviewer has it, as an Excel workbook:
    every page, sorted as on screen.

    Body: the list's filter (see report_filter) and where the file links to:
          {"period": "2026-10", "status": "approved", "by": "proceed", "q": "RB-0", "sort": "-total", "tz": 420,
           "website_url": "https://reimbursement.example.com"}
      period, status, by, q, sort  the list: the month, status filter, search and sort on screen (also the file's
                                   title, name and the line under each sheet's title)
      tz                           minutes east of UTC of the reviewer (420 = WIB), for the times (the months are WIB)
      website_url                  optional, the website's address (scheme, host, port): the report codes and photos
                                   in the file then link to the report page and the photo

    At most MAX_EXPORT_REPORTS reports (400 with more: choose a month or a status). The X-Export-Count header says
    how many reports the file holds.
    """
    reimbursement_type = request.args.get("type") or "bbm"
    build = WORKBOOK_BUILDERS.get(reimbursement_type)
    if build is None:
        return _error("invalid_type", f"type must be one of: {', '.join(WORKBOOK_BUILDERS)}")

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error("invalid_body", 'Send a JSON object like {"period": "2026-10", "status": "approved"}.')
    try:
        found = report_filter.parse({**body, "type": reimbursement_type}, WORKBOOK_BUILDERS)
    except report_filter.FilterError as error:
        return _error(error.error, str(error))
    website_url = body.get("website_url")
    if website_url is not None and not (isinstance(website_url, str) and WEBSITE_URL.fullmatch(website_url)):
        return _error("invalid_website_url", "website_url must be like https://host or http://host:port, without a path.")

    codes = reimbursement_repository.find_report_codes(found.query, MAX_EXPORT_REPORTS + 1)
    if len(codes) > MAX_EXPORT_REPORTS:
        return _error("too_many_reports", f"This list has more than {MAX_EXPORT_REPORTS} reports. Choose a month or a "
                                          "status to export fewer at once.")
    status, by, parts = found.status, found.by, STATUS_PARTS.get(found.status, {})
    label = "All reports" if status == "all" else STATUSES[status][0]
    if by:
        label = f"{label} · {parts[by]}"
    reports = reimbursement_repository.find_current_revisions(reimbursement_type, codes) if codes else []
    for report in reports:
        revision = report["revision"]
        report["ocr_status"] = add_photo_status(revision["photos"])
        report["decision"] = current_decision(revision["decisions"])
        report["review_status"] = review_status(report["ocr_status"], report["decision"])
    if status != "all":
        # The list's status was worked out in SQL; a report whose status changed in the meantime is left out.
        reports = [report for report in reports
                   if report["review_status"] == status and by in (None, _part(report))]
    if not reports:
        return jsonify(
            error="empty_list",
            message=f"There are no reports in “{label}” to export any more. Refresh the list to see where they are now.",
        ), 409

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
    workbook = build(reports, info)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    response = send_file(output, mimetype=XLSX_TYPE, as_attachment=True, download_name=file_name(info))
    response.headers["X-Export-Count"] = str(len(reports))
    return response


def _part(report):
    """The part of its status a report is in: how an approved one was approved (matched / proceed / reviewer), why
    one needs review (failed: the OCR couldn't read the file; differences: the OCR read it and found some). As the
    website's needsReviewReason and approvedBy."""
    if report["review_status"] == "approved":
        return "reviewer" if report["decision"] else report["ocr_status"]
    if report["review_status"] == "needs_review":
        return "failed" if report["ocr_status"] == "failed" else "differences"
    return None


def _error(error, message):
    return jsonify(error=error, message=message), 400

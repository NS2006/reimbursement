from flask import jsonify, request

from backend.repositories import ocr_repository, reimbursement_repository
from backend.repositories.reimbursement_repository import OCR_TYPES
from backend.services import report_filter
from backend.services.json_values import to_json
from backend.services.reimbursement_service import report_detail

# Who is signed in is checked by the Blibli gateway, not here.

MAX_RETRY_REPORTS = 5000  # as the Excel export


def retry_failed(code):
    """POST /api/reimbursements/<code>/ocr/retry: queue the receipt files of the current revision that the OCR could
    not read (failed) again, with their attempts back at 0; the OCR worker reads them next. Their last error stays
    until a file is read.

    Body: {"revision_no": 2}, the revision the reviewer looked at; it must still be the current one, and without a
    decision in force (a reviewer's decision wins over the OCR anyway).

    Answers 200 with how many files were queued and the whole report as GET /api/reimbursements/<code> sends it.
    """
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    revision_no = body.get("revision_no")
    if not isinstance(revision_no, int) or isinstance(revision_no, bool) or revision_no < 1:
        return _error(400, "invalid_revision_no", "revision_no must be the number of the revision you looked at.")

    outcome, detail = ocr_repository.requeue_revision(code, revision_no)
    if outcome == "not_found":
        return _error(404, "not_found", f"No reimbursement with code {code}.")
    if outcome == "not_current":
        return _error(409, "revision_changed", f"Revision {detail} of {code} arrived in the meantime.")
    if outcome == "decided":
        return _error(409, "decided", f"{code} is already {detail}. Take the decision back to retry the OCR.")
    if outcome == "nothing_failed":
        return _error(409, "nothing_failed", f"The OCR is not stuck on {code} any more: it was retried in the meantime.")

    return jsonify(queued=detail, reimbursement=to_json(report_detail(code)))


def retry_failed_reports():
    """POST /api/reimbursements/ocr/retry?type=bbm: retry the OCR on the website's "OCR couldn't read" list at once
    (every page): the failed files of its reports' current revisions are queued again, as POST
    /api/reimbursements/<code>/ocr/retry does for one. A report without a failed file left, or with a decision in
    force, is skipped.

    Body: the list's filter (see report_filter), which must be that list: {"status": "needs_review", "by": "failed",
    "period": "2026-10", "q": "RB-0", "sort": "-received", "tz": 420}. At most MAX_RETRY_REPORTS reports.

    Answers 200 with the codes of the reports queued again ("queued") and how many files ("files"); 409 when none
    of them had a failed file left (retried in the meantime, or decided).
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(400, "invalid_body", 'Send the filter of the list, like {"status": "needs_review", "by": "failed"}.')
    try:
        found = report_filter.parse({**body, "type": request.args.get("type") or "bbm"}, OCR_TYPES)
    except report_filter.FilterError as error:
        return _error(400, error.error, str(error))
    if (found.status, found.by) != ("needs_review", "failed"):
        return _error(400, "invalid_list", "Only the list Needs review · OCR couldn't read can be retried at once "
                                           '(status "needs_review", by "failed").')

    codes = reimbursement_repository.find_report_codes(found.query, MAX_RETRY_REPORTS + 1)
    if len(codes) > MAX_RETRY_REPORTS:
        return _error(400, "too_many_reports", f"Retry at most {MAX_RETRY_REPORTS} reports at once: choose a month.")
    queued, files = ocr_repository.requeue_reports(codes) if codes else ([], 0)
    if not queued:
        return _error(409, "nothing_failed",
                      "None of these reports has a file the OCR couldn't read any more: retried or decided in the meantime.")
    return jsonify(queued=queued, files=files)


def _error(status, error, message):
    return jsonify(error=error, message=message), status

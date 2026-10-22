import hashlib
import json
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from flask import jsonify, request

from backend.jobs.bbm_ocr.receipt_config import MAX_PDF_BYTES
from backend.repositories import comment_repository, reimbursement_repository
from backend.services import file_storage, report_filter
from backend.services.file_download import EXTENSIONS, DownloadError, download
from backend.services.json_values import to_json

log = logging.getLogger(__name__)

MAX_REPORTS_PER_REQUEST = 100
DOWNLOADS_AT_ONCE = 8  # files of one request downloaded and stored in parallel
PAGE_SIZE = 20  # reports on a page of the list (as the website's PAGE_SIZE)
MAX_PAGE_SIZE = 100
MAX_LIST_CODES = 5000  # the codes a list gives for previous / next on the report pages

# One status for a revision, from the newest OCR row of each of its photos; the first that applies wins:
# a photo the OCR could not read (failed), a photo that needs a reviewer, a photo still queued or being read
# (processing), then harmless differences, then a match.
OCR_STATUS_ORDER = ["failed", "needs_review", "processing", "proceed", "matched"]

# What is left to do with a revision (its review status): needs_review, processing (the OCR is reading it),
# approved or rejected.
REVIEW_STATUSES = ["needs_review", "processing", "approved", "rejected"]


def store_reimbursements():
    """POST /api/reimbursements: store every report in the request as a new revision.

    Each report is checked and saved on its own, so one bad report does not block the others.
    The links of the files expire soon (Darwinbox's after 10 minutes), so every file is downloaded now and kept in
    our file storage (file_storage) before its report is saved; a report whose file can't be downloaded is rejected,
    to be sent again with a new link. When the file storage itself can't be used, nothing is saved (503).
    Sending a report again is safe: the same data and files store nothing new ("unchanged"), whatever the links.
    The OCR does not run here: the file of every new revision is queued, in one OCR process for this request,
    and the OCR worker (backend/jobs/bbm_ocr/worker.py) reads it soon after.
    """
    try:
        body = json.loads(request.get_data(), parse_float=Decimal, parse_constant=_reject_constant)
    except ValueError:
        return _body_error("invalid_json", "The body must be valid JSON.")

    reports = body.get("reimbursements") if isinstance(body, dict) else None
    if not isinstance(reports, list) or not reports:
        return _body_error("invalid_body", 'Send a JSON object like {"reimbursements": [ ... ]} with at least one report.')
    if len(reports) > MAX_REPORTS_PER_REQUEST:
        return _body_error("too_many_reports", f"Send at most {MAX_REPORTS_PER_REQUEST} reports per request.")

    results = [None] * len(reports)
    to_save = []  # (index, report, payload hash)
    seen_codes = set()
    for index, raw in enumerate(reports):
        report, errors = validate_report(raw)
        if not errors and report["reimbursement_code"] in seen_codes:
            errors = [_error("reimbursement_code", "appears more than once in this request")]
        if errors:
            code = raw.get("reimbursement_code") if isinstance(raw, dict) else None
            results[index] = {
                "index": index,
                "reimbursement_code": code if isinstance(code, str) else None,
                "status": "rejected",
                "errors": errors,
            }
        else:
            seen_codes.add(report["reimbursement_code"])
            to_save.append((index, report))

    try:
        failed = fetch_files(to_save)
    except file_storage.StorageError as error:
        log.error("File storage unavailable, nothing stored: %s", error)
        return jsonify(error="file_storage_unavailable",
                       message="The receipt files can't be stored right now, so nothing was saved. Send the request "
                               "again later."), 503
    for index, report in to_save:
        if index in failed:
            results[index] = {"index": index, "reimbursement_code": report["reimbursement_code"],
                              "status": "rejected", "errors": failed[index]}
    to_save = [(index, report, payload_hash(report)) for index, report in to_save if index not in failed]

    outcomes = reimbursement_repository.save_revisions([(report, digest) for _, report, digest in to_save])
    for (index, report, _), outcome in zip(to_save, outcomes):
        results[index] = {"index": index, "reimbursement_code": report["reimbursement_code"], **outcome}

    rejected = sum(result["status"] == "rejected" for result in results)
    return jsonify(received=len(results), accepted=len(results) - rejected, rejected=rejected, results=results), 202


# ---------------------------------------------------------------------------
# Reading reports (for the website)
# ---------------------------------------------------------------------------

def list_reimbursements():
    """GET /api/reimbursements?type=bbm&period=2026-10&status=approved&by=proceed&q=RB-0&sort=-total&tz=420&page=2:
    one page of the report list (the filter: see report_filter), each report with its current revision, its OCR and
    review status. page_size: the reports on a page (default 20, at most 100). A page past the end of the list gives
    its last page.

    Answers {"reimbursements": [...], "page": 2, "page_size": 20, "page_count": 3, "matching": 57}: matching is how
    many reports the whole list holds."""
    try:
        found = report_filter.parse(request.args, ITEM_VALIDATORS)
        page_size = _page_size(request.args.get("page_size"))
    except report_filter.FilterError as error:
        return _body_error(error.error, str(error))

    page = found.page
    reports, earlier, matching = reimbursement_repository.find_report_page(found.query, page_size, (page - 1) * page_size)
    page_count = max(1, -(-matching // page_size))
    if page > page_count:  # the list got shorter since the page was linked
        page = page_count
        reports, earlier, matching = reimbursement_repository.find_report_page(
            found.query, page_size, (page - 1) * page_size)
        page_count = max(1, -(-matching // page_size))

    before = defaultdict(list)  # the revisions before the current one, oldest first, by report
    for revision in earlier:
        revision["ocr_status"] = ocr_status(revision.pop("photo_count"), revision.pop("ocr_states"))
        revision["decision"] = {"decision": revision["decision"]} if revision["decision"] in ("approved", "rejected") else None
        before[revision.pop("reimbursement_code")].append(revision)
    for report in reports:
        decision = {"id": report.pop("decision_id"), "decision": report.pop("decision"),
                    "reason": report.pop("decision_reason"), "user_email": report.pop("decision_user_email"),
                    "user_name": report.pop("decision_user_name"), "decided_at": report.pop("decision_decided_at")}
        report["decision"] = decision if decision["id"] is not None else None
        report["previously_approved"] = walk_revisions(before[report["reimbursement_code"]]) == "approved"
    return jsonify(reimbursements=to_json(reports), page=page, page_size=page_size, page_count=page_count,
                   matching=matching)


def summarize_reimbursements():
    """GET /api/reimbursements/summary?type=bbm&q=RB-0: how many reports there are of each month (received in, WIB),
    review status and part of it, and their amount; q narrows it down as in the list.
    For the list's month picker and status counts, and the home page.

    Answers {"groups": [{"period": "2026-10", "status": "approved", "part": "proceed", "reports": 12,
    "amount": 4250000}, ...], "oldest_needs_review": "RB-012"}: the report that needs review the longest, or null."""
    try:
        found = report_filter.parse(request.args, ITEM_VALIDATORS)
    except report_filter.FilterError as error:
        return _body_error(error.error, str(error))
    groups, oldest = reimbursement_repository.find_report_summary(
        found.query.reimbursement_type, found.query.search, report_filter.MONTH_UTC_OFFSET)
    return jsonify(groups=to_json(groups), oldest_needs_review=oldest)


def list_codes():
    """GET /api/reimbursements/codes?<the list's filter and sort>: the codes of the reports of the list, in its order
    (the first MAX_LIST_CODES), for previous / next on the report pages.

    Answers {"codes": ["RB-012", ...], "more": false}: more is true when the list holds more reports."""
    try:
        found = report_filter.parse(request.args, ITEM_VALIDATORS)
    except report_filter.FilterError as error:
        return _body_error(error.error, str(error))
    codes = reimbursement_repository.find_report_codes(found.query, MAX_LIST_CODES + 1)
    return jsonify(codes=codes[:MAX_LIST_CODES], more=len(codes) > MAX_LIST_CODES)


def _page_size(value):
    if value is None or value == "":
        return PAGE_SIZE
    if not re.fullmatch(r"\d{1,3}", value) or not 1 <= int(value) <= MAX_PAGE_SIZE:
        raise report_filter.FilterError("invalid_page_size", f"page_size must be a number from 1 to {MAX_PAGE_SIZE}.")
    return int(value)


def get_reimbursement(code):
    """GET /api/reimbursements/<code>: one report with every revision (newest first: the first is the current one),
    their items and photos, the OCR result of each photo (lines read, differences), the reviewers' decisions on each
    revision and their comments on the report."""
    report = report_detail(code)
    if report is None:
        return jsonify(error="not_found", message=f"No reimbursement with code {code}."), 404
    return jsonify(reimbursement=to_json(report))


def report_detail(code):
    """The report as GET /api/reimbursements/<code> sends it (not yet made JSON-ready), or None if it is unknown.
    Each revision gets its ocr_status, the decision in force (or None), previously_rejected, previously_approved and
    review_status (see walk_revisions), and each photo its own ocr_status, ocr_error_reason and ocr_attempts (see
    add_photo_status)."""
    report = reimbursement_repository.find_report(code)
    if report is None:
        return None

    for revision in report["revisions"]:
        revision["ocr_status"] = add_photo_status(revision["photos"])
        revision["decision"] = current_decision(revision["decisions"])
    walk_revisions(reversed(report["revisions"]))
    report["comments"] = comment_repository.find_by_report(code)
    return report


def walk_revisions(revisions):
    """Give each revision of a report, oldest first (each with its ocr_status and its decision in force, or None),
    what came before it and its review_status:
      previously_rejected  the latest earlier revision with a decision was rejected: shown as a note ("Sent again
                           after a rejection"); the status is worked out as for any revision
      previously_approved  the latest earlier revision that ended approved or rejected (by a reviewer, or approved by
                           the OCR) ended approved: the report was revised after an approval, which the website marks
    Returns how the last of them that ended approved or rejected ended ("approved" / "rejected"; None when none did),
    which is previously_approved for a revision after them."""
    decided = None  # the decision in force on the latest revision so far that has one
    ended = None  # how the latest revision so far that ended approved or rejected ended
    for revision in revisions:
        revision["previously_rejected"] = decided == "rejected"
        revision["previously_approved"] = ended == "approved"
        revision["review_status"] = review_status(revision["ocr_status"], revision["decision"])
        if revision["decision"]:
            decided = revision["decision"]["decision"]
        if revision["review_status"] in ("approved", "rejected"):
            ended = revision["review_status"]
    return ended


# Why the OCR could not read a file, as a code the website names in the reviewer's language. The error kept with the
# failed attempt (ocr_reimbursement.error) is the worker's own text, for developers: it can hold storage paths or
# Claude's output, so it is never sent. The patterns follow the worker's wording (jobs/bbm_ocr/worker.py and
# receipt_ocr_haiku.py, services/file_storage.py); anything else is "other".
_FAILURE_REASONS = [
    ("file_missing", re.compile(r"(?:local:|gs://).* is (?:not in|outside) the (?:local )?file storage\.$|Unknown storage path ")),
    ("storage_unavailable", re.compile(r"The file storage could not be reached ")),
    ("pdf_too_large", re.compile(r"The PDF is [\d.]+ MB;")),
    ("pdf_too_many_pages", re.compile(r"The PDF has \d+ pages;")),
    ("timed_out", re.compile(r"Claude did not finish within ")),
    ("unreadable", re.compile(r"Claude completed successfully, but no valid JSON|The OCR answer has no list of receipts\.")),
    ("ocr_unavailable", re.compile(r"Claude Code CLI |Claude execution failed:")),
]


def failure_reason(error):
    """The reason code of a failed read, from the error kept with it (matched at its start): file_missing,
    storage_unavailable, pdf_too_large, pdf_too_many_pages, timed_out, unreadable, ocr_unavailable or other."""
    return next((reason for reason, pattern in _FAILURE_REASONS if pattern.match(error or "")), "other")


def ocr_status(photo_count, states):
    """failed / needs_review / processing / proceed / matched for a revision, from the state of the newest OCR row
    of each of its photos: the decision of a done reading, else queued / running / failed. A photo without a row,
    or one queued or being read, is processing."""
    found = {"processing" if state in ("queued", "running") else state for state in states}
    if len(states) < photo_count or not states:
        found.add("processing")
    return next(status for status in OCR_STATUS_ORDER if status in found)


def add_photo_status(photos):
    """Give each photo (with ocr_task and ocr from the repository) its ocr_status (as ocr_status() above, for
    one photo), ocr_error_reason (why the OCR could not read it, when it failed: see failure_reason) and
    ocr_attempts; ocr_task is taken out.
    Returns the ocr_status of the revision they belong to."""
    for photo in photos:
        task = photo.pop("ocr_task")
        state = photo["ocr"]["decision"] if photo["ocr"] else task["status"] if task else None
        photo["ocr_status"] = ocr_status(1, [state] if state else [])
        photo["ocr_error_reason"] = failure_reason(task["error"]) if task and task["status"] == "failed" else None
        photo["ocr_attempts"] = task["attempts"] if task else 0
    return ocr_status(len(photos), [photo["ocr_status"] for photo in photos])


def current_decision(decisions):
    """The reviewer's decision in force on a revision, from its decisions newest first: the newest one, unless it was
    taken back ("reopened"). None when no decision is in force."""
    return decisions[0] if decisions and decisions[0]["decision"] != "reopened" else None


def review_status(ocr_status_, decision):
    """needs_review / processing / approved / rejected: what is left to do with a revision.

    A reviewer's decision wins. Without one, a matched or proceed revision is approved by its OCR result, whatever
    happened to the revisions before it (every revision is compared on its own, also one sent again after a rejection
    or an approval). A revision the OCR flagged, or could not read (failed), needs a reviewer; one the OCR is still
    reading is processing."""
    if decision:
        return decision["decision"]
    if ocr_status_ in ("matched", "proceed"):
        return "approved"
    return "needs_review" if ocr_status_ == "failed" else ocr_status_


# ---------------------------------------------------------------------------
# Checking one report
# ---------------------------------------------------------------------------

def validate_bbm_item(raw, path, errors):
    return {
        "item_id": _text(raw, "item_id", path, errors, max_length=50),
        "product_name": _text(raw, "product_name", path, errors, max_length=255),
        "date_of_expense": _date(raw, "date_of_expense", path, errors),
        "price_per_liter": _number(raw, "price_per_liter", path, errors, digits=12, decimals=2, required=False),
        "volume_liter": _number(raw, "volume_liter", path, errors, digits=10, decimals=3, above_zero=True),
        "kilometer": _integer(raw, "kilometer", path, errors, required=False),
        "total_price": _number(raw, "total_price", path, errors, digits=14, decimals=2),
    }


# reimbursement_type -> how to check one of its items. A new type adds a line here (and a table + writer
# in reimbursement_repository); the endpoint and the request shape stay the same.
ITEM_VALIDATORS = {
    "bbm": validate_bbm_item,
}

# reimbursement_type -> the most attachments (files) one report may have; a type not listed may have several.
# A BBM report has exactly one file, which may show several receipts (e.g. a month of fills).
MAX_ATTACHMENTS = {
    "bbm": 1,
}


def validate_report(raw):
    """Return (report, errors). The report holds the cleaned values; errors is empty when it is valid."""
    if not isinstance(raw, dict):
        return None, [_error("", "each report must be a JSON object")]

    errors = []
    report = {
        "reimbursement_code": _text(raw, "reimbursement_code", "", errors, max_length=50),
        "reimbursement_type": _text(raw, "reimbursement_type", "", errors, max_length=20),
        "grand_total": _number(raw, "grand_total", "", errors, digits=14, decimals=2),
    }
    item_validator = ITEM_VALIDATORS.get(report["reimbursement_type"])
    if report["reimbursement_type"] is not None and item_validator is None:
        errors.append(_error("reimbursement_type", f"must be one of: {', '.join(ITEM_VALIDATORS)}"))

    employee = raw.get("employee")
    if isinstance(employee, dict):
        report["employee"] = {
            "employee_no": _text(employee, "employee_no", "employee.", errors, max_length=50),
            "name": _text(employee, "name", "employee.", errors, max_length=255),
        }
    else:
        errors.append(_error("employee", "must be an object with employee_no and name"))

    report["attachments"] = [
        {
            "name": _text(attachment, "name", path, errors, max_length=255),
            "url": _url(attachment, "url", path, errors),
        }
        for attachment, path in _objects(raw, "attachments", errors)
    ]
    limit = MAX_ATTACHMENTS.get(report["reimbursement_type"])
    sent = raw.get("attachments")
    if limit is not None and isinstance(sent, list) and len(sent) > limit:
        files = "one file" if limit == 1 else f"at most {limit} files"
        errors.append(_error("attachments", f"a {report['reimbursement_type']} report has {files} (one file may show "
                                            f"several receipts); {len(sent)} were sent"))

    report["items"] = []
    if item_validator is not None:
        report["items"] = [item_validator(item, path, errors) for item, path in _objects(raw, "items", errors)]
        seen = set()
        for i, item in enumerate(report["items"]):
            if item["item_id"] in seen:
                errors.append(_error(f"items[{i}].item_id", "is used by another item in this report"))
            seen.add(item["item_id"])

        # What was paid can't be more than the price of what was bought: a discount only lowers it.
        prices = [item.get("total_price") for item in report["items"]]
        if report["grand_total"] is not None and prices and None not in prices and report["grand_total"] > sum(prices):
            errors.append(_error("grand_total", f"is more than the total_price of the items added up "
                                                f"({format(sum(prices).normalize(), 'f')}); a discount can only lower it"))

    return report, errors


def fetch_files(reports):
    """Download the file of every attachment of these (index, report) and store it (file_storage), several at
    once. Each attachment that worked gets its sha256, storage_path and content_type. Returns {index: errors} for
    the reports with a file that could not be downloaded; raises file_storage.StorageError when the storage fails."""
    jobs = [(index, n, attachment) for index, report in reports for n, attachment in enumerate(report["attachments"])]
    failed = {}
    with ThreadPoolExecutor(max_workers=DOWNLOADS_AT_ONCE) as pool:
        for (index, n, _), error in zip(jobs, pool.map(lambda job: _fetch_file(job[2]), jobs)):
            if error:
                failed.setdefault(index, []).append(_error(f"attachments[{n}].url", error))
    return failed


def _fetch_file(attachment):
    """Download one attachment's file and store it; returns why it could not be downloaded, or None."""
    try:
        data, content_type = download(attachment["url"], attachment["name"])
    except DownloadError as error:
        # An unreachable file may be an expired link: a new one may work
        return f"{error} Send the report again with a new link." if error.error == "file_unreachable" else str(error)
    if content_type == "application/pdf" and len(data) > MAX_PDF_BYTES:
        # Stored, it would fail the OCR for good: Claude reads a PDF of at most MAX_PDF_BYTES
        return (f"{attachment['name']} is a PDF of {len(data) / (1024 * 1024):.1f} MB; the OCR reads PDFs of at most "
                f"{MAX_PDF_BYTES // (1024 * 1024)} MB.")
    digest = hashlib.sha256(data).hexdigest()
    attachment["storage_path"] = file_storage.save(data, digest, EXTENSIONS[content_type], content_type)
    attachment["sha256"] = digest
    attachment["content_type"] = content_type
    return None


def payload_hash(report):
    """SHA-256 of what a revision contains, written the same way every time (numbers without trailing
    zeros, items sorted by item_id, files by their content), so an identical resend gives the same hash.
    A file counts by its name and SHA-256, not its link: a resend comes with a new link to the same file."""

    def plain(value):
        if isinstance(value, Decimal):
            return f"{value.normalize():f}"
        if isinstance(value, date):
            return value.isoformat()
        return value

    content = {
        "grand_total": plain(report["grand_total"]),
        "attachments": sorted(
            ({"name": a["name"], "sha256": a["sha256"]} for a in report["attachments"]),
            key=lambda a: (a["sha256"], a["name"]),
        ),
        "items": sorted(
            ({key: plain(value) for key, value in item.items()} for item in report["items"]),
            key=lambda item: item["item_id"],
        ),
    }
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Field checks: each returns the cleaned value (or None) and adds an error when the value is wrong
# ---------------------------------------------------------------------------

DATE_PATTERN = re.compile(r"\d{2}-\d{2}-\d{4}")  # DD-MM-YYYY, e.g. 12-06-2026 is 12 June 2026


def _error(field, message):
    return {"field": field, "message": message}


def _body_error(error, message):
    return jsonify(error=error, message=message), 400


def _reject_constant(name):
    raise ValueError(f"{name} is not allowed")


def _missing(obj, key, path, errors, required):
    if obj.get(key) is None:
        if required:
            errors.append(_error(path + key, "is required"))
        return True
    return False


def _text(obj, key, path, errors, *, max_length, required=True):
    if _missing(obj, key, path, errors, required):
        return None
    value = obj[key]
    if not isinstance(value, str) or not value.strip():
        errors.append(_error(path + key, "must be a non-empty text"))
        return None
    value = value.strip()
    if len(value) > max_length:
        errors.append(_error(path + key, f"must be at most {max_length} characters"))
        return None
    return value


def _number(obj, key, path, errors, *, digits, decimals, above_zero=False, required=True):
    """A number that fits numeric(digits, decimals) and is not negative (above zero if asked)."""
    if _missing(obj, key, path, errors, required):
        return None
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        errors.append(_error(path + key, "must be a number"))
        return None
    value = Decimal(value)
    if value < 0 or (above_zero and value == 0):
        errors.append(_error(path + key, "must be greater than 0" if above_zero else "must not be negative"))
        return None
    if -value.normalize().as_tuple().exponent > decimals:
        errors.append(_error(path + key, f"must have at most {decimals} decimals"))
        return None
    if value >= Decimal(10) ** (digits - decimals):
        errors.append(_error(path + key, "is too large"))
        return None
    return value


def _integer(obj, key, path, errors, *, required=True):
    if _missing(obj, key, path, errors, required):
        return None
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2_147_483_647:
        errors.append(_error(path + key, "must be a whole number, 0 or more"))
        return None
    return value


def _date(obj, key, path, errors, *, required=True):
    if _missing(obj, key, path, errors, required):
        return None
    value = obj[key]
    try:
        if isinstance(value, str) and DATE_PATTERN.fullmatch(value):
            return datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        pass
    errors.append(_error(path + key, "must be a date written as DD-MM-YYYY"))
    return None


def _url(obj, key, path, errors):
    value = _text(obj, key, path, errors, max_length=4000)  # a signed link can be long
    if value is None:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        errors.append(_error(path + key, "must be an http or https address"))
        return None
    return value


def _objects(obj, key, errors):
    """Yield (object, path) for a required, non-empty list of objects."""
    value = obj.get(key)
    if not isinstance(value, list) or not value:
        errors.append(_error(key, "must be a list with at least one entry"))
        return
    for i, entry in enumerate(value):
        if isinstance(entry, dict):
            yield entry, f"{key}[{i}]."
        else:
            errors.append(_error(f"{key}[{i}]", "must be a JSON object"))

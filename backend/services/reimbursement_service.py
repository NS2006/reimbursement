import hashlib
import json
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit

from flask import jsonify, request

from backend.repositories import comment_repository, reimbursement_repository
from backend.services import file_storage, fuel_price_service, report_filter
from backend.services.file_download import EXTENSIONS, DownloadError, download
from backend.services.json_values import to_json

log = logging.getLogger(__name__)

# For now (the trial with Darwinbox) a request has no limit on its reports, the files of an item or their sizes;
# limits come back later. A PDF the OCR can't read whole (receipt_config) is stored, and its OCR fails for the
# reviewer to check it by hand.
DOWNLOADS_AT_ONCE = 16  # files of one request downloaded and stored in parallel
PAGE_SIZE = 20  # reports on a page of the list (as the website's PAGE_SIZE)
MAX_PAGE_SIZE = 100
MAX_LIST_CODES = 5000  # the codes a list gives for previous / next on the report pages

# One status for a report, from the newest OCR row of each of its files; the first that applies wins:
# a file the OCR could not read (failed), a file that needs a reviewer, a file still queued or being read
# (processing), then harmless differences, then a match.
OCR_STATUS_ORDER = ["failed", "needs_review", "processing", "proceed", "matched"]

# What is left to do with a report (its review status): needs_review, processing (the OCR is reading it),
# approved or rejected.
REVIEW_STATUSES = ["needs_review", "processing", "approved", "rejected"]


def store_reimbursements():
    """POST /api/reimbursements: store every report in the request that is new. A request may hold any number of
    reports, and its body may be any size (backend/app.py).

    Each report is checked and saved on its own, so one bad report does not block the others. A report is stored
    once and never changed (a rejected report comes back under a new code): its code sent again with the same data
    and files stores nothing ("unchanged"), whatever the links; with other data it is rejected.
    The links of the files expire soon (Darwinbox's after 10 minutes), so every file is downloaded now and kept in
    our file storage (file_storage) before its report is saved; a report whose file can't be downloaded is rejected,
    to be sent again with a new link. When the file storage itself can't be used, nothing is saved (503).
    The OCR does not run here: the files of every new report are queued, in one OCR process for this request,
    and the OCR worker (backend/jobs/bbm_ocr/worker.py) reads them soon after.
    """
    try:
        body = json.loads(request.get_data(), parse_float=Decimal, parse_constant=_reject_constant)
    except ValueError:
        return _body_error("invalid_json", "The body must be valid JSON.")

    reports = body.get("reimbursements") if isinstance(body, dict) else None
    if not isinstance(reports, list) or not reports:
        return _body_error("invalid_body", 'Send a JSON object like {"reimbursements": [ ... ]} with at least one report.')

    results = [None] * len(reports)
    to_save = []  # (index, report)
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

    outcomes = reimbursement_repository.save_reports([(report, digest) for _, report, digest in to_save])
    for (index, report, _), outcome in zip(to_save, outcomes):
        results[index] = {"index": index, "reimbursement_code": report["reimbursement_code"], **outcome}
    if any(outcome["status"] == "created" for outcome in outcomes):
        fuel_price_service.queue_daily_refresh()  # a new batch: the fuel prices are checked once a day

    rejected = sum(result["status"] == "rejected" for result in results)
    return jsonify(received=len(results), accepted=len(results) - rejected, rejected=rejected, results=results), 202


# ---------------------------------------------------------------------------
# Reading reports (for the website)
# ---------------------------------------------------------------------------

def list_reimbursements():
    """GET /api/reimbursements?period=2026-10&status=approved&by=proceed&q=EREP_100&sort=-total&tz=420&page=2:
    one page of the report list (the filter: see report_filter), each report with its OCR and review status.
    page_size: the reports on a page (default 20, at most 100). A page past the end of the list gives its last page.

    Answers {"reimbursements": [...], "page": 2, "page_size": 20, "page_count": 3, "matching": 57}: matching is how
    many reports the whole list holds."""
    try:
        found = report_filter.parse(request.args)
        page_size = _page_size(request.args.get("page_size"))
    except report_filter.FilterError as error:
        return _body_error(error.error, str(error))

    page = found.page
    reports, matching = reimbursement_repository.find_report_page(found.query, page_size, (page - 1) * page_size)
    page_count = max(1, -(-matching // page_size))
    if page > page_count:  # the list got shorter since the page was linked
        page = page_count
        reports, matching = reimbursement_repository.find_report_page(found.query, page_size, (page - 1) * page_size)
        page_count = max(1, -(-matching // page_size))

    for report in reports:
        decision = _decision_of(report)
        for key in ("decision_id", "decision_reason", "decision_user_email", "decision_user_name",
                    "decision_decided_at"):
            del report[key]
        report["decision"] = decision
    return jsonify(reimbursements=to_json(reports), page=page, page_size=page_size, page_count=page_count,
                   matching=matching)


def summarize_reimbursements():
    """GET /api/reimbursements/summary?q=EREP_100: how many reports there are of each month (received in, WIB),
    review status and part of it, and their amount; q narrows it down as in the list.
    For the list's month picker and status counts, and the home page.

    Answers {"groups": [{"period": "2026-10", "status": "approved", "part": "proceed", "reports": 12,
    "amount": 4250000}, ...], "oldest_needs_review": "EREP_10012"}: the report that needs review the longest, or null."""
    try:
        found = report_filter.parse(request.args)
    except report_filter.FilterError as error:
        return _body_error(error.error, str(error))
    groups, oldest = reimbursement_repository.find_report_summary(found.query.search, report_filter.MONTH_UTC_OFFSET)
    return jsonify(groups=to_json(groups), oldest_needs_review=oldest)


def list_codes():
    """GET /api/reimbursements/codes?<the list's filter and sort>: the codes of the reports of the list, in its order
    (the first MAX_LIST_CODES), for previous / next on the report pages.

    Answers {"codes": ["EREP_10012", ...], "more": false}: more is true when the list holds more reports."""
    try:
        found = report_filter.parse(request.args)
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
    """GET /api/reimbursements/<code>: one report with its items and photos (its files: each item's photo_ids, each
    photo's item_ids), the OCR result of each photo (lines read, differences), the reviewers' decisions and their
    comments."""
    report = report_detail(code)
    if report is None:
        return jsonify(error="not_found", message=f"No reimbursement with code {code}."), 404
    return jsonify(reimbursement=to_json(report))


def report_detail(code):
    """The report as GET /api/reimbursements/<code> sends it (not yet made JSON-ready), or None if it is unknown.
    The report gets its ocr_status, the decision in force (or None) and its review_status, and each photo its own
    ocr_status, ocr_error_reason and ocr_attempts (see add_photo_status), and each item its fuel_price (the fuel price
    page's price of its fuel, today and on its date: fuel_price_service.add_item_prices)."""
    report = reimbursement_repository.find_report(code)
    if report is None:
        return None
    report["ocr_status"] = add_photo_status(report["photos"])
    fuel_price_service.add_item_prices(report)
    report["decision"] = current_decision(report["decisions"])
    add_same_receipt(report)
    report["review_status"] = review_status(report["ocr_status"], report["decision"], report["double_claim"])
    report["comments"] = comment_repository.find_by_report(code)
    return report


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
    """failed / needs_review / processing / proceed / matched for a report, from the state of the newest OCR row
    of each of its files: the decision of a done reading, else queued / running / failed. A file without a row,
    or one queued or being read, is processing."""
    found = {"processing" if state in ("queued", "running") else state for state in states}
    if len(states) < photo_count or not states:
        found.add("processing")
    return next(status for status in OCR_STATUS_ORDER if status in found)


def add_photo_status(photos):
    """Give each photo (with ocr_task and ocr from the repository) its ocr_status (as ocr_status() above, for
    one photo), ocr_error_reason (why the OCR could not read it, when it failed: see failure_reason) and
    ocr_attempts; ocr_task is taken out.
    Returns the ocr_status of the report they belong to."""
    for photo in photos:
        task = photo.pop("ocr_task")
        state = photo["ocr"]["decision"] if photo["ocr"] else task["status"] if task else None
        photo["ocr_status"] = ocr_status(1, [state] if state else [])
        photo["ocr_error_reason"] = failure_reason(task["error"]) if task and task["status"] == "failed" else None
        photo["ocr_attempts"] = task["attempts"] if task else 0
    return ocr_status(len(photos), [photo["ocr_status"] for photo in photos])


# What another report claiming the same receipt is to this one, in the order the page lists them
SAME_RECEIPT_KINDS = ("double_claim", "resubmission", "claimed_again", "resubmitted")


def add_same_receipt(report):
    """Give the report (with its decision in force) same_receipt: the other reports claiming the same receipt (a file
    with the same content, or the same employee's item with the same day, amount and volume: stored when a report or
    a reading comes in, schema.sql store_receipt_matches), and double_claim: one of them is a double_claim, so the report needs
    a reviewer. Each other report: {reimbursement_code, employee_no, employee_name, received_at, review_status,
    decision (in force, or None), kind, files (this report's files with the same content), numbers ([{day, amount,
    volume}] they both have)}, kind being what it is to this report:

        double_claim   received before, and not a resubmission: this report may claim the receipt a second time
        resubmission   received before: the same employee's report a reviewer rejected, this one sends it again
        claimed_again  received after, claiming it again (flagged there, unless it resubmits this rejected report)
        resubmitted    received after: the same employee resubmitting this rejected report

    Worked out on every read: a decision on the other report (or on this one) changes what it is."""
    matches, others = reimbursement_repository.find_same_receipt(report["reimbursement_code"])
    found = {}
    for match in matches:
        code = match["other_code"]
        other = others[code]
        entry = found.get(code)
        if entry is None:
            entry = found[code] = {
                **_other_report(other), "kind": _same_receipt_kind(report, other, match["earlier"]),
                "files": [], "numbers": [],
            }
        if match["how"] == "file":
            if match["file_name"] not in entry["files"]:
                entry["files"].append(match["file_name"])
        elif match["how"] == "data":
            numbers = {"day": match["day"], "amount": match["amount"], "volume": match["volume"]}
            if numbers not in entry["numbers"]:
                entry["numbers"].append(numbers)
    report["same_receipt"] = sorted(found.values(), key=lambda entry: (SAME_RECEIPT_KINDS.index(entry["kind"]),
                                                                       entry["received_at"]))
    report["double_claim"] = any(entry["kind"] == "double_claim" for entry in report["same_receipt"])


def add_same_receipts(reports):
    """add_same_receipt for many reports at once (the Excel export), without the matched numbers: each report (with
    its decision in force) gets same_receipt, [{reimbursement_code, employee_no, employee_name, received_at,
    review_status, decision, kind, file_name}], file_name being its file with the same content as the other report's
    (None when they share an item's day, amount and volume instead). Leaves double_claim as it is."""
    pairs, others = reimbursement_repository.find_same_receipt_pairs([report["reimbursement_code"] for report in reports])
    by_code = defaultdict(list)
    for pair in pairs:
        by_code[pair["reimbursement_code"]].append(pair)
    for report in reports:
        report["same_receipt"] = [
            {**_other_report(others[pair["other_code"]]),
             "kind": _same_receipt_kind(report, others[pair["other_code"]], pair["earlier"]),
             "file_name": pair["file_name"]}
            for pair in by_code[report["reimbursement_code"]]
        ]


def _other_report(row):
    """The other report claiming the same receipt, from its row of the list."""
    return {"reimbursement_code": row["reimbursement_code"], "employee_no": row["employee_no"],
            "employee_name": row["employee_name"], "received_at": row["received_at"],
            "review_status": row["review_status"], "decision": _decision_of(row)}


def _same_receipt_kind(report, other, earlier):
    """What the other report (its row of the list) is to this report (with its decision in force): see
    add_same_receipt. earlier: it was received before this one."""
    same_employee = other["employee_no"] == report["employee_no"]
    if earlier:
        decision = _decision_of(other)
        resubmission = same_employee and decision is not None and decision["decision"] == "rejected"
        return "resubmission" if resubmission else "double_claim"
    rejected = report["decision"] is not None and report["decision"]["decision"] == "rejected"
    return "resubmitted" if same_employee and rejected else "claimed_again"


def _decision_of(row):
    """The decision in force of a report row of the list (its decision_* columns), or None."""
    if row["decision_id"] is None:
        return None
    return {"id": row["decision_id"], "decision": row["decision"], "reason": row["decision_reason"],
            "user_email": row["decision_user_email"], "user_name": row["decision_user_name"],
            "decided_at": row["decision_decided_at"]}


def current_decision(decisions):
    """The reviewer's decision in force on a report, from its decisions newest first: the newest one, unless it was
    taken back ("reopened"). None when no decision is in force."""
    return decisions[0] if decisions and decisions[0]["decision"] != "reopened" else None


def review_status(ocr_status_, decision, double_claim=False):
    """needs_review / processing / approved / rejected: what is left to do with a report.

    A reviewer's decision wins. Without one, a report claiming a receipt an earlier report claimed (double_claim, see
    add_same_receipt) needs a reviewer, whatever the OCR found. Else a matched or proceed report is approved by its
    OCR result. A report the OCR flagged, or could not read (failed), needs a reviewer; one the OCR is still reading
    is processing."""
    if decision:
        return decision["decision"]
    if double_claim:
        return "needs_review"
    if ocr_status_ in ("matched", "proceed"):
        return "approved"
    return "needs_review" if ocr_status_ == "failed" else ocr_status_


# ---------------------------------------------------------------------------
# Checking one report
# ---------------------------------------------------------------------------

# The price per liter the database works out (bbm_receipt.price_per_liter, numeric(12,2)) must fit its column
MAX_PRICE_PER_LITER = Decimal(10) ** 10


def validate_bbm_item(raw, path, errors):
    item = {
        "item_id": _text(raw, "item_id", path, errors, max_length=50),
        "product_name": _text(raw, "product_name", path, errors, max_length=255),
        "date_of_expense": _date(raw, "date_of_expense", path, errors),
        "volume_liter": _number(raw, "volume_liter", path, errors, digits=10, decimals=3, above_zero=True),
        "kilometer": _integer(raw, "kilometer", path, errors, required=False),
        "total_price": _number(raw, "total_price", path, errors, digits=14, decimals=2),
    }
    volume, total = item["volume_liter"], item["total_price"]
    if volume is not None and total is not None and \
            (total / volume).quantize(Decimal("0.01"), ROUND_HALF_UP) >= MAX_PRICE_PER_LITER:
        errors.append(_error(path + "total_price", "divided by volume_liter (the price per liter) is too large"))
    return item


# item type -> how to check one of its items. Only "bbm" so far: a new type adds a line here (and a table, its
# writer and readers in the repositories).
ITEM_VALIDATORS = {
    "bbm": validate_bbm_item,
}


def validate_report(raw):
    """Return (report, errors). The report holds the cleaned values; errors is empty when it is valid."""
    if not isinstance(raw, dict):
        return None, [_error("", "each report must be a JSON object")]

    errors = []
    report = {
        "reimbursement_code": _text(raw, "reimbursement_code", "", errors, max_length=50),
        "grand_total": _number(raw, "grand_total", "", errors, digits=14, decimals=2),
    }

    employee = raw.get("employee")
    if isinstance(employee, dict):
        report["employee"] = {
            "employee_no": _text(employee, "employee_no", "employee.", errors, max_length=50),
            "name": _text(employee, "name", "employee.", errors, max_length=255),
        }
    else:
        errors.append(_error("employee", "must be an object with employee_no and name"))

    report["items"] = [_validate_item(item, path, errors) for item, path in _objects(raw, "items", errors)]
    seen = set()
    for i, item in enumerate(report["items"]):
        if item.get("item_id") is not None and item["item_id"] in seen:
            errors.append(_error(f"items[{i}].item_id", "is used by another item in this report"))
        seen.add(item.get("item_id"))

    # What was paid can't be more than the price of what was bought: a discount only lowers it.
    prices = [item.get("total_price") for item in report["items"]]
    if report["grand_total"] is not None and prices and None not in prices and report["grand_total"] > sum(prices):
        errors.append(_error("grand_total", f"is more than the total_price of the items added up "
                                            f"({format(sum(prices).normalize(), 'f')}); a discount can only lower it"))

    return report, errors


def _validate_item(raw, path, errors):
    """One item: its type, its type's fields and its files (attachments: at least one; the same file may be sent
    with several items: it is read once)."""
    item_type = _text(raw, "type", path, errors, max_length=20)
    validator = ITEM_VALIDATORS.get(item_type)
    if item_type is not None and validator is None:
        errors.append(_error(path + "type", f"must be one of: {', '.join(ITEM_VALIDATORS)}"))
    item = validator(raw, path, errors) if validator else {}
    item["type"] = item_type

    item["attachments"] = [
        {
            "name": _text(attachment, "name", attachment_path, errors, max_length=255),
            "url": _url(attachment, "url", attachment_path, errors),
        }
        for attachment, attachment_path in _objects(raw, "attachments", errors, path)
    ]
    return item


def _downloads(reports):
    """The files to download for these (index, report): {(url, name): [(index, field, attachment), ...]}. An
    attachment sent several times in a request (the same link and name) is downloaded once."""
    downloads = defaultdict(list)
    for index, report in reports:
        for i, item in enumerate(report["items"]):
            for n, attachment in enumerate(item["attachments"]):
                downloads[(attachment["url"], attachment["name"])].append(
                    (index, f"items[{i}].attachments[{n}].url", attachment))
    return downloads


def fetch_files(reports):
    """Download the file of every attachment of these (index, report) and store it (file_storage), several at
    once. Each attachment that worked gets its sha256, storage_path and content_type. Returns {index: errors} for
    the reports with a file that could not be downloaded; raises file_storage.StorageError when the storage fails."""
    downloads = _downloads(reports)
    failed = {}
    with ThreadPoolExecutor(max_workers=DOWNLOADS_AT_ONCE) as pool:
        for uses, (stored, error) in zip(downloads.values(), pool.map(lambda key: _fetch_file(*key), downloads)):
            for index, field, attachment in uses:
                if error:
                    failed.setdefault(index, []).append(_error(field, error))
                else:
                    attachment.update(stored)
    return failed


def _fetch_file(url, name):
    """Download one file and store it: ({sha256, storage_path, content_type}, None), or (None, why it could not be
    downloaded)."""
    try:
        data, content_type = download(url, name)
    except DownloadError as error:
        # An unreachable file may be an expired link: a new one may work
        return None, f"{error} Send the report again with a new link." if error.error == "file_unreachable" else str(error)
    digest = hashlib.sha256(data).hexdigest()
    storage_path = file_storage.save(data, digest, EXTENSIONS[content_type], content_type)
    return {"sha256": digest, "storage_path": storage_path, "content_type": content_type}, None


# The item fields a report's payload_hash covers (with its files)
HASHED_ITEM_FIELDS = ("item_id", "type", "product_name", "date_of_expense", "volume_liter", "kilometer", "total_price")


def payload_hash(report):
    """SHA-256 of what a report contains, written the same way every time (numbers without trailing zeros, items
    sorted by item_id, each item's files by their content), so an identical resend gives the same hash. A file counts
    by its name and SHA-256, not its link: a resend comes with a new link to the same file. The seeds
    (backend/database/seeds) store hashes made this way: change them together."""

    def plain(value):
        if isinstance(value, Decimal):
            return f"{value.normalize():f}"
        if isinstance(value, date):
            return value.isoformat()
        return value

    content = {
        "grand_total": plain(report["grand_total"]),
        "items": sorted(
            (
                {
                    **{key: plain(item[key]) for key in HASHED_ITEM_FIELDS},
                    "attachments": sorted(
                        ({"name": a["name"], "sha256": a["sha256"]} for a in item["attachments"]),
                        key=lambda a: (a["sha256"], a["name"]),
                    ),
                }
                for item in report["items"]
            ),
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


def _objects(obj, key, errors, path=""):
    """Yield (object, path) for a required, non-empty list of objects."""
    value = obj.get(key)
    if not isinstance(value, list) or not value:
        errors.append(_error(path + key, "must be a list with at least one entry"))
        return
    for i, entry in enumerate(value):
        if isinstance(entry, dict):
            yield entry, f"{path}{key}[{i}]."
        else:
            errors.append(_error(f"{path}{key}[{i}]", "must be a JSON object"))

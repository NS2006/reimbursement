import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from backend.database.connection import fetch_all, get_connection


class ReportConflictError(Exception):
    """The reimbursement_code is already used for another employee, or was sent before with other data."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def save_reports(reports):
    """Store each (report, payload_hash) that is new, every report in its own transaction. A report is stored once
    and never changed: its code sent again with the same data (the same payload_hash) is a retry and stores nothing
    ("unchanged"); with other data, or for another employee, it is rejected.

    Every new report is checked against the others for the same receipt (store_same_receipt). The files of every new
    report are queued for the OCR worker, each file once (a file attached to several items is
    read once, as its first attachment), all in one OCR process for this call: it is made with the first file
    queued, so a call that stores nothing new makes none.

    Returns one outcome per report, in the same order:
        {"status": "created" | "unchanged"}
        {"status": "rejected", "errors": [{"field": ..., "message": ...}]}
    """
    outcomes = []
    process_id = None
    with get_connection() as conn:
        for report, payload_hash in reports:
            conn.run("START TRANSACTION")
            process_before = process_id
            try:
                outcome, attachment_ids = _save_one(conn, report, payload_hash)
                if outcome["status"] == "created":
                    store_same_receipt(conn, [report["reimbursement_code"]])
                if attachment_ids:
                    if process_id is None:
                        [[process_id]] = conn.run("INSERT INTO ocr_process DEFAULT VALUES RETURNING id")
                    _queue_ocr(conn, process_id, attachment_ids)
            except ReportConflictError as exc:
                conn.run("ROLLBACK")
                process_id = process_before  # a process made in this transaction is gone with it
                outcomes.append({"status": "rejected", "errors": [{"field": exc.field, "message": str(exc)}]})
                continue
            except Exception:
                conn.run("ROLLBACK")
                raise
            conn.run("COMMIT")
            outcomes.append(outcome)
    return outcomes


def _save_one(conn, report, payload_hash):
    """Store one report: (outcome, the attachments the OCR reads: the first of each of its files)."""
    code = report["reimbursement_code"]
    employee = report["employee"]

    conn.run(
        "INSERT INTO employee (employee_no, name) VALUES (:employee_no, :name) "
        "ON CONFLICT (employee_no) DO UPDATE SET name = EXCLUDED.name",
        employee_no=employee["employee_no"],
        name=employee["name"],
    )
    # A request storing the same code at the same time makes this wait until it is committed (then nothing is
    # inserted here) or rolled back.
    created = conn.run(
        "INSERT INTO reimbursement_report (reimbursement_code, employee_no, grand_total, payload_hash) "
        "VALUES (:code, :employee_no, :grand_total, :payload_hash) "
        "ON CONFLICT (reimbursement_code) DO NOTHING RETURNING reimbursement_code",
        code=code,
        employee_no=employee["employee_no"],
        grand_total=report["grand_total"],
        payload_hash=payload_hash,
    )
    if not created:
        [[owner, stored_hash]] = conn.run(
            "SELECT employee_no, payload_hash FROM reimbursement_report WHERE reimbursement_code = :code",
            code=code,
        )
        if owner != employee["employee_no"]:
            raise ReportConflictError("employee.employee_no", "this reimbursement_code already belongs to another employee")
        if stored_hash != payload_hash:
            raise ReportConflictError("reimbursement_code", "was already sent with other data. A report can't be "
                                                            "changed: send the changed report under a new code")
        return {"status": "unchanged"}, []

    files = {}  # sha256 -> the first attachment of that file: the one the OCR reads
    for item in report["items"]:
        [[item_row_id]] = conn.run(
            "INSERT INTO bbm_receipt (reimbursement_code, item_id, product_name, date_of_expense, volume_liter, "
            "kilometer, total_price) VALUES (:code, :item_id, :product_name, :date_of_expense, :volume_liter, "
            ":kilometer, :total_price) RETURNING id",
            code=code,
            item_id=item["item_id"],
            product_name=item["product_name"],
            date_of_expense=item["date_of_expense"],
            volume_liter=item["volume_liter"],
            kilometer=item["kilometer"],
            total_price=item["total_price"],
        )
        for attachment in item["attachments"]:
            [[attachment_id]] = conn.run(
                "INSERT INTO attachment (bbm_receipt_id, name, url, sha256, storage_path, content_type) "
                "VALUES (:item_row_id, :name, :url, :sha256, :storage_path, :content_type) RETURNING id",
                item_row_id=item_row_id,
                name=attachment["name"],
                url=attachment["url"],
                sha256=attachment["sha256"],
                storage_path=attachment["storage_path"],
                content_type=attachment["content_type"],
            )
            files.setdefault(attachment["sha256"], attachment_id)
    return {"status": "created"}, list(files.values())


def store_same_receipt(conn, codes):
    """Store the other reports claiming the same receipt as these reports (schema.sql store_receipt_matches: a file
    with the same content, or the same employee's receipt with the same day, amount and volume), in the caller's
    transaction. Called when a report arrives, and by the OCR worker when it saves a reading (ocr_repository)."""
    conn.run("SELECT store_receipt_matches(CAST(:codes AS varchar[]))", codes=list(codes))


def _queue_ocr(conn, process_id, attachment_ids):
    """Queue each file of a new report for the OCR worker, in this call's OCR process."""
    for attachment_id in attachment_ids:
        conn.run(
            "INSERT INTO ocr_reimbursement (ocr_process_id, attachment_id) VALUES (:process_id, :attachment_id)",
            process_id=process_id,
            attachment_id=attachment_id,
        )
    conn.run(
        "UPDATE ocr_process SET total_images = total_images + :count WHERE id = :process_id",
        count=len(attachment_ids),
        process_id=process_id,
    )


# ---------------------------------------------------------------------------
# Reading reports (for the website)
# ---------------------------------------------------------------------------

def _latest_ocr(where=""):
    """SQL for the newest OCR row of every file (its first attachment), whatever its status (queued, running, done or
    failed): a file queued again counts with its last row. processed_at is when a done reading finished (None
    otherwise). `where` is a fixed condition written in this file, never user input (values stay bound parameters)."""
    return f"""
        SELECT DISTINCT ON (o.attachment_id)
               o.id, o.attachment_id, o.status, o.attempts, o.error, o.decision, o.elapsed_seconds,
               o.grand_total, o.confidence_grand_total, o.ocr_process_id,
               CASE WHEN o.status = 'done' THEN o.started_at + o.elapsed_seconds * interval '1 second' END
                   AS processed_at
        FROM ocr_reimbursement o
        {where}
        ORDER BY o.attachment_id, o.id DESC
    """


# ---------------------------------------------------------------------------
# The report list (GET /api/reimbursements, /summary and /codes): filtered, sorted, counted and paged here, so the
# website only gets the page it shows. Each figure is worked out once for every report in the list (one GROUP BY
# each) and joined; a subquery per report would read the whole OCR history again for every report (about 35 s with
# a year of reports, over 20 minutes with five years).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReportQuery:
    """Which reports a list holds and in what order (checked by the service, report_filter)."""
    received_from: datetime | None = None  # a month: received from ... (included)
    received_to: datetime | None = None    # ... to (excluded)
    status: str | None = None              # needs_review / processing / approved / rejected; None: every status
    part: str | None = None                # with a status: how approved (matched / proceed / reviewer), why it needs
                                           # review (duplicate / differences / failed)
    search: str | None = None              # in the code, the employee's name or number, in any case
    sort: str = "received"                 # a key of LIST_SORTS
    descending: bool = True


# How the list can be sorted. Ties: newest first. code and employee sort the numbers in them by value (EREP_2 before
# EREP_10), with the natural_sort collation of schema.sql.
LIST_SORTS = {
    "code": "s.reimbursement_code COLLATE natural_sort",
    "employee": "s.employee_name COLLATE natural_sort",
    "received": "s.received_at",
    "total": "s.grand_total",
    # A report the OCR has not compared (still processing, or it couldn't read a file) comes before the ones
    # without differences.
    "differences": "CASE WHEN s.ocr_status IN ('processing', 'failed') THEN -1 ELSE s.difference_count END",
    # Ascending is the most urgent first.
    "status": "array_position(ARRAY['needs_review', 'processing', 'approved', 'rejected'], s.review_status)",
}
# The sorts that need the status of every report of the list (the others are read in index order, page by page)
_STATUS_SORTS = {"differences", "status"}
# What the sorts read of each report of a list
_FOUND_COLUMNS = "s.reimbursement_code, s.received_at, s.grand_total, s.employee_name"


def _scope_sql(query, params, codes=False):
    """SQL for the reports the query holds, before its status filter (with codes: the reports in :codes instead), and
    its values added to params. Only the fixed SQL below goes in the text; every value is a bound parameter."""
    where = []
    if codes:
        where.append("r.reimbursement_code = ANY(:codes)")
    else:
        if query.received_from is not None:
            where.append("r.received_at >= :received_from")
            params["received_from"] = query.received_from
        if query.received_to is not None:
            where.append("r.received_at < :received_to")
            params["received_to"] = query.received_to
        if query.search:
            where.append("(r.reimbursement_code ILIKE :search OR e.name ILIKE :search OR e.employee_no ILIKE :search)")
            params["search"] = f"%{_escape_like(query.search)}%"
    return f"""
        SELECT r.reimbursement_code, r.grand_total, r.received_at, e.employee_no, e.name AS employee_name
        FROM reimbursement_report r
        JOIN employee e USING (employee_no)
        {"WHERE " + " AND ".join(where) if where else ""}
    """


def _escape_like(text):
    """The text matched as it is in ILIKE: its %, _ and \\ are no wildcards."""
    return re.sub(r"([\\%_])", r"\\\1", text)


# The statuses of the reports in the scope CTE, worked out in SQL so the list can be filtered, sorted and counted by
# them: the "listed" CTE has ocr_status, review_status and status_part. They are reimbursement_service.ocr_status()
# and review_status(), and the part of a status as export_service._part() and the website's statusPartOf(): a change
# to one must be made to the others.
def _claimed_sql():
    """The CTE after scope with the scope's reports that claim a receipt an earlier report claimed (claimed:
    reimbursement_code), from the stored pairs (same_receipt, see schema.sql): an earlier report (received before, or
    at the same time with a lower code) claims the same receipt, and it isn't a resubmission, the same employee's report
    rejected by a reviewer (the decision in force). A claimed report needs a reviewer, whatever the OCR found.
    reimbursement_service.add_same_receipt and the website's report page explain these to the reviewer: change them
    together.
    """
    return """
        claimed AS (
            SELECT DISTINCT p.reimbursement_code
            FROM same_receipt p
            JOIN scope s ON s.reimbursement_code = p.reimbursement_code
            JOIN reimbursement_report r2 ON r2.reimbursement_code = p.other_code
            WHERE (r2.received_at, r2.reimbursement_code) < (s.received_at, s.reimbursement_code)
              AND NOT (r2.employee_no = s.employee_no AND coalesce((
                  SELECT d2.decision FROM review_decision d2 WHERE d2.reimbursement_code = r2.reimbursement_code
                  ORDER BY d2.decided_at DESC, d2.id DESC LIMIT 1), '') = 'rejected')
        )
    """


def _status_sql(differences=False, narrow=True):
    """The CTEs after scope; differences: also difference_count and difference_fields. narrow: the scope is a small
    part of the reports (a month, a search, a page), so only its rows are read; else every row is read once, which
    is faster than looking each one up in a scope of nearly every report."""
    of_scope = "WHERE {} IN (SELECT reimbursement_code FROM scope)" if narrow else "{}"
    return f"""
        {_claimed_sql()},
        files AS (    -- each file of each report (the same file attached to several items is one), by its first
                      -- attachment: the one the OCR reads
            SELECT i.reimbursement_code, min(a.id) AS attachment_id
            FROM attachment a
            JOIN bbm_receipt i ON i.id = a.bbm_receipt_id
            {of_scope.format("i.reimbursement_code") if narrow else ""}
            GROUP BY i.reimbursement_code, a.sha256
        ),
        latest AS (   -- the newest OCR row of each file; state: its decision when read, else its status
            SELECT DISTINCT ON (o.attachment_id)
                   o.id, f.reimbursement_code, o.status, o.grand_total, coalesce(o.decision, o.status) AS state
            FROM ocr_reimbursement o
            JOIN files f ON f.attachment_id = o.attachment_id
            ORDER BY o.attachment_id, o.id DESC
        ),
        ocr AS (
            SELECT reimbursement_code, count(*) AS files,
                   count(*) FILTER (WHERE state = 'failed') AS failed,
                   count(*) FILTER (WHERE state = 'needs_review') AS needs_review,
                   count(*) FILTER (WHERE state IN ('queued', 'running')) AS processing,
                   count(*) FILTER (WHERE state = 'proceed') AS proceed,
                   sum(grand_total) FILTER (WHERE status = 'done') AS ocr_grand_total
            FROM latest
            GROUP BY reimbursement_code
        ),
        photos AS (
            SELECT reimbursement_code, count(*) AS photo_count
            FROM files
            GROUP BY reimbursement_code
        ),
        decided AS (  -- the newest decision on each report ("reopened": none is in force)
            SELECT DISTINCT ON (d.reimbursement_code)
                   d.reimbursement_code, d.id, d.decision, d.reason, d.user_email, d.decided_at
            FROM review_decision d
            {of_scope.format("d.reimbursement_code") if narrow else ""}
            ORDER BY d.reimbursement_code, d.decided_at DESC, d.id DESC
        ),
        {'''differences AS (
            SELECT l.reimbursement_code, count(*) AS difference_count,
                   array_agg(df.field_name ORDER BY df.id) AS difference_fields
            FROM ocr_difference df
            JOIN latest l ON l.id = df.ocr_reimbursement_id
            GROUP BY l.reimbursement_code
        ),''' if differences else ""}
        listed AS (
            SELECT s.*, coalesce(ph.photo_count, 0) AS photo_count, o.ocr_grand_total,
                   d.id AS decision_id, d.decision, d.reason AS decision_reason, d.user_email AS decision_user_email,
                   d.decided_at AS decision_decided_at,
                   {'''coalesce(df.difference_count, 0) AS difference_count,
                   coalesce(df.difference_fields, ARRAY[]::varchar[]) AS difference_fields,''' if differences else ""}
                   os.ocr_status, rs.review_status, sp.status_part, c.reimbursement_code IS NOT NULL AS double_claim
            FROM scope s
            LEFT JOIN photos ph ON ph.reimbursement_code = s.reimbursement_code
            LEFT JOIN ocr o ON o.reimbursement_code = s.reimbursement_code
            LEFT JOIN decided d ON d.reimbursement_code = s.reimbursement_code AND d.decision <> 'reopened'
            LEFT JOIN claimed c ON c.reimbursement_code = s.reimbursement_code
            {"LEFT JOIN differences df ON df.reimbursement_code = s.reimbursement_code" if differences else ""}
            -- the first that applies: a file the OCR couldn't read, a file that needs a reviewer, a file not read yet
            -- (also one without an OCR row), then harmless differences, then a match
            CROSS JOIN LATERAL (SELECT CASE
                WHEN o.failed > 0 THEN 'failed'
                WHEN o.needs_review > 0 THEN 'needs_review'
                WHEN o.files IS NULL OR o.processing > 0 OR o.files < coalesce(ph.photo_count, 0) THEN 'processing'
                WHEN o.proceed > 0 THEN 'proceed'
                ELSE 'matched'
            END AS ocr_status) os
            -- a reviewer's decision wins; else a receipt an earlier report claimed needs a reviewer; else matched or
            -- proceed is approved by the OCR, failed needs a reviewer
            CROSS JOIN LATERAL (SELECT CASE
                WHEN d.decision IS NOT NULL THEN d.decision::text
                WHEN c.reimbursement_code IS NOT NULL THEN 'needs_review'
                WHEN os.ocr_status IN ('matched', 'proceed') THEN 'approved'
                WHEN os.ocr_status = 'failed' THEN 'needs_review'
                ELSE os.ocr_status
            END AS review_status) rs
            -- how an approved one was approved, why one needs review
            CROSS JOIN LATERAL (SELECT CASE
                WHEN rs.review_status = 'approved' AND d.decision IS NOT NULL THEN 'reviewer'
                WHEN rs.review_status = 'approved' THEN os.ocr_status
                WHEN rs.review_status = 'needs_review' AND c.reimbursement_code IS NOT NULL THEN 'duplicate'
                WHEN rs.review_status = 'needs_review' AND os.ocr_status = 'failed' THEN 'failed'
                WHEN rs.review_status = 'needs_review' THEN 'differences'
            END AS status_part) sp
        )
    """


def _narrow(query):
    """The list is a small part of the reports: a month or a search."""
    return query.received_from is not None or bool(query.search)


def _status_scope(query, scope):
    """The scope CTE of a list filtered or sorted by status. Of every report (no month, no search) it is worked out
    first (MATERIALIZED): else the planner filters on the status before joining the reports, expects a few rows
    where there are thousands, and loops over them (9 to over 30 seconds at 5 to 10 years of reports)."""
    return f"scope AS {'' if _narrow(query) else 'MATERIALIZED '}({scope})"


def _list_sql(query, params, column):
    """SQL for `column` (and "matching", how many reports the list holds, when it is worked out on the way) of
    the reports of the list, in its order, from :offset on, at most :limit."""
    direction = "DESC" if query.descending else "ASC"
    order = (f"s.received_at {direction}, s.reimbursement_code {direction}" if query.sort == "received"
             else f"{LIST_SORTS[query.sort]} {direction}, s.received_at DESC, s.reimbursement_code DESC")
    scope = _scope_sql(query, params)
    if query.status is None and query.sort not in _STATUS_SORTS:
        if not query.search and (query.sort == "received" or query.received_from is None):
            # Read in order and stop after the page: newest (or oldest) first with the index on received_at, the
            # first pages take a few ms; other orders sort the reports once. Counted on its own (_count_list),
            # quick without a search.
            return f"WITH scope AS ({scope}) SELECT s.{column} FROM scope s ORDER BY {order} LIMIT :limit OFFSET :offset"
        found = f"scope AS ({scope}), found AS MATERIALIZED (SELECT {_FOUND_COLUMNS} FROM scope s)"
    else:
        where = []
        if query.status is not None:
            where.append("s.review_status = :status")
            params["status"] = query.status
        if query.part is not None:
            where.append("s.status_part = :part")
            params["part"] = query.part
        differences = query.sort == "differences"
        found = (f"{_status_scope(query, scope)}, {_status_sql(differences=differences, narrow=_narrow(query))}, "
                 f"found AS MATERIALIZED (SELECT {_FOUND_COLUMNS}, s.ocr_status, s.review_status"
                 f"{', s.difference_count' if differences else ''} FROM listed s "
                 f"{'WHERE ' + ' AND '.join(where) if where else ''})")
    # Every report of the list is read for this order or filter anyway: found first (MATERIALIZED, so the planner
    # does not plan it for a few rows because of the LIMIT), then counted and paged.
    return (f"WITH {found} SELECT s.{column}, (SELECT count(*) FROM found) AS matching FROM found s "
            f"ORDER BY {order} LIMIT :limit OFFSET :offset")


def _count_list(conn, query):
    """How many reports the list holds."""
    params = {}
    if query.status is None and not _narrow(query):
        return conn.run("SELECT count(*) FROM reimbursement_report")[0][0]
    scope = _scope_sql(query, params)
    if query.status is None:
        return conn.run(f"WITH scope AS ({scope}) SELECT count(*) FROM scope", **params)[0][0]
    where = ["s.review_status = :status"]
    params["status"] = query.status
    if query.part is not None:
        where.append("s.status_part = :part")
        params["part"] = query.part
    return conn.run(f"WITH {_status_scope(query, scope)}, {_status_sql(narrow=_narrow(query))} SELECT count(*) FROM listed s "
                    f"WHERE {' AND '.join(where)}", **params)[0][0]


def find_report_page(query, limit, offset):
    """One page of the list: (rows, matching).
    rows: its reports in order, each with photo_count (its files), ocr_status, ocr_grand_total, difference_count,
    difference_fields (the field_name of each difference the newest OCR results found: a field appears once per
    difference), review_status and decision_* (the decision in force, None without one).
    matching: how many reports the whole list holds. An offset past its end gives no rows."""
    with get_connection() as conn:
        params = {"limit": limit, "offset": offset}
        found = fetch_all(conn, _list_sql(query, params, "reimbursement_code"), **params)
        codes = [row["reimbursement_code"] for row in found]
        if found and "matching" in found[0]:
            matching = found[0]["matching"]
        elif offset == 0 and len(found) < limit:
            matching = len(found)
        else:
            matching = _count_list(conn, query)
        if not codes:
            return [], matching
        rows = _list_rows(conn, codes)
    return rows, matching


def find_report_codes(query, limit):
    """The codes of the first `limit` reports of the list, in its order."""
    with get_connection() as conn:
        params = {"limit": limit, "offset": 0}
        return [row["reimbursement_code"] for row in fetch_all(conn, _list_sql(query, params, "reimbursement_code"), **params)]


def _list_rows(conn, codes):
    """The list's columns of these reports (see find_report_page), in the order of codes."""
    params = {"codes": codes}
    rows = fetch_all(
        conn,
        f"""
        WITH scope AS ({_scope_sql(None, params, codes=True)}), {_status_sql(differences=True)}
        SELECT s.reimbursement_code, s.employee_no, s.employee_name, s.grand_total, s.received_at, s.photo_count,
               s.ocr_status, s.ocr_grand_total, s.difference_count, s.difference_fields, s.review_status,
               s.double_claim, s.decision_id, s.decision, s.decision_reason, s.decision_user_email, u.name AS decision_user_name,
               s.decision_decided_at
        FROM listed s
        LEFT JOIN app_user u ON u.email = s.decision_user_email
        """,
        **params,
    )
    position = {code: index for index, code in enumerate(codes)}
    rows.sort(key=lambda row: position[row["reimbursement_code"]])
    return rows


def find_report_summary(search, utc_offset_minutes):
    """How many reports there are of each month (received in, in the time zone utc_offset_minutes east of UTC: WIB,
    report_filter.MONTH_UTC_OFFSET), review status and part of it, and their amount: ([{period: "2026-10", status, part, reports, amount}],
    oldest_needs_review), the code of the report that needs review the longest (received first; None if none does).
    search narrows it down as in the list."""
    params = {"utc_offset": utc_offset_minutes}
    query = ReportQuery(search=search)
    with get_connection() as conn:
        groups = fetch_all(
            conn,
            f"""
            WITH scope AS ({_scope_sql(query, params)}), {_status_sql(narrow=_narrow(query))}
            SELECT to_char((s.received_at AT TIME ZONE 'UTC') + make_interval(mins => CAST(:utc_offset AS integer)),
                           'YYYY-MM') AS period,
                   s.review_status AS status, s.status_part AS part, count(*) AS reports, sum(s.grand_total) AS amount,
                   (SELECT n.reimbursement_code FROM listed n WHERE n.review_status = 'needs_review'
                    ORDER BY n.received_at, n.reimbursement_code LIMIT 1) AS oldest_needs_review
            FROM listed s
            GROUP BY 1, 2, 3
            ORDER BY 1 DESC, 2, 3
            """,
            **params,
        )
    oldest = groups[0]["oldest_needs_review"] if groups else None
    for group in groups:
        del group["oldest_needs_review"]
    return groups, oldest


def find_report(code):
    """One report with its items, files (photos) and decisions; each photo with its newest OCR result: the lines the
    OCR read and where they differ from the items. None if the code is unknown."""
    with get_connection() as conn:
        reports = _find_reports(conn, [code])
    return reports[0] if reports else None


def find_same_receipt(code):
    """The other reports claiming the same receipt as this one (the stored pairs, see schema.sql), for its page:
    (matches, others). matches: [{other_code, how, file_name, day, amount, volume, earlier}], one per thing both have
    (schema.sql receipt_matches; how and the rest None if it finds none now) and earlier: received before this one, as
    _claimed_sql counts it; others: by code, the other reports with the list's columns (as find_report_page's rows:
    employee, received_at, review_status, decision_*, ...)."""
    with get_connection() as conn:
        matches = fetch_all(
            conn,
            """
            SELECT p.other_code, m.how, m.file_name, m.day, m.amount, m.volume,
                   (r2.received_at, r2.reimbursement_code) < (r.received_at, r.reimbursement_code) AS earlier
            FROM same_receipt p
            JOIN reimbursement_report r ON r.reimbursement_code = p.reimbursement_code
            JOIN reimbursement_report r2 ON r2.reimbursement_code = p.other_code
            LEFT JOIN receipt_matches(ARRAY[CAST(:code AS varchar)]) m ON m.other_code = p.other_code
            WHERE p.reimbursement_code = :code
            ORDER BY p.other_code, m.how, m.file_name, m.day
            """,
            code=code,
        )
        codes = sorted({match["other_code"] for match in matches})
        others = {row["reimbursement_code"]: row for row in _list_rows(conn, codes)} if codes else {}
    return matches, others


def find_claimed(codes):
    """Which of these reports claim a receipt an earlier report claimed, not as a resubmission (_claimed_sql): they
    need a reviewer. For the Excel export, which works out the statuses in Python."""
    if not codes:
        return set()
    with get_connection() as conn:
        params = {"codes": list(codes)}
        rows = conn.run(f"WITH scope AS ({_scope_sql(None, params, codes=True)}), {_claimed_sql()} "
                        "SELECT reimbursement_code FROM claimed", **params)
    return {row[0] for row in rows}


def find_reports(codes):
    """The reports with these codes in full, like find_report gives them, in the order of codes; unknown codes are
    left out. Used by the Excel export."""
    with get_connection() as conn:
        reports = _find_reports(conn, codes)
    by_code = {report["reimbursement_code"]: report for report in reports}
    return [by_code[code] for code in dict.fromkeys(codes) if code in by_code]


def _find_reports(conn, codes):
    reports = fetch_all(
        conn,
        "SELECT r.reimbursement_code, e.employee_no, e.name AS employee_name, r.grand_total, r.received_at "
        "FROM reimbursement_report r JOIN employee e USING (employee_no) WHERE r.reimbursement_code = ANY(:codes)",
        codes=codes,
    )
    if reports:
        _add_details(conn, reports)
    return reports


def _add_details(conn, reports):
    """Give each report its items, photos (its files) and the reviewers' decisions on it, newest first.

    A file is a photo or PDF: the same file (by its SHA-256) attached to several items of a report is one photo,
    shown as its first attachment (the one the OCR reads). Each photo gets item_ids (the ids of the items it is
    attached to) and each item photo_ids (its photos). Each photo also gets ocr_task, its newest OCR row ({status,
    attempts, error}; None when it has none), and ocr, the reading of that row when it is done (the lines the OCR read
    and where they differ from the items; else None)."""
    codes = [report["reimbursement_code"] for report in reports]
    items = fetch_all(
        conn,
        "SELECT id, reimbursement_code, item_id, product_name, date_of_expense, price_per_liter, volume_liter, "
        "kilometer, total_price FROM bbm_receipt WHERE reimbursement_code = ANY(:codes) ORDER BY id",
        codes=codes,
    )
    attachments = fetch_all(
        conn,
        # Not url: the other system's link (it may carry a signature) is only for downloading the file once
        "SELECT a.id, a.bbm_receipt_id, a.name, a.sha256, i.reimbursement_code FROM attachment a "
        "JOIN bbm_receipt i ON i.id = a.bbm_receipt_id WHERE i.reimbursement_code = ANY(:codes) ORDER BY a.id",
        codes=codes,
    )
    photos = {}  # (code, sha256) -> photo
    photo_ids = defaultdict(list)  # item id -> its photos
    for attachment in attachments:
        photo = photos.setdefault((attachment["reimbursement_code"], attachment["sha256"]), {
            "id": attachment["id"], "reimbursement_code": attachment["reimbursement_code"], "name": attachment["name"],
            "item_ids": [],
        })
        if attachment["bbm_receipt_id"] not in photo["item_ids"]:
            photo["item_ids"].append(attachment["bbm_receipt_id"])
        if photo["id"] not in photo_ids[attachment["bbm_receipt_id"]]:
            photo_ids[attachment["bbm_receipt_id"]].append(photo["id"])
    for item in items:
        item["photo_ids"] = photo_ids[item["id"]]

    rows = fetch_all(conn, _latest_ocr("WHERE o.attachment_id = ANY(:ids)"),
                     ids=[photo["id"] for photo in photos.values()]) if photos else []
    task_by_photo = {row["attachment_id"]: {key: row[key] for key in TASK_FIELDS} for row in rows}
    results = [{key: value for key, value in row.items() if key not in TASK_FIELDS}
               for row in rows if row["status"] == "done"]
    result_ids = [result["id"] for result in results]
    lines, differences = [], []
    if result_ids:
        lines = _find_bbm_ocr_lines(conn, result_ids)
        differences = fetch_all(
            conn,
            "SELECT id, ocr_reimbursement_id, ocr_item_id AS ocr_line_id, bbm_receipt_id AS item_row_id, "
            "field_name, ocr_value, submitted_value, description, likely_wrong, expected_value "
            "FROM ocr_difference WHERE ocr_reimbursement_id = ANY(:ids) ORDER BY id",
            ids=result_ids,
        )

    lines_by_result = _group(lines, "ocr_reimbursement_id")
    differences_by_result = _group(differences, "ocr_reimbursement_id")
    result_by_photo = {}
    for result in results:
        result["lines"] = lines_by_result.get(result["id"], [])
        result["differences"] = differences_by_result.get(result["id"], [])
        result_by_photo[result.pop("attachment_id")] = result
    decisions = fetch_all(
        conn,
        "SELECT d.id, d.reimbursement_code, d.decision, d.reason, d.user_email, u.name AS user_name, d.decided_at "
        "FROM review_decision d JOIN app_user u ON u.email = d.user_email "
        "WHERE d.reimbursement_code = ANY(:codes) ORDER BY d.decided_at DESC, d.id DESC",
        codes=codes,
    )
    items_by_report = _group(items, "reimbursement_code")
    photos_by_report = _group(list(photos.values()), "reimbursement_code")
    decisions_by_report = _group(decisions, "reimbursement_code")
    for report in reports:
        code = report["reimbursement_code"]
        report["items"] = items_by_report.get(code, [])
        report["photos"] = [
            {**photo, "ocr_task": task_by_photo.get(photo["id"]), "ocr": result_by_photo.get(photo["id"])}
            for photo in photos_by_report.get(code, [])
        ]
        report["decisions"] = decisions_by_report.get(code, [])


# Where the newest OCR row of a photo is (queued / running / done / failed), how often it was tried and why it failed
TASK_FIELDS = ("status", "attempts", "error")


def _group(rows, key):
    """{value of key: [rows with that value]}, with the key taken out of each row."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.pop(key)].append(row)
    return grouped


def _find_bbm_ocr_lines(conn, result_ids):
    """What the OCR read, one row per product line in reading order, with its confidence per field."""
    lines = fetch_all(
        conn,
        "SELECT id, ocr_reimbursement_id, product_name, date_of_expense, price_per_liter, volume_liter, total_price, "
        "discount, confidence_product_name, confidence_date_of_expense, confidence_price_per_liter, "
        "confidence_volume_liter, confidence_total_price, confidence_discount "
        "FROM ocr_bbm_receipt WHERE ocr_reimbursement_id = ANY(:ids) ORDER BY id",
        ids=result_ids,
    )
    return [
        {
            **{key: value for key, value in line.items() if not key.startswith("confidence_")},
            "confidence": {
                key.removeprefix("confidence_"): value for key, value in line.items() if key.startswith("confidence_")
            },
        }
        for line in lines
    ]

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from backend.database.connection import fetch_all, get_connection


class ReportConflictError(Exception):
    """The reimbursement_code is already used for another employee or another reimbursement type."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def save_revisions(reports):
    """Store each (report, payload_hash) as a new revision, every report in its own transaction.

    The files of every new revision of a type the OCR reads (OCR_TYPES) are queued for the OCR worker, all in one
    OCR process for this call: it is made with the first file queued, so a call that stores nothing new makes none.

    Returns one outcome per report, in the same order:
        {"status": "created" | "revised" | "unchanged", "revision_no": n}
        {"status": "rejected", "errors": [{"field": ..., "message": ...}]}
    """
    outcomes = []
    process_id = None
    with get_connection() as conn:
        for report, payload_hash in reports:
            conn.run("START TRANSACTION")
            process_before = process_id
            try:
                outcome, revision_id, attachment_ids = _save_one(conn, report, payload_hash)
                if attachment_ids and report["reimbursement_type"] in OCR_TYPES:
                    if process_id is None:
                        [[process_id]] = conn.run("INSERT INTO ocr_process DEFAULT VALUES RETURNING id")
                    _queue_ocr(conn, process_id, revision_id, attachment_ids)
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
    code = report["reimbursement_code"]
    employee = report["employee"]

    conn.run(
        "INSERT INTO employee (employee_no, name) VALUES (:employee_no, :name) "
        "ON CONFLICT (employee_no) DO UPDATE SET name = EXCLUDED.name",
        employee_no=employee["employee_no"],
        name=employee["name"],
    )
    conn.run(
        "INSERT INTO reimbursement_report (reimbursement_code, employee_no, reimbursement_type) "
        "VALUES (:code, :employee_no, :type) ON CONFLICT (reimbursement_code) DO NOTHING",
        code=code,
        employee_no=employee["employee_no"],
        type=report["reimbursement_type"],
    )

    # Lock the report, so two requests for the same code cannot both take the next revision number.
    [[owner, reimbursement_type]] = conn.run(
        "SELECT employee_no, reimbursement_type FROM reimbursement_report WHERE reimbursement_code = :code FOR UPDATE",
        code=code,
    )
    if owner != employee["employee_no"]:
        raise ReportConflictError("employee.employee_no", "this reimbursement_code already belongs to another employee")
    if reimbursement_type != report["reimbursement_type"]:
        raise ReportConflictError("reimbursement_type", f"this reimbursement_code is a '{reimbursement_type}' reimbursement")

    latest = conn.run(
        "SELECT revision_no, payload_hash FROM reimbursement_revision "
        "WHERE reimbursement_code = :code ORDER BY revision_no DESC LIMIT 1",
        code=code,
    )
    if latest and latest[0][1] == payload_hash:
        return {"status": "unchanged", "revision_no": latest[0][0]}, None, []
    revision_no = latest[0][0] + 1 if latest else 1

    [[revision_id]] = conn.run(
        "INSERT INTO reimbursement_revision (reimbursement_code, revision_no, grand_total, payload_hash) "
        "VALUES (:code, :revision_no, :grand_total, :payload_hash) RETURNING id",
        code=code,
        revision_no=revision_no,
        grand_total=report["grand_total"],
        payload_hash=payload_hash,
    )
    ITEM_WRITERS[report["reimbursement_type"]](conn, revision_id, report["items"])
    attachment_ids = []
    for attachment in report["attachments"]:
        [[attachment_id]] = conn.run(
            "INSERT INTO attachment (revision_id, name, url, sha256, storage_path, content_type) "
            "VALUES (:revision_id, :name, :url, :sha256, :storage_path, :content_type) RETURNING id",
            revision_id=revision_id,
            **attachment,
        )
        attachment_ids.append(attachment_id)
    outcome = {"status": "created" if revision_no == 1 else "revised", "revision_no": revision_no}
    return outcome, revision_id, attachment_ids


def _queue_ocr(conn, process_id, revision_id, attachment_ids):
    """Queue each file of a new revision for the OCR worker, in this call's OCR process."""
    for attachment_id in attachment_ids:
        conn.run(
            "INSERT INTO ocr_reimbursement (ocr_process_id, revision_id, attachment_id) "
            "VALUES (:process_id, :revision_id, :attachment_id)",
            process_id=process_id,
            revision_id=revision_id,
            attachment_id=attachment_id,
        )
    conn.run(
        "UPDATE ocr_process SET total_images = total_images + :count WHERE id = :process_id",
        count=len(attachment_ids),
        process_id=process_id,
    )


def _insert_bbm_items(conn, revision_id, items):
    for item in items:
        conn.run(
            "INSERT INTO bbm_receipt (revision_id, item_id, product_name, date_of_expense, price_per_liter, "
            "volume_liter, kilometer, total_price) VALUES (:revision_id, :item_id, :product_name, "
            ":date_of_expense, :price_per_liter, :volume_liter, :kilometer, :total_price)",
            revision_id=revision_id,
            **item,
        )


# reimbursement_type -> where its items are stored
ITEM_WRITERS = {
    "bbm": _insert_bbm_items,
}

# The reimbursement types whose files the OCR reads: their files are queued when a revision is stored.
OCR_TYPES = {"bbm"}


# ---------------------------------------------------------------------------
# Reading reports (for the website)
# ---------------------------------------------------------------------------

def _latest_ocr(where=""):
    """SQL for the newest OCR row of every photo, whatever its status (queued, running, done or failed): a photo
    queued again counts with its last row. processed_at is when a done reading finished (None otherwise).
    `where` is a fixed condition written in this file, never user input (values stay bound parameters)."""
    return f"""
        SELECT DISTINCT ON (o.attachment_id)
               o.id, o.attachment_id, o.revision_id, o.status, o.attempts, o.error, o.decision, o.elapsed_seconds,
               o.grand_total, o.confidence_grand_total, o.ocr_process_id,
               CASE WHEN o.status = 'done' THEN o.started_at + o.elapsed_seconds * interval '1 second' END
                   AS processed_at
        FROM ocr_reimbursement o
        {where}
        ORDER BY o.attachment_id, o.id DESC
    """


# For revision r: whether the latest earlier revision with a decision was rejected, for the note "Sent again after a
# rejection" (the status does not depend on it). Reads the newest decision of each earlier revision through the
# index on review_decision (revision_id, decided_at DESC, id DESC), never the whole table.
_PREVIOUSLY_REJECTED = """
    coalesce((SELECT d0.decision = 'rejected'
              FROM reimbursement_revision r0
              CROSS JOIN LATERAL (SELECT d.decision FROM review_decision d WHERE d.revision_id = r0.id
                                  ORDER BY d.decided_at DESC, d.id DESC LIMIT 1) d0
              WHERE r0.reimbursement_code = r.reimbursement_code AND r0.revision_no < r.revision_no
                AND d0.decision <> 'reopened'
              ORDER BY r0.revision_no DESC
              LIMIT 1), false)
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
    reimbursement_type: str | None = None  # None: every type
    received_from: datetime | None = None  # a month: its current revision received from ... (included)
    received_to: datetime | None = None    # ... to (excluded)
    status: str | None = None              # needs_review / processing / approved / rejected; None: every status
    part: str | None = None                # with a status: how approved (matched / proceed / reviewer), why it needs
                                           # review (differences / failed)
    search: str | None = None              # in the code, the employee's name or number, in any case
    sort: str = "received"                 # a key of LIST_SORTS
    descending: bool = True


# How the list can be sorted. Ties: newest first. code and employee sort the numbers in them by value (RB-2 before
# RB-10), with the natural_sort collation of schema.sql.
LIST_SORTS = {
    "code": "s.reimbursement_code COLLATE natural_sort",
    "employee": "s.employee_name COLLATE natural_sort",
    "received": "s.received_at",
    "total": "s.grand_total",
    # A report the OCR has not compared (still processing, or it couldn't read the file) comes before the ones
    # without differences.
    "differences": "CASE WHEN s.ocr_status IN ('processing', 'failed') THEN -1 ELSE s.difference_count END",
    # Ascending is the most urgent first.
    "status": "array_position(ARRAY['needs_review', 'processing', 'approved', 'rejected'], s.review_status)",
}
# The sorts that need the status of every report of the list (the others are read in index order, page by page)
_STATUS_SORTS = {"differences", "status"}
# What the sorts read of each report of a list
_FOUND_COLUMNS = "s.id, s.reimbursement_code, s.received_at, s.grand_total, s.employee_name"


def _scope_sql(query, params, ids=False):
    """SQL for the current revision of each report the query holds, before its status filter (with ids: the
    revisions in :ids instead), and its values added to params. Only the fixed SQL below goes in the text; every
    value is a bound parameter."""
    where = []
    if ids:
        where.append("r.id = ANY(:ids)")
    else:
        where.append("NOT EXISTS (SELECT 1 FROM reimbursement_revision n "
                     "WHERE n.reimbursement_code = r.reimbursement_code AND n.revision_no > r.revision_no)")
        if query.reimbursement_type is not None:
            where.append("p.reimbursement_type = :reimbursement_type")
            params["reimbursement_type"] = query.reimbursement_type
        if query.received_from is not None:
            where.append("r.received_at >= :received_from")
            params["received_from"] = query.received_from
        if query.received_to is not None:
            where.append("r.received_at < :received_to")
            params["received_to"] = query.received_to
        if query.search:
            where.append("(p.reimbursement_code ILIKE :search OR e.name ILIKE :search OR e.employee_no ILIKE :search)")
            params["search"] = f"%{_escape_like(query.search)}%"
    return f"""
        SELECT r.id, r.reimbursement_code, r.revision_no, r.grand_total, r.received_at,
               p.reimbursement_type, e.employee_no, e.name AS employee_name
        FROM reimbursement_revision r
        JOIN reimbursement_report p USING (reimbursement_code)
        JOIN employee e USING (employee_no)
        WHERE {" AND ".join(where)}
    """


def _escape_like(text):
    """The text matched as it is in ILIKE: its %, _ and \\ are no wildcards."""
    return re.sub(r"([\\%_])", r"\\\1", text)


# The statuses of the revisions in the scope CTE, worked out in SQL so the list can be filtered, sorted and counted by
# them: the "listed" CTE has ocr_status, review_status and status_part. They are reimbursement_service.ocr_status()
# and review_status(), and the part of a status as export_service._part() and the website's statusPartOf(): a change
# to one must be made to the others.
def _status_sql(differences=False, narrow=True):
    """The CTEs after scope; differences: also difference_count and difference_fields. narrow: the scope is a small
    part of the reports (a month, a search, a page), so only its rows are read; else every row is read once, which
    is faster than looking each one up in a scope of nearly every report."""
    of_scope = "WHERE {} IN (SELECT id FROM scope)" if narrow else "{}"
    return f"""
        latest AS (   -- the newest OCR row of each file; state: its decision when read, else its status
            SELECT DISTINCT ON (o.attachment_id)
                   o.id, o.revision_id, o.status, o.grand_total, coalesce(o.decision, o.status) AS state
            FROM ocr_reimbursement o
            {of_scope.format("o.revision_id") if narrow else ""}
            ORDER BY o.attachment_id, o.id DESC
        ),
        ocr AS (
            SELECT revision_id, count(*) AS files,
                   count(*) FILTER (WHERE state = 'failed') AS failed,
                   count(*) FILTER (WHERE state = 'needs_review') AS needs_review,
                   count(*) FILTER (WHERE state IN ('queued', 'running')) AS processing,
                   count(*) FILTER (WHERE state = 'proceed') AS proceed,
                   sum(grand_total) FILTER (WHERE status = 'done') AS ocr_grand_total
            FROM latest
            GROUP BY revision_id
        ),
        photos AS (
            SELECT revision_id, count(*) AS photo_count
            FROM attachment
            {of_scope.format("revision_id") if narrow else ""}
            GROUP BY revision_id
        ),
        decided AS (  -- the newest decision on each revision ("reopened": none is in force)
            SELECT DISTINCT ON (d.revision_id)
                   d.revision_id, d.id, d.decision, d.reason, d.user_email, d.decided_at
            FROM review_decision d
            {of_scope.format("d.revision_id") if narrow else ""}
            ORDER BY d.revision_id, d.decided_at DESC, d.id DESC
        ),
        {'''differences AS (
            SELECT l.revision_id, count(*) AS difference_count,
                   array_agg(df.field_name ORDER BY df.id) AS difference_fields
            FROM ocr_difference df
            JOIN latest l ON l.id = df.ocr_reimbursement_id
            GROUP BY l.revision_id
        ),''' if differences else ""}
        listed AS (
            SELECT s.*, coalesce(ph.photo_count, 0) AS photo_count, o.ocr_grand_total,
                   d.id AS decision_id, d.decision, d.reason AS decision_reason, d.user_email AS decision_user_email,
                   d.decided_at AS decision_decided_at,
                   {'''coalesce(df.difference_count, 0) AS difference_count,
                   coalesce(df.difference_fields, ARRAY[]::varchar[]) AS difference_fields,''' if differences else ""}
                   os.ocr_status, rs.review_status, sp.status_part
            FROM scope s
            LEFT JOIN photos ph ON ph.revision_id = s.id
            LEFT JOIN ocr o ON o.revision_id = s.id
            LEFT JOIN decided d ON d.revision_id = s.id AND d.decision <> 'reopened'
            {"LEFT JOIN differences df ON df.revision_id = s.id" if differences else ""}
            -- the first that applies: a file the OCR couldn't read, a file that needs a reviewer, a file not read yet
            -- (also one without an OCR row), then harmless differences, then a match
            CROSS JOIN LATERAL (SELECT CASE
                WHEN o.failed > 0 THEN 'failed'
                WHEN o.needs_review > 0 THEN 'needs_review'
                WHEN o.files IS NULL OR o.processing > 0 OR o.files < coalesce(ph.photo_count, 0) THEN 'processing'
                WHEN o.proceed > 0 THEN 'proceed'
                ELSE 'matched'
            END AS ocr_status) os
            -- a reviewer's decision wins; else matched or proceed is approved by the OCR, failed needs a reviewer
            CROSS JOIN LATERAL (SELECT CASE
                WHEN d.decision IS NOT NULL THEN d.decision::text
                WHEN os.ocr_status IN ('matched', 'proceed') THEN 'approved'
                WHEN os.ocr_status = 'failed' THEN 'needs_review'
                ELSE os.ocr_status
            END AS review_status) rs
            -- how an approved one was approved, why one needs review
            CROSS JOIN LATERAL (SELECT CASE
                WHEN rs.review_status = 'approved' AND d.decision IS NOT NULL THEN 'reviewer'
                WHEN rs.review_status = 'approved' THEN os.ocr_status
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
    order = (f"s.received_at {direction}, s.id {direction}" if query.sort == "received"
             else f"{LIST_SORTS[query.sort]} {direction}, s.received_at DESC, s.id DESC")
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
        # Every report: each has one current revision.
        if query.reimbursement_type is None:
            return conn.run("SELECT count(*) FROM reimbursement_report")[0][0]
        return conn.run("SELECT count(*) FROM reimbursement_report WHERE reimbursement_type = :reimbursement_type",
                        reimbursement_type=query.reimbursement_type)[0][0]
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
    """One page of the list: (rows, earlier, matching).
    rows: its reports in order, each with its current revision: photo_count, ocr_status, ocr_grand_total,
    difference_count, difference_fields (the field_name of each difference the newest OCR results found: a field
    appears once per difference), review_status, decision_* (the decision in force, None without one) and
    previously_rejected (the latest earlier revision with a decision was rejected).
    earlier: every revision before the current one of those reports, as _earlier_revisions gives them.
    matching: how many reports the whole list holds. An offset past its end gives no rows."""
    with get_connection() as conn:
        params = {"limit": limit, "offset": offset}
        found = fetch_all(conn, _list_sql(query, params, "id"), **params)
        ids = [row["id"] for row in found]
        if found and "matching" in found[0]:
            matching = found[0]["matching"]
        elif offset == 0 and len(found) < limit:
            matching = len(found)
        else:
            matching = _count_list(conn, query)
        if not ids:
            return [], [], matching
        rows = _list_rows(conn, ids)
        earlier = _earlier_revisions(conn, [row["reimbursement_code"] for row in rows])
    return rows, earlier, matching


def find_report_codes(query, limit):
    """The codes of the first `limit` reports of the list, in its order."""
    with get_connection() as conn:
        params = {"limit": limit, "offset": 0}
        return [row["reimbursement_code"] for row in fetch_all(conn, _list_sql(query, params, "reimbursement_code"), **params)]


def _list_rows(conn, ids):
    """The list's columns of these revisions (see find_report_page), in the order of ids."""
    params = {"ids": ids}
    rows = fetch_all(
        conn,
        f"""
        WITH scope AS ({_scope_sql(None, params, ids=True)}), {_status_sql(differences=True)},
        previous AS (   -- per report: whether its latest earlier revision with a decision in force was rejected
            SELECT DISTINCT ON (r0.reimbursement_code) r0.reimbursement_code, d0.decision = 'rejected' AS rejected
            FROM scope s
            JOIN reimbursement_revision r0 ON r0.reimbursement_code = s.reimbursement_code
                                          AND r0.revision_no < s.revision_no
            CROSS JOIN LATERAL (SELECT d.decision FROM review_decision d WHERE d.revision_id = r0.id
                                ORDER BY d.decided_at DESC, d.id DESC LIMIT 1) d0
            WHERE d0.decision <> 'reopened'
            ORDER BY r0.reimbursement_code, r0.revision_no DESC
        )
        SELECT s.id, s.reimbursement_code, s.reimbursement_type, s.employee_no, s.employee_name,
               s.revision_no, s.grand_total, s.received_at, s.photo_count, s.ocr_status, s.ocr_grand_total,
               s.difference_count, s.difference_fields, s.review_status,
               s.decision_id, s.decision, s.decision_reason, s.decision_user_email, u.name AS decision_user_name,
               s.decision_decided_at, coalesce(pr.rejected, false) AS previously_rejected
        FROM listed s
        LEFT JOIN app_user u ON u.email = s.decision_user_email
        LEFT JOIN previous pr ON pr.reimbursement_code = s.reimbursement_code
        """,
        **params,
    )
    position = {revision_id: index for index, revision_id in enumerate(ids)}
    rows.sort(key=lambda row: position[row["id"]])
    for row in rows:
        del row["id"]
    return rows


def _earlier_revisions(conn, codes):
    """Every revision but the current one of these reports, by report and oldest first, for working out how the
    revisions before the current one ended: reimbursement_code, revision_no, photo_count, ocr_states (the state of
    the newest OCR row of each photo: its decision when done, else queued / running / failed) and decision, the newest
    decision on that revision (None without one; "reopened" when the decision was taken back)."""
    return fetch_all(
        conn,
        f"""
        WITH earlier AS (
            SELECT r.id, r.reimbursement_code, r.revision_no
            FROM reimbursement_revision r
            WHERE r.reimbursement_code = ANY(:codes)
              AND EXISTS (SELECT 1 FROM reimbursement_revision r2
                          WHERE r2.reimbursement_code = r.reimbursement_code AND r2.revision_no > r.revision_no)
        ),
        latest_ocr AS ({_latest_ocr("WHERE o.revision_id IN (SELECT id FROM earlier)")}),
        ocr AS (
            SELECT revision_id, array_agg(coalesce(decision, status)) AS ocr_states
            FROM latest_ocr
            GROUP BY revision_id
        ),
        photos AS (
            SELECT revision_id, count(*) AS photo_count
            FROM attachment
            WHERE revision_id IN (SELECT id FROM earlier)
            GROUP BY revision_id
        )
        SELECT x.reimbursement_code, x.revision_no,
               coalesce(ph.photo_count, 0) AS photo_count,
               coalesce(o.ocr_states, ARRAY[]::varchar[]) AS ocr_states,
               d.decision
        FROM earlier x
        LEFT JOIN photos ph ON ph.revision_id = x.id
        LEFT JOIN ocr o ON o.revision_id = x.id
        LEFT JOIN LATERAL (SELECT d.decision FROM review_decision d WHERE d.revision_id = x.id
                           ORDER BY d.decided_at DESC, d.id DESC LIMIT 1) d ON true
        ORDER BY x.reimbursement_code, x.revision_no
        """,
        codes=codes,
    )


def find_report_summary(reimbursement_type, search, utc_offset_minutes):
    """How many reports there are of each month (received in, in the time zone utc_offset_minutes east of UTC: WIB,
    report_filter.MONTH_UTC_OFFSET), review status and part of it, and their amount: ([{period: "2026-10", status, part, reports, amount}],
    oldest_needs_review), the code of the report that needs review the longest (received first; None if none does).
    search narrows it down as in the list."""
    params = {"utc_offset": utc_offset_minutes}
    query = ReportQuery(reimbursement_type=reimbursement_type, search=search)
    with get_connection() as conn:
        groups = fetch_all(
            conn,
            f"""
            WITH scope AS ({_scope_sql(query, params)}), {_status_sql(narrow=_narrow(query))}
            SELECT to_char((s.received_at AT TIME ZONE 'UTC') + make_interval(mins => CAST(:utc_offset AS integer)),
                           'YYYY-MM') AS period,
                   s.review_status AS status, s.status_part AS part, count(*) AS reports, sum(s.grand_total) AS amount,
                   (SELECT n.reimbursement_code FROM listed n WHERE n.review_status = 'needs_review'
                    ORDER BY n.received_at, n.id LIMIT 1) AS oldest_needs_review
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
    """One report with every revision (newest first). Each revision has its items and photos, and each photo
    its newest OCR result: the lines the OCR read and where they differ from the items. None if the code is unknown."""
    with get_connection() as conn:
        found = fetch_all(
            conn,
            "SELECT p.reimbursement_code, p.reimbursement_type, e.employee_no, e.name AS employee_name "
            "FROM reimbursement_report p JOIN employee e USING (employee_no) WHERE p.reimbursement_code = :code",
            code=code,
        )
        if not found:
            return None
        report = found[0]
        revisions = fetch_all(
            conn,
            "SELECT id, revision_no, grand_total, received_at FROM reimbursement_revision "
            "WHERE reimbursement_code = :code ORDER BY revision_no DESC",
            code=code,
        )
        _add_details(conn, report["reimbursement_type"], revisions)
    report["revisions"] = revisions
    return report


def find_current_revisions(reimbursement_type, codes):
    """The reports of this type with these codes, each with its current (highest) revision in full, like
    find_report gives it ("revision": items, photos and their newest OCR result). In the order of codes;
    unknown codes and reports of another type are left out. Used by the Excel export."""
    with get_connection() as conn:
        reports = fetch_all(
            conn,
            "SELECT p.reimbursement_code, e.employee_no, e.name AS employee_name "
            "FROM reimbursement_report p JOIN employee e USING (employee_no) "
            "WHERE p.reimbursement_code = ANY(:codes) AND p.reimbursement_type = :reimbursement_type",
            codes=codes,
            reimbursement_type=reimbursement_type,
        )
        if not reports:
            return []
        revisions = fetch_all(
            conn,
            f"""
            SELECT DISTINCT ON (r.reimbursement_code) r.id, r.reimbursement_code, r.revision_no, r.grand_total,
                   r.received_at, {_PREVIOUSLY_REJECTED} AS previously_rejected
            FROM reimbursement_revision r
            WHERE r.reimbursement_code = ANY(:codes)
            ORDER BY r.reimbursement_code, r.revision_no DESC
            """,
            codes=[report["reimbursement_code"] for report in reports],
        )
        _add_details(conn, reimbursement_type, revisions)

    revision_by_code = {revision.pop("reimbursement_code"): revision for revision in revisions}
    report_by_code = {report["reimbursement_code"]: {**report, "revision": revision_by_code[report["reimbursement_code"]]}
                      for report in reports}
    return [report_by_code[code] for code in dict.fromkeys(codes) if code in report_by_code]


def _add_details(conn, reimbursement_type, revisions):
    """Give each revision its items and photos, and the reviewers' decisions on the revision, newest first.
    Each photo gets ocr_task, its newest OCR row ({status, attempts, error}; None when it has none), and ocr, the
    reading of that row when it is done (the lines the OCR read and where they differ from the items; else None)."""
    revision_ids = [revision["id"] for revision in revisions]
    if not revision_ids:
        return
    items = ITEM_READERS[reimbursement_type](conn, revision_ids)
    photos = fetch_all(
        conn,
        # Not url: the other system's link (it may carry a signature) is only for downloading the file once
        "SELECT id, revision_id, name FROM attachment WHERE revision_id = ANY(:ids) ORDER BY id",
        ids=revision_ids,
    )
    rows = fetch_all(conn, _latest_ocr("WHERE o.revision_id = ANY(:ids)"), ids=revision_ids)
    task_by_photo = {row["attachment_id"]: {key: row[key] for key in TASK_FIELDS} for row in rows}
    results = [{key: value for key, value in row.items() if key not in TASK_FIELDS}
               for row in rows if row["status"] == "done"]
    result_ids = [result["id"] for result in results]
    lines, differences = [], []
    if result_ids:
        lines = OCR_LINE_READERS[reimbursement_type](conn, result_ids)
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
        del result["revision_id"]
        result["lines"] = lines_by_result.get(result["id"], [])
        result["differences"] = differences_by_result.get(result["id"], [])
        result_by_photo[result.pop("attachment_id")] = result
    decisions = fetch_all(
        conn,
        "SELECT d.id, d.revision_id, d.decision, d.reason, d.user_email, u.name AS user_name, d.decided_at "
        "FROM review_decision d JOIN app_user u ON u.email = d.user_email "
        "WHERE d.revision_id = ANY(:ids) ORDER BY d.decided_at DESC, d.id DESC",
        ids=revision_ids,
    )
    items_by_revision = _group(items, "revision_id")
    photos_by_revision = _group(photos, "revision_id")
    decisions_by_revision = _group(decisions, "revision_id")
    for revision in revisions:
        revision["decisions"] = decisions_by_revision.get(revision["id"], [])
        revision["items"] = items_by_revision.get(revision["id"], [])
        revision["photos"] = [
            {**photo, "ocr_task": task_by_photo.get(photo["id"]), "ocr": result_by_photo.get(photo["id"])}
            for photo in photos_by_revision.get(revision["id"], [])
        ]


# Where the newest OCR row of a photo is (queued / running / done / failed), how often it was tried and why it failed
TASK_FIELDS = ("status", "attempts", "error")


def _group(rows, key):
    """{value of key: [rows with that value]}, with the key taken out of each row."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.pop(key)].append(row)
    return grouped


def _find_bbm_items(conn, revision_ids):
    return fetch_all(
        conn,
        "SELECT id, revision_id, item_id, product_name, date_of_expense, price_per_liter, volume_liter, kilometer, "
        "total_price FROM bbm_receipt WHERE revision_id = ANY(:ids) ORDER BY id",
        ids=revision_ids,
    )


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


# reimbursement_type -> how to read its items and its OCR lines
ITEM_READERS = {
    "bbm": _find_bbm_items,
}
OCR_LINE_READERS = {
    "bbm": _find_bbm_ocr_lines,
}

from backend.database.connection import fetch_all, get_connection
from backend.repositories.reimbursement_repository import ITEM_READERS


# ---------------------------------------------------------------------------
# The queue of the OCR worker (backend/jobs/bbm_ocr/worker.py)
# ---------------------------------------------------------------------------

def requeue_stale(minutes):
    """Put files back in the queue that have been running longer than this (their worker stopped without saying
    so). Returns how many."""
    with get_connection() as conn:
        rows = conn.run(
            "UPDATE ocr_reimbursement SET status = 'queued' "
            "WHERE status = 'running' AND started_at < now() - make_interval(mins => CAST(:minutes AS integer)) "
            "RETURNING id",
            minutes=minutes,
        )
    return len(rows)


def requeue_failed():
    """Queue every failed file again, with its attempts back at 0, and reopen their processes. Returns how many."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        rows = conn.run(
            "UPDATE ocr_reimbursement SET status = 'queued', attempts = 0 WHERE status = 'failed' "
            "RETURNING ocr_process_id"
        )
        _reopen(conn, rows)
        conn.run("COMMIT")
    return len(rows)


def requeue_revision(code, revision_no):
    """Queue the failed files of the current revision of a report again (a reviewer retrying the OCR), with their
    attempts back at 0, and reopen their processes. Returns (outcome, detail):

        ("queued", how many files)
        ("not_found", None)            no report with that code
        ("not_current", revision_no)   a newer revision arrived: detail is the current revision_no
        ("decided", decision)          a reviewer's decision is in force on it (approved / rejected)
        ("nothing_failed", None)       none of its files failed (queued again in the meantime, or read)

    The report row is locked, as when deciding, so a decision and a retry at the same time come one after the other."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        try:
            outcome = _requeue_revision(conn, code, revision_no)
        except Exception:
            conn.run("ROLLBACK")
            raise
        conn.run("COMMIT" if outcome[0] == "queued" else "ROLLBACK")
    return outcome


def _requeue_revision(conn, code, revision_no):
    if not conn.run("SELECT 1 FROM reimbursement_report WHERE reimbursement_code = :code FOR UPDATE", code=code):
        return "not_found", None
    [[revision_id, current_no]] = conn.run(
        "SELECT id, revision_no FROM reimbursement_revision WHERE reimbursement_code = :code "
        "ORDER BY revision_no DESC LIMIT 1",
        code=code,
    )
    if current_no != revision_no:
        return "not_current", current_no
    newest = conn.run(
        "SELECT decision FROM review_decision WHERE revision_id = :revision_id "
        "ORDER BY decided_at DESC, id DESC LIMIT 1",
        revision_id=revision_id,
    )
    if newest and newest[0][0] != "reopened":
        return "decided", newest[0][0]

    rows = conn.run(
        "UPDATE ocr_reimbursement SET status = 'queued', attempts = 0 "
        "WHERE revision_id = :revision_id AND status = 'failed' RETURNING ocr_process_id",
        revision_id=revision_id,
    )
    if not rows:
        return "nothing_failed", None
    _reopen(conn, rows)
    return "queued", len(rows)


def requeue_reports(codes):
    """Queue the failed files of these reports again (a reviewer retrying the OCR on a whole list), as
    requeue_revision does for one: only the current revision of each, and only when no decision is in force on it.
    The report rows are locked (in code order, so two retries can't wait on each other). Returns the codes of the
    reports queued again and how many files."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        try:
            conn.run(
                "SELECT 1 FROM reimbursement_report WHERE reimbursement_code = ANY(:codes) "
                "ORDER BY reimbursement_code FOR UPDATE",
                codes=codes,
            )
            rows = conn.run(
                """
                WITH current_revision AS (
                    SELECT DISTINCT ON (reimbursement_code) id, reimbursement_code
                    FROM reimbursement_revision
                    WHERE reimbursement_code = ANY(:codes)
                    ORDER BY reimbursement_code, revision_no DESC
                ),
                newest_decision AS (
                    SELECT DISTINCT ON (d.revision_id) d.revision_id, d.decision
                    FROM review_decision d
                    JOIN current_revision r ON r.id = d.revision_id
                    ORDER BY d.revision_id, d.decided_at DESC, d.id DESC
                )
                UPDATE ocr_reimbursement o SET status = 'queued', attempts = 0
                FROM current_revision r
                WHERE o.revision_id = r.id AND o.status = 'failed'
                  AND NOT EXISTS (SELECT 1 FROM newest_decision n WHERE n.revision_id = r.id AND n.decision <> 'reopened')
                RETURNING o.ocr_process_id, r.reimbursement_code
                """,
                codes=codes,
            )
            _reopen(conn, rows)
        except Exception:
            conn.run("ROLLBACK")
            raise
        conn.run("COMMIT")
    return sorted({row[1] for row in rows}), len(rows)


def _reopen(conn, rows):
    """Reopen the processes of files queued again (rows of ocr_process_id): they are not finished any more."""
    for process_id in {row[0] for row in rows}:
        conn.run("UPDATE ocr_process SET finished_at = NULL WHERE id = :id", id=process_id)


def claim_next():
    """Take the next queued file, the oldest of those tried least (a file that failed waits behind the ones not tried
    yet): it becomes running (one more attempt, started now). Returns what reading it needs, or None when nothing is
    queued. Two workers never take the same file (SKIP LOCKED).

    {id, ocr_process_id, revision_id, attachment_id, attempts, name, storage_path, content_type, reimbursement_type,
     reimbursement_code, revision_no, grand_total, file_count (files of the revision), items (the submitted items of
     the revision)}"""
    with get_connection() as conn:
        claimed = fetch_all(
            conn,
            """
            UPDATE ocr_reimbursement o SET status = 'running', attempts = o.attempts + 1, started_at = now()
            WHERE o.id = (SELECT id FROM ocr_reimbursement WHERE status = 'queued'
                          ORDER BY attempts, id LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING o.id, o.ocr_process_id, o.revision_id, o.attachment_id, o.attempts
            """,
        )
        if not claimed:
            return None
        task = claimed[0]
        [details] = fetch_all(
            conn,
            """
            SELECT a.name, a.storage_path, a.content_type, p.reimbursement_type, r.reimbursement_code, r.revision_no, r.grand_total,
                   (SELECT count(*) FROM attachment x WHERE x.revision_id = r.id) AS file_count
            FROM attachment a
            JOIN reimbursement_revision r ON r.id = a.revision_id
            JOIN reimbursement_report p ON p.reimbursement_code = r.reimbursement_code
            WHERE a.id = :attachment_id
            """,
            attachment_id=task["attachment_id"],
        )
        task.update(details)
        task["items"] = ITEM_READERS[task["reimbursement_type"]](conn, [task["revision_id"]])
    for item in task["items"]:
        del item["revision_id"]
    return task


def save_reading(task, rows, elapsed_seconds, usage):
    """Store what the OCR read for a claimed file (rows from receipt_records.reading_rows) and mark it done, add the
    tokens it used to its process, and finish the process when nothing of it is left. All or nothing; returns False
    (and stores nothing) when the file is no longer this attempt's (requeued as stale, or its revision deleted)."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        try:
            updated = conn.run(
                "UPDATE ocr_reimbursement SET status = 'done', error = NULL, decision = :decision, "
                "elapsed_seconds = :elapsed, grand_total = :grand_total, confidence_grand_total = :confidence "
                "WHERE id = :id AND status = 'running' AND attempts = :attempts RETURNING id",
                id=task["id"],
                attempts=task["attempts"],
                decision=rows["result"]["decision"],
                elapsed=elapsed_seconds,
                grand_total=rows["result"]["grand_total"],
                confidence=rows["result"]["confidence_grand_total"],
            )
            if not updated:
                conn.run("ROLLBACK")
                return False
            line_ids = OCR_LINE_WRITERS[task["reimbursement_type"]](conn, task["id"], rows["lines"])
            for difference in rows["differences"]:
                conn.run(
                    "INSERT INTO ocr_difference (ocr_reimbursement_id, ocr_item_id, bbm_receipt_id, field_name, "
                    "ocr_value, submitted_value, description, likely_wrong, expected_value) "
                    "VALUES (:result_id, :line_id, :item_row_id, :field_name, :ocr_value, :submitted_value, :description, "
                    ":likely_wrong, :expected_value)",
                    result_id=task["id"],
                    line_id=line_ids[difference["line"]] if difference["line"] is not None else None,
                    item_row_id=difference["item_row_id"],
                    field_name=difference["field_name"],
                    ocr_value=difference["ocr_value"],
                    submitted_value=difference["submitted_value"],
                    description=difference["description"],
                    likely_wrong=difference["likely_wrong"],
                    expected_value=difference["expected_value"],
                )
            conn.run(
                "UPDATE ocr_process SET cached_input_tokens = cached_input_tokens + :cached, "
                "uncached_input_tokens = uncached_input_tokens + :uncached, output_tokens = output_tokens + :output, "
                "reasoning_tokens = reasoning_tokens + :reasoning WHERE id = :process_id",
                process_id=task["ocr_process_id"],
                cached=usage["cached_input_tokens"],
                uncached=usage["uncached_input_tokens"],
                output=usage["output_tokens"],
                reasoning=usage["reasoning_tokens"],
            )
            _finish_if_done(conn, task["ocr_process_id"])
        except Exception:
            conn.run("ROLLBACK")
            raise
        conn.run("COMMIT")
    return True


def save_failure(task, error, final):
    """A claimed file could not be read this time: back to the queue, or failed for good (final). The error is
    kept either way, so the website can say why."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        conn.run(
            "UPDATE ocr_reimbursement SET status = :status, error = :error "
            "WHERE id = :id AND status = 'running' AND attempts = :attempts",
            id=task["id"],
            attempts=task["attempts"],
            status="failed" if final else "queued",
            error=error,
        )
        _finish_if_done(conn, task["ocr_process_id"])
        conn.run("COMMIT")


def release(task):
    """Give a claimed file back to the queue as if it was never taken (the worker was stopped while reading it)."""
    with get_connection() as conn:
        conn.run(
            "UPDATE ocr_reimbursement SET status = 'queued', attempts = attempts - 1 "
            "WHERE id = :id AND status = 'running' AND attempts = :attempts",
            id=task["id"],
            attempts=task["attempts"],
        )


def _finish_if_done(conn, process_id):
    conn.run(
        "UPDATE ocr_process SET finished_at = now() "
        "WHERE id = :id AND finished_at IS NULL AND NOT EXISTS ("
        "    SELECT 1 FROM ocr_reimbursement WHERE ocr_process_id = :id AND status IN ('queued', 'running'))",
        id=process_id,
    )


def _insert_bbm_lines(conn, result_id, lines):
    """Insert the OCR lines of one file in reading order; returns their ids in the same order."""
    ids = []
    for line in lines:
        [[line_id]] = conn.run(
            "INSERT INTO ocr_bbm_receipt (ocr_reimbursement_id, product_name, date_of_expense, price_per_liter, "
            "volume_liter, total_price, discount, confidence_product_name, confidence_date_of_expense, "
            "confidence_price_per_liter, confidence_volume_liter, confidence_total_price, confidence_discount) "
            "VALUES (:result_id, :product_name, :date_of_expense, :price_per_liter, :volume_liter, :total_price, "
            ":discount, :confidence_product_name, :confidence_date_of_expense, :confidence_price_per_liter, "
            ":confidence_volume_liter, :confidence_total_price, :confidence_discount) RETURNING id",
            result_id=result_id,
            **line,
        )
        ids.append(line_id)
    return ids


# reimbursement_type -> where the lines the OCR read are stored
OCR_LINE_WRITERS = {
    "bbm": _insert_bbm_lines,
}

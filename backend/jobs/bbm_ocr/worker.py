"""
The OCR worker: reads the files the reimbursement API queued (one OCR process per call to POST /api/reimbursements),
one at a time, and stores what the OCR read and how it compares with the submitted data.

Run from the repository root (it keeps running until Ctrl+C):

    py -m backend.jobs.bbm_ocr.worker                  read the queued files, then wait for new ones
    py -m backend.jobs.bbm_ocr.worker --once           read what is queued now, then stop
    py -m backend.jobs.bbm_ocr.worker --retry-failed   queue the failed files again first
    py -m backend.jobs.bbm_ocr.worker --no-fuel-prices leave the fuel price refreshes to their own worker

For each file: take it from the file storage (services/file_storage.py; the API stored it when the report arrived),
read it with Claude Haiku (receipt_ocr_haiku.py) in a folder of its own, compare it with the submitted items it is
attached to (receipt_validation.py, the fuel types by product_labels.py; a report's only file as a whole against the
grand total) and store the reading, the decision and the differences (receipt_records.py, ocr_repository). A file
attached to several items of a report (the same file sent with each) is read once.

A file that could not be read goes back to the queue, behind the files not tried yet, up to MAX_ATTEMPTS times; one
that can never be read (missing from the storage, a PDF Claude cannot take) fails at once. When Claude itself
cannot run (not logged in, a usage limit, the service is down), or the file storage can't be reached, the worker
waits, longer each time, and fails the file only after MAX_SERVICE_ATTEMPTS. A failed file shows on the website as "OCR couldn't read it", for a reviewer,
who can queue it again there ("Retry OCR": POST /api/reimbursements/<code>/ocr/retry, or "Retry OCR on all" on the
list: POST /api/reimbursements/ocr/retry).
Several workers can run at once: they never take the same file.

Before its next file, the worker runs a queued fuel price refresh, if any (backend/jobs/fuel_price/worker.py; the
website's button and a new batch of reports queue one): it takes a few minutes, and someone may be waiting for it.
With --no-fuel-prices it doesn't: the fuel price worker runs them (py -m backend.jobs.fuel_price.worker).
"""

import argparse
import logging
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

from backend.jobs.bbm_ocr.product_labels import matches_fuel_type
from backend.jobs.bbm_ocr.receipt_config import SCHEMA_PATH
from backend.jobs.bbm_ocr.receipt_ocr_haiku import ClaudeInterrupted, ClaudeUnavailable, extract_receipts
from backend.jobs.bbm_ocr.receipt_records import reading_rows, submitted_receipts
from backend.jobs.bbm_ocr.receipt_validation import validate_receipts
from backend.jobs.fuel_price import worker as fuel_price_worker
from backend.repositories import ocr_repository
from backend.services import file_storage
from backend.services.file_download import EXTENSIONS

log = logging.getLogger("ocr_worker")

MAX_ATTEMPTS = 3                 # reads of a file that went wrong (timed out, no usable answer)
MAX_SERVICE_ATTEMPTS = 12        # reads while Claude itself could not run, or the file storage was down
STALE_MINUTES = 30               # a file running longer than this lost its worker (the longest read is ~23 minutes)
IDLE_SECONDS = 15                # how often to look for new files when nothing is queued
PAUSE_SECONDS = (60, 15 * 60)    # waiting while Claude or the storage is down: from 1 minute, doubling, up to 15
DATABASE_PAUSE_SECONDS = (5, 60) # waiting while the database can't be used: from 5 seconds, doubling, up to 60


def read_one(task, reader=extract_receipts):
    """Read one claimed file (from ocr_repository.claim_next) and store the outcome. Returns "done", "queued" (tried
    again later), "failed", "unavailable" (Claude or the storage is down: wait before the next file) or "dropped" (the
    file was no longer this worker's when the reading was ready). reader is how the file is read (a fake one in
    tests)."""
    label = f"{task['reimbursement_code']} {task['name']}"
    try:
        data = file_storage.read(task["storage_path"])
    except file_storage.StorageError as error:
        if error.missing:
            return _fail(task, label, str(error), final=True)
        # The storage is down: like Claude being down, wait before the next file
        outcome = _fail(task, label, str(error), limit=MAX_SERVICE_ATTEMPTS)
        return "unavailable" if outcome == "queued" else outcome

    # A folder of its own, the file named by its attachment id (never the caller's file name): Claude's Read tool
    # can open this file only.
    with tempfile.TemporaryDirectory(prefix="ocr-") as folder:
        path = Path(folder) / f"{task['attachment_id']}{EXTENSIONS.get(task['content_type'], '')}"
        path.write_bytes(data)
        try:
            result, usage = reader(path, SCHEMA_PATH)
        except ClaudeInterrupted:
            raise KeyboardInterrupt from None
        except ClaudeUnavailable as error:
            outcome = _fail(task, label, str(error), limit=MAX_SERVICE_ATTEMPTS)
            return "unavailable" if outcome == "queued" else outcome
        except ValueError as error:  # a PDF too large or too long for Claude: reading it again will not help
            return _fail(task, label, str(error), final=True)
        except RuntimeError as error:  # timed out, or no usable answer: maybe better next time
            return _fail(task, label, str(error))

    receipts = result.get("receipts")
    if not isinstance(receipts, list) or not all(isinstance(receipt, dict) for receipt in receipts):
        return _fail(task, label, "The OCR answer has no list of receipts.")
    # The grand total is what was paid for the whole report: it can be checked against its only file only (every item
    # is attached to it then).
    grand_total = task["grand_total"] if task["file_count"] == 1 else None
    validation = validate_receipts(submitted_receipts(task["items"]), receipts, grand_total=grand_total,
                                   names=matches_fuel_type)
    rows = reading_rows(receipts, validation, task["items"])
    if not ocr_repository.save_reading(task, rows, usage["elapsed_seconds"], _tokens(usage)):
        log.warning("%s: read, but no longer this worker's (queued again or deleted); the reading is dropped", label)
        return "dropped"
    log.info("%s: %d receipt(s), %s, %d difference(s) (%.0f s)", label, len(receipts),
             rows["result"]["decision"], len(rows["differences"]), usage["elapsed_seconds"])
    return "done"


def _fail(task, label, error, final=False, limit=MAX_ATTEMPTS):
    """Store a failed attempt: back to the queue, or failed for good (final, or the attempts used up). The website
    names the reason from the error's wording (reimbursement_service.failure_reason): change both together."""
    final = final or task["attempts"] >= limit
    ocr_repository.save_failure(task, error, final)
    log.warning("%s: attempt %d %s: %s", label, task["attempts"], "failed, giving up" if final else "failed", error)
    return "failed" if final else "queued"


def _tokens(usage):
    """The token counts of one read, as ocr_process stores them."""
    cached = int(usage.get("cached_input_tokens", 0))
    return {
        "cached_input_tokens": cached,
        "uncached_input_tokens": int(usage.get("input_tokens", 0)) - cached,
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_tokens": int(usage.get("thinking_tokens", 0)),
    }


def run(once=False, reader=extract_receipts, fuel_prices=True):
    """Read queued files, oldest first, until stopped; with once, stop when nothing is queued (or Claude or the
    storage is down). When the database can't be used (it restarted, the network dropped), wait a little, longer
    each time, and go on (with once: stop with the error); a file being read then is queued again after
    STALE_MINUTES."""
    pause = 0
    database_pause = 0
    while True:
        try:
            outcome = _next_file(once, reader, fuel_prices)
        except Exception as error:
            if once:
                raise
            database_pause = min(max(database_pause * 2, DATABASE_PAUSE_SECONDS[0]), DATABASE_PAUSE_SECONDS[1])
            log.warning("The database can't be used (%s); trying again in %d seconds.", error, database_pause)
            time.sleep(database_pause)
            continue
        database_pause = 0

        if outcome == "nothing":
            if once:
                log.info("Nothing queued.")
                return
            time.sleep(IDLE_SECONDS)
            continue
        if outcome != "unavailable":
            pause = 0
            continue
        if once:
            log.warning("Claude or the file storage is down; stopping (the file stays queued).")
            return
        pause = min(max(pause * 2, PAUSE_SECONDS[0]), PAUSE_SECONDS[1])
        log.warning("Claude or the file storage is down; waiting %d seconds before the next file.", pause)
        time.sleep(pause)


def _next_file(once, reader, fuel_prices=True):
    """Run a queued fuel price refresh (its outcome: "done", "failed" or "unavailable"; not with fuel_prices False);
    or else queue stale files again, then take the next file and read it: its outcome (see read_one), or "nothing"
    when none is queued. A database error is raised (run waits and tries again)."""
    refresh = fuel_price_worker.run_next() if fuel_prices else "nothing"
    if refresh != "nothing":
        return refresh
    stale = ocr_repository.requeue_stale(STALE_MINUTES)
    if stale:
        log.warning("%d file(s) were running for over %d minutes; queued again", stale, STALE_MINUTES)
    task = ocr_repository.claim_next()
    if task is None:
        return "nothing"
    try:
        return read_one(task, reader)
    except KeyboardInterrupt:
        try:
            ocr_repository.release(task)
            log.info("%s %s is back in the queue.", task["reimbursement_code"], task["name"])
        except Exception:  # the database is down too: stop anyway, the file is queued again after STALE_MINUTES
            log.warning("%s %s could not be put back; it is queued again after %d minutes.",
                        task["reimbursement_code"], task["name"], STALE_MINUTES)
        raise
    except Exception as error:  # a bug or the database: count it as an attempt, so one file cannot block the queue
        log.exception("Reading %s %s went wrong", task["reimbursement_code"], task["name"])
        return _fail(task, f"{task['reimbursement_code']} {task['name']}", f"The OCR worker failed: {error}")


def main():
    parser = argparse.ArgumentParser(description="Read the receipt files queued for the OCR.")
    parser.add_argument("--once", action="store_true", help="read what is queued now, then stop")
    parser.add_argument("--retry-failed", action="store_true", help="queue the failed files again first")
    parser.add_argument("--no-fuel-prices", action="store_true",
                        help="don't run the fuel price refreshes (py -m backend.jobs.fuel_price.worker does)")
    args = parser.parse_args()

    # The DB_* settings (and GCS_BUCKET) live in the .env file in the repo root.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.retry_failed:
        log.info("Queued %d failed file(s) again.", ocr_repository.requeue_failed())
    if not args.no_fuel_prices:
        fuel_price_worker.add_products_if_none()  # a first deploy: the fuels the fuel price page lists
    try:
        run(once=args.once, fuel_prices=not args.no_fuel_prices)
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()

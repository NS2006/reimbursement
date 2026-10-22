# Backend

The Python side of the reimbursement review: the **web API** (Flask), the **OCR worker** that reads the receipt files
with Claude, and the **PostgreSQL** schema. Python 3.11; run every command from the repository root.

For what the project does and how to set it up, see the [main README](../README.md).

```bash
py -m backend.app                               # the API on http://127.0.0.1:5000/api
py -m backend.jobs.bbm_ocr.worker               # the OCR worker (keep it running next to the API)
py -m backend.database.reset rebuild            # local database: drop everything, create the tables, seed
```

---

## Layout

```
backend/
├── app.py                 # the Flask app: error answers, gzip of JSON answers, the /api prefix
├── routes.py              # every endpoint: URL -> service function (nothing else)
├── services/              # one file per area: reads the request, applies the rules, answers
│   ├── reimbursement_service.py   #   receiving reports, the list, one report, review statuses
│   ├── report_filter.py           #   the list's filter (month, status, search, sort), shared by list/export/retry
│   ├── review_service.py          #   approve / reject / take back
│   ├── comment_service.py         #   comments
│   ├── ocr_service.py             #   retry the OCR on failed files
│   ├── export_service.py          #   Excel export (bbm_workbook.py builds it, xlsx_style.py styles it)
│   ├── attachment_service.py      #   serve a receipt file
│   ├── file_download.py           #   download a file from another system (allowed hosts, size, type)
│   ├── file_storage.py            #   keep and read files: GCS bucket, or backend/storage/ locally
│   └── auth_service.py, user_service.py, dummy_receipt_service.py, json_values.py
├── repositories/          # all SQL, one file per area (pg8000, no ORM)
├── database/
│   ├── connection.py      # one connection per unit of work, 9-second statement timeout
│   ├── schema.sql         # every table and index
│   ├── seeds/             # sample data for local development (fake people)
│   ├── dummy_bbm_receipt/ # the sample receipt photos the seeds link to
│   └── reset.py           # reseed / rebuild / empty the local database
├── jobs/bbm_ocr/          # the OCR: worker, Claude reader, comparison, and the research pipeline
└── main.py                # the research pipeline's entry point (see "OCR research pipeline")
```

**Layers:** `routes.py` → `services/` → `repositories/`. A route only names its service function, a service never
writes SQL, and a repository never reads the request. There is no `controllers/` folder.

---

## API

Every answer is JSON, except files. Errors are always `{"error": "<code>", "message": "<text for people>"}`, with
the code stable enough to act on (the website translates by it): `400` bad input, `404` unknown report, `409` the data
changed in the meantime, `413` body over 5 MB, `503` the file storage is down, `500` anything else (details only in the
server log).

### For other systems

**`POST /api/reimbursements`**: send up to 100 reports at once. Answers `202`.

```json
{"reimbursements": [{
  "reimbursement_code": "RB-101",
  "reimbursement_type": "bbm",
  "employee": {"employee_no": "EMP-001", "name": "Employee One"},
  "grand_total": 1358170,
  "attachments": [{"name": "1.jpeg", "url": "https://files.example.com/1.jpeg"}],
  "items": [{"item_id": "RB-101-1", "product_name": "pertamina dex", "date_of_expense": "26-05-2026",
             "price_per_liter": 27900, "volume_liter": 48.68, "kilometer": 49532, "total_price": 1358170}]
}]}
```

```json
{"received": 1, "accepted": 1, "rejected": 0,
 "results": [{"index": 0, "reimbursement_code": "RB-101", "status": "created", "revision_no": 1}]}
```

- Each report is checked and saved on its own: one bad report doesn't block the others. Its result is `created`,
  `revised` (a new revision of a known code), `unchanged` (same data and files as its latest revision, so sending
  again is safe) or `rejected` with `errors: [{"field", "message"}]`.
- A BBM report has exactly **one file**, which may show several receipts. `date_of_expense` is `DD-MM-YYYY`;
  `price_per_liter` and `kilometer` are optional.
- The file is downloaded during the request, only from `ATTACHMENT_HOSTS`: a JPEG, PNG, GIF, BMP or PDF of at most
  25 MB (a PDF at most 20 MB, the most the OCR reads). A report whose file can't be downloaded is rejected, to be sent
  again with a new link. If the file storage is down, nothing is saved (`503`).
- The OCR doesn't run here: the new files are queued for the OCR worker.

### For the website

| Method and path | What it does |
|---|---|
| `GET /users`, `POST /auth/login` | The development login: the users to pick from, and checking the picked one |
| `GET /reimbursements` | One page of the list (20 reports), filtered and sorted (see below) |
| `GET /reimbursements/summary` | Reports and amount per month, status and part of it, plus the oldest report needing review (Home, month picker, status cards) |
| `GET /reimbursements/codes` | Every code of a list in order (up to 5,000), for previous / next on a report |
| `GET /reimbursements/<code>` | One report with every revision, its OCR reading, differences, decisions and comments |
| `POST /reimbursements/<code>/decisions` | Approve, reject (reason required) or take back; `409` if someone decided first |
| `POST /reimbursements/<code>/comments`, `PATCH` / `DELETE .../comments/<id>` | Comments; only the author edits or deletes |
| `POST /reimbursements/<code>/ocr/retry` | Queue the report's failed files for the OCR again |
| `POST /reimbursements/ocr/retry` | The same for every report in a list (up to 5,000) |
| `POST /reimbursements/export?type=bbm` | The list as an Excel file (up to 5,000 reports) |
| `GET /attachments/<id>/file` | A receipt file |
| `GET /dummy-receipts/<file>` | Development only: the sample photos the seeds link to (not in the Docker images) |

All paths are under `/api`. The list, codes, summary, export and retry-all take the same filter, as query parameters
or (export and retry-all) as the JSON body:

| Parameter | Values |
|---|---|
| `type` | `bbm` |
| `period` | `all` or a month, `2026-10`: the reports received in that month, **in WIB** for every reviewer |
| `status`, `by` | `all`, `needs_review` (`by`: `differences`, `failed`), `processing`, `approved` (`by`: `matched`, `proceed`, `reviewer`), `rejected` |
| `q` | Search in the code, employee name and employee number |
| `sort` | `received`, `code`, `employee`, `total`, `differences`, `status`; `-` in front for descending (default `-received`) |
| `page` | From 1 (list only) |
| `tz` | The reviewer's offset from UTC in minutes (default 420): only for the times written in the Excel export |

**Who is acting:** for now the website sends the acting user's email with decisions and comments. Before production,
the user must come from the Blibli gateway instead (see the main README).

---

## Review status

Worked out on every read from the OCR results and the decisions, never stored:

1. A reviewer's decision wins (the newest one in force; "take back" removes it).
2. Otherwise a `matched` or `proceed` OCR result approves the revision.
3. A file the OCR flagged, or couldn't read, needs review; a file not read yet is processing.

Every revision is judged on its own, also one sent again after a rejection. A later OCR reading never changes a
reviewer's decision.

---

## OCR worker

```bash
py -m backend.jobs.bbm_ocr.worker                  # keeps running; checks for new files every 15 seconds
py -m backend.jobs.bbm_ocr.worker --once           # reads what is queued now, then stops
py -m backend.jobs.bbm_ocr.worker --retry-failed   # queues the failed files again first
```

- Takes one queued file at a time, reads it with Claude ([receipt_ocr_haiku.py](jobs/bbm_ocr/receipt_ocr_haiku.py),
  through the Claude Code CLI) and stores the reading and the comparison. A file typically takes 15 to 35 seconds.
- **Retries:** a read that times out or gives no usable answer is tried 3 times; when Claude or the file storage is
  down, the worker pauses (1 minute, doubling up to 15) and tries up to 12 times. A missing file or a too-large PDF
  fails at once.
- **Database down:** the worker waits (5 seconds, doubling up to 60) and goes on when the database is back.
- A file left "running" for 30 minutes (a worker that died) is queued again.
- **Why a file failed:** the error is kept in `ocr_reimbursement.error` for developers. The website gets only a
  reason code (`file_missing`, `storage_unavailable`, `pdf_too_large`, `pdf_too_many_pages`, `timed_out`,
  `unreadable`, `ocr_unavailable`, `other`), worked out from that error's wording in
  `reimbursement_service.failure_reason()`. If you reword an error in the worker, update that function too.
- Stop it with Ctrl+C; a file being read is put back in the queue.

---

## How a receipt is compared

[receipt_validation.py](jobs/bbm_ocr/receipt_validation.py) compares the submitted items with the OCR reading:

1. **Pair.** Each submitted receipt is paired with the OCR receipt it resembles most (one-to-one), so a file with
   several receipts works. A receipt found on one side only is flagged.
2. **Compare field by field**, in plain code: names ignore case, spaces and punctuation; dates are parsed; numbers
   have a small tolerance. A receipt without differences is `matched`.
3. **Decide each difference:**

   | What differs | Decision |
   |---|---|
   | One number (liters, price per liter, amount, total, discount) | Explained when only the submitted value fits the receipt's other numbers (an OCR misread); otherwise flagged |
   | Several numbers on one receipt | Flagged: one misread can't explain it |
   | Date, product name, a missing or extra product | Flagged |

4. **Status.** `matched` (no differences), `proceed` (every difference explained) or `needs_review`.

Arithmetic tolerance: liters × price per liter may differ from the amount by 0.5 % (at least 100 rupiah); amounts
minus discount must equal the total within 1 rupiah. Each difference carries a hint for the reviewer. The OCR's
confidence is shown as a hint only and never decides anything.

---

## Database

- **[schema.sql](database/schema.sql)** creates every table and index; the ERD is in `Database Design/` at the
  repository root. There are no migrations yet: after a schema change, rebuild your local database.
- **[reset.py](database/reset.py)** works on a local database only (it refuses any other host) and needs `psql`:

  | Command | What it does |
  |---|---|
  | `py -m backend.database.reset rebuild` | Drop everything, create the tables from `schema.sql`, run every seed |
  | `py -m backend.database.reset reseed` | Empty every table and run the seeds again (tables kept) |
  | `py -m backend.database.reset empty` | Empty every table but `app_user`; reports then only come from the API |

  Add `--yes` to skip the confirmation.
- **Seeds** ([database/seeds/](database/seeds/)) use fake people with `example.com` addresses.
- Every query is cancelled after **9 seconds**, so a slow query can't hold the database.
- Months are worked out in **WIB** (`report_filter.MONTH_ZONE`), the same for every reviewer.

---

## OCR research pipeline

Separate from the running system: a command-line pipeline to measure and tune the OCR on a fixed set of receipt
photos. Its data lives in [jobs/bbm_ocr/](jobs/bbm_ocr/): `images/` (named by id: `1.jpg`, `65.pdf`; only 13
samples are in git), `ground_truth/gt.json` (the correct data per image) and `results/` (what a run writes).

Set `MODE` in [main.py](main.py), then run `py -m backend.main`:

| `MODE` | What it does |
|---|---|
| `extract` | Reads every image with Claude, saves `results/batch_results.json` (costs tokens and takes minutes) |
| `evaluate` | Measures the accuracy against the ground truth, writes `results/evaluation_report/` |
| `validate` | Runs the comparison above with the ground truth as the submitted data |

To compare models or settings, keep each run in `results_<model>/evaluation_report_<effort>_<retries>/` and run
`py backend/jobs/bbm_ocr/comparison.py`. Best so far (63 images, 80 receipts): Claude Opus at effort `max`, and
Claude Haiku at `max` with 1 retry, both **99.29 %** of fields and **95 %** of receipts completely right.

Settings you may tune:

| Setting | Where | Now |
|---|---|---|
| Model, effort, time limit per file | `MODEL`, `EFFORT`, `TIMEOUT_SECONDS` in `receipt_ocr_haiku.py` | `claude-haiku-5-5`, `max`, 300 s |
| Read again when the numbers don't add up | `RETRIES` in `receipt_ocr_haiku.py` | `0` (off) |
| Arithmetic tolerance | `PRODUCT_REL_TOLERANCE`, `PRODUCT_ABS_FLOOR`, `RECEIPT_ABS_TOLERANCE` in `receipt_validation.py` | 0.5 %, 100 rupiah, 1 rupiah |
| PDF limits | `MAX_PDF_PAGES`, `MAX_PDF_BYTES` in `receipt_config.py` | 10 pages, 20 MB |

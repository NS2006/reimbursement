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
│   ├── fuel_price_service.py      #   the fuel prices, and queueing a refresh from the web
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
├── jobs/fuel_price/       # the fuel price refresh from the web: search, page download, checks, worker
└── main.py                # the research pipeline's entry point (see "OCR research pipeline")
```

**Layers:** `routes.py` → `services/` → `repositories/`. A route only names its service function, a service never
writes SQL, and a repository never reads the request. There is no `controllers/` folder.

---

## API

Every answer is JSON, except files. Errors are always `{"error": "<code>", "message": "<text for people>"}`, with
the code stable enough to act on (the website translates by it): `400` bad input, `404` unknown report, `409` the data
changed in the meantime, `413` body over 5 MB (except `POST /api/reimbursements`: any size), `503` the file storage is down, `500` anything else (details only in the
server log).

### For other systems

**`POST /api/reimbursements`**: send any number of reports at once. Answers `202`, after every file is downloaded
and every report saved, so a big batch takes a while; if the caller gives up waiting, sending it again is safe (what
was saved comes back `unchanged`).

```json
{"reimbursements": [{
  "reimbursement_code": "EREP_10101",
  "employee": {"employee_no": "06300001", "name": "Employee One"},
  "grand_total": 1358170,
  "items": [{"item_id": "EXP_10501", "type": "bbm", "date_of_expense": "26-05-2026", "total_price": 1358170,
             "product_name": "Diesel/Dex", "volume_liter": 48.68, "kilometer": 49532,
             "attachments": [{"name": "1.jpeg", "url": "https://files.example.com/1.jpeg"}]}]
}]}
```

```json
{"received": 1, "accepted": 1, "rejected": 0,
 "results": [{"index": 0, "reimbursement_code": "EREP_10101", "status": "created"}]}
```

- Each report is checked and saved on its own: one bad report doesn't block the others. Its result is `created`,
  `unchanged` (the code was sent before with the same data and files, so sending again is safe) or `rejected` with
  `errors: [{"field", "message"}]`.
- **A report is never changed.** Its code sent again with other data, or for another employee, is rejected: a
  corrected report comes under a new code (Darwinbox gives it one).
- Every item has a `type` (only `bbm` so far) and its own `attachments`: at least 1 file, each may show several receipts.
  The same file may be sent with several items: it is read once and compared with all of them.
  `date_of_expense` is `DD-MM-YYYY`; `kilometer` is optional. `product_name` is Darwinbox's fuel type as picked
  (`Pertamax 92`, `Pertalite 90`, `Shell Super 92`, `BP 92`, `BP 90`, `Vivo Ron 92`, `Performa > 92`,
  `Diesel/Dex`). There is no price per liter: the database works it out (`total_price / volume_liter`).
- The files are downloaded during the request, only from `ATTACHMENT_HOSTS`: a JPEG, PNG, GIF, BMP or PDF of any
  size. A report whose file can't be downloaded is rejected, to be sent again with a new link. If the file storage is
  down, nothing is saved (`503`). A PDF the OCR can't read whole (over 20 MB or 10 pages) is stored; its OCR fails and
  the reviewer checks it by hand.
- **No limits for now** (the trial with Darwinbox): any number of reports, files per item and file sizes. They come
  back later.
- The OCR doesn't run here: the new files are queued for the OCR worker.

### For the website

| Method and path | What it does |
|---|---|
| `GET /users`, `POST /auth/login` | The development login: the users to pick from, and checking the picked one |
| `GET /reimbursements` | One page of the list (20 reports), filtered and sorted (see below) |
| `GET /reimbursements/summary` | Reports and amount per month, status and part of it, plus the oldest report needing review (Home, month picker, status cards) |
| `GET /reimbursements/codes` | Every code of a list in order (up to 5,000), for previous / next on a report |
| `GET /reimbursements/<code>` | One report with its items and files (which file each item was sent with), the OCR reading of each file, differences, decisions and comments. Each item has `fuel_price`: the fuel it is (its fuel type, or for `Performa > 92` and `Diesel/Dex` the name on its receipt: `from_receipt`) with the fuel price page's price `today` and `on_date` (its date); `null` when the fuel can't be told. `same_receipt`: the other reports claiming the same receipt, each with its `kind` (see [Same receipt](#same-receipt-double-claims)), status, decision, the files with the same content (`files`) and the day, amount and volume both have (`numbers`); `double_claim`: one of them is a double claim |
| `POST /reimbursements/<code>/decisions` | Approve, reject (reason required) or take back; `409` if someone decided first |
| `POST /reimbursements/<code>/comments`, `PATCH` / `DELETE .../comments/<id>` | Comments; only the author edits or deletes |
| `POST /reimbursements/<code>/ocr/retry` | Queue the report's failed files for the OCR again |
| `POST /reimbursements/ocr/retry` | The same for every report in a list (up to 5,000) |
| `POST /reimbursements/export` | The list as an Excel file (up to 5,000 reports) |
| `GET /attachments/<id>/file` | A receipt file |
| `GET /fuel-prices` | Every active fuel with its DKI Jakarta price per liter today (`price`, with its source), the different price before it (`previous`), the nearest price announced for a later day (`upcoming`) and every price change (`history`, newest first; a price equal to the one before it only goes on with it, so it is left out). Days are WIB (`today`). Each price says which refresh from the web stored it (`fuel_price_run_id`; empty for manual and seeded ones). Also the last refresh from the web (the prices it did not use, and why) and when the refresh button can be pressed again (a day after the last refresh) |
| `POST /fuel-prices/refresh` | Queue a refresh of the fuel prices from the web (`{"user_email"}`): `201` with `{run}`; `409 refresh_active` while one is queued or running; `429 refresh_too_soon` (with `next_refresh_at`) within a day of the last refresh; `400 invalid_user` |
| `GET /dummy-receipts/<file>` | Development only: the sample photos the seeds link to (not in the Docker images) |

All paths are under `/api`. The list, codes, summary, export and retry-all take the same filter, as query parameters
or (export and retry-all) as the JSON body:

| Parameter | Values |
|---|---|
| `period` | `all` or a month, `2026-10`: the reports received in that month, **in WIB** for every reviewer |
| `status`, `by` | `all`, `needs_review` (`by`: `duplicate`, `differences`, `failed`), `processing`, `approved` (`by`: `matched`, `proceed`, `reviewer`), `rejected` |
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
2. Otherwise a `matched` or `proceed` OCR result approves the report.
3. A file the OCR flagged, or couldn't read, needs review; a file not read yet is processing.

A later OCR reading never changes a reviewer's decision.

---

## OCR worker

```bash
py -m backend.jobs.bbm_ocr.worker                  # keeps running; checks for new files every 15 seconds
py -m backend.jobs.bbm_ocr.worker --once           # reads what is queued now, then stops
py -m backend.jobs.bbm_ocr.worker --retry-failed   # queues the failed files again first
py -m backend.jobs.bbm_ocr.worker --no-fuel-prices # leaves the fuel price refreshes to their own worker (below)
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
- Before its next file, it runs a queued fuel price refresh (below), unless started with `--no-fuel-prices`.

---

## Fuel price refresh

The website's "Update from the web" button (`POST /fuel-prices/refresh`) and a new batch of reports queue a refresh
(`fuel_price_run`, one at a time), at most one a day: neither queues one within a day of the last refresh, whichever
started it (the button answers `429 refresh_too_soon`; the reports are stored anyway). The OCR worker runs it before its next file, or run it alone (VS
Code's Ctrl+Shift+B does, next to `--no-fuel-prices` for the OCR worker):

```bash
py -m backend.jobs.fuel_price.worker               # keeps running; checks for a queued refresh every 30 seconds
py -m backend.jobs.fuel_price.worker --once        # runs the queued refresh, if any, then stops
```

The fuels it looks for are the active rows of `fuel_product`. On a first deploy, when the table has no row at all,
the worker inserts them from [seeds/fuel_product.sql](database/seeds/fuel_product.sql) (the 19 fuels of Pertamina,
Shell, BP and Vivo): when it starts (the OCR worker too, unless `--no-fuel-prices`) and before each refresh. A table
with products, even only inactive ones, is left as it is. The prices start empty: the first refresh fills them.

1. **The merchants' own price lists.** Pertamina's and Shell's price pages draw their list with JavaScript, so the
   job downloads the data they draw it from ([sources.py](jobs/fuel_price/sources.py) `OFFICIAL_LISTS`: Pertamina's
   price data by province, Shell's page data). [page_fetch.py](jobs/fuel_price/page_fetch.py) turns the JSON into
   one line per product (with its province) and Claude reads it like an article (step 4), so a change of its layout
   doesn't break the job. A product the list gives without a price (`0`), or leaves out, is stored as not listed
   (out of stock; "Tidak tercantum" on the website). BP's page refuses a download and Vivo's site doesn't answer.
2. **The news, for the rest:** the products no list settled (BP's, Vivo's, a product Claude missed on a list, and all
   of a merchant's when its list can't be downloaded or read). Claude Haiku, with web search only (low effort, at
   most 2 searches: each costs $0.01), finds articles of the last 60 days about their prices on the six listed news
   sites (Kompas, detik, CNBC Indonesia, Liputan6, Antara, Katadata): up to 12, at most 2 of a site. Up to 6 are
   read; an article whose page says it was published over 60 days ago (its `datePublished` or publish-date meta tag)
   is skipped before Claude reads it, and the next one is read instead.
3. The job downloads each page itself (page_fetch.py: https and listed sites only, public addresses only, the
   address looked up once and connected to, up to 3 redirects, 4 MB, 30 seconds; HTML, text or JSON).
4. Claude, with no tools, reads each page's text and gives the prices with a sentence (or a line of the list) copied
   from it. (Claude's own page tool shows it a summary of the page, so the sentences it quoted from it couldn't be
   found on the page.)
5. [price_checks.py](jobs/fuel_price/price_checks.py) checks every price: the sentence is on the page, gives the
   price and names the product (not Pertashop's or non-subsidised Biosolar); a line of Pertamina's list names
   Jakarta; a whole number from Rp 5.000 to Rp 60.000; the day it starts at most 60 days back and 31 ahead. A new
   price is stored only when the page says from which day, two different news sites give the same price from the
   same day (or the merchant's own list or site gives it), and it doesn't replace a manual price, or an official one
   with one from the news. A price that only confirms the stored one changes nothing. An article that gives a price
   without saying from which day counts it from the day it was published: such a price is stored once two different
   sites give it, from the day the second of them gave it (later than the real start, at worst, never earlier).
   "Not listed" comes only from a list read well (a price on it passed), and never for a product the list still
   shows with a price.
6. The run keeps how many products a price was found for, how many prices were stored, the prices not used with a
   reason code (`one_site_only`, `quote_not_on_page`, `region_not_in_quote`, `no_start_date`, ...), and the tokens
   and web searches. A run costs about $0.03 (one search, two lists, a few articles).

- **Failed runs:** `claude_unavailable`, `timeout`, `no_answer`, `over_budget` (the search, when no list was read
  either; otherwise the lists' prices are still stored), `no_articles` (no list or article could be downloaded or
  read), `worker_error`; a refresh no worker took in 2 hours fails as `not_started`, one running for over 40 minutes
  as `stale`. The website explains each.
- Stop it with Ctrl+C; the refresh goes back to the queue.

---

## How a receipt is compared

[receipt_validation.py](jobs/bbm_ocr/receipt_validation.py) compares each file the OCR read with the items it was
sent with (each item is one receipt):

1. **Pair.** Each submitted receipt is paired with the OCR receipt it resembles most (one-to-one), so a file with
   several receipts works. A receipt found on one side only is flagged.
2. **Compare field by field**, in plain code: dates are parsed; numbers have a small tolerance. The product is
   Darwinbox's fuel type, matched with the names receipts print for it
   ([product_labels.py](jobs/bbm_ocr/product_labels.py): `Pertamax 92` is `PERTAMAX`, `Diesel/Dex` is any diesel,
   `Performa > 92` is any fuel above RON 92, ...), ignoring case, spaces and punctuation; anything else read with the
   name is flagged. The price per liter isn't submitted: the amount ÷ the volume is compared with the price on the
   receipt instead (not when the OCR read no price: the MyPertamina app's screen shows none). A receipt without
   differences is `matched`.
3. **Decide each difference:**

   | What differs | Decision |
   |---|---|
   | One number (liters, amount, total, discount) | Explained when only the submitted value fits the receipt's other numbers (an OCR misread; the price per liter used is the one on the receipt); otherwise flagged |
   | Price per liter (the amount ÷ the volume against the receipt's, while liters and amount agree) | Flagged: an OCR misread of the price and an amount or volume changed on the receipt look the same |
   | Several numbers on one receipt | Flagged: one misread can't explain it |
   | Date, product name, a missing or extra product | Flagged |

4. **Status.** `matched` (no differences), `proceed` (every difference explained) or `needs_review`. When a report
   has one file, the file's total is also checked against the grand total (what was paid), and an approval needs the
   receipts' numbers to back the amount claimed.

### Same receipt (double claims)

Darwinbox gives a resubmitted report a new code and nothing that links it to the old one, and its weekly batches can
overlap. So every report is checked against every other report for the same receipt (`receipt_matches` in
[schema.sql](database/schema.sql)):

- **The same file**: an attachment with the same SHA-256, whoever sent it.
- **The same data**: the same employee's receipt with the same day, amount and volume, as submitted or as any OCR
  reading of its file read them (with the item's day too, as the OCR may misread a date). A new photo of the same
  receipt has another SHA-256, but the same numbers.

A match never stops being true (files, items and readings are never changed), so it is found once and stored, both
ways round, in `same_receipt` (`store_receipt_matches`): when a report arrives (`POST /reimbursements`) and when the
OCR worker saves a reading, in the same transaction, one at a time (a report and a reading of the same receipt saved
at the same moment still find each other). The lists then only read the pairs. What the other report is depends on
the decisions, so that is worked out on every read:

What the other report is to this one (`kind`; "earlier" is received before, or at the same time with a lower code):

| `kind` | Meaning |
|---|---|
| `double_claim` | Earlier, and not a resubmission: this report needs review whatever the OCR found (`by=duplicate`), unless a reviewer decided |
| `resubmission` | Earlier, the same employee's report with a rejection in force: this one sends the receipt again (not flagged) |
| `claimed_again` | Later, claiming it again (flagged there) |
| `resubmitted` | Later, the same employee resending this rejected report |

A decision on the other report changes the kind (rejecting it turns a double claim into a resubmission; taking the
rejection back turns it into a double claim again); a reviewer's decision on this one still stays final.

Arithmetic tolerance: liters × price per liter may differ from the amount by 0.5 % (at least 100 rupiah), and the
amount ÷ the volume from the price per liter by 0.5 % (at least 1 rupiah); amounts minus discount must equal the
total within 1 rupiah. Each difference carries a hint for the reviewer. The OCR's
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
  | `py -m backend.database.reset empty` | Empty every table but `app_user`, like a first deploy: reports then only come from the API; the fuel price worker adds the fuels again (when it starts, or before its next refresh) and their prices from "Update from the web" |

  Add `--yes` to skip the confirmation.
- **The same receipt in several reports** is stored by the API and the OCR worker as data comes in (see
  [Same receipt](#same-receipt-double-claims)). Data inserted another way (the seeds, SQL by hand) needs the pairs
  stored afterwards: [seeds/same_receipt.sql](database/seeds/same_receipt.sql) runs last and does it for every report;
  run `SELECT store_receipt_matches(NULL);` in psql to rebuild them on any database (it only adds what is missing;
  about 6 seconds with five years of reports, so not through the API, which stops queries after 9 seconds).
- **Seeds** ([database/seeds/](database/seeds/)): [fuel_product.sql](database/seeds/fuel_product.sql) (the fuels;
  real data, also inserted by the fuel price worker on a first deploy) and
  [fuel_price.sql](database/seeds/fuel_price.sql) (their price history) are real; the others use fake people with `example.com` addresses, and codes in
  Darwinbox's format: reports `EREP_<number>`, items `EXP_<number>`. The hand-made reports (EREP_10001 ..
  EREP_10082; EREP_10073 onwards are corrected reports sent again under a new code) cover every case; [dummy_month.sql](database/seeds/dummy_month.sql) adds a full month on top: 800
  reports (EREP_11001 .. EREP_11800) received in September 2026 in four weekly batches, copied from the hand-made ones
  with their OCR results and decisions, to see the website and the queries at a real month's volume.
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

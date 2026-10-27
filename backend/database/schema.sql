-- Reimbursement database (PostgreSQL 15), from Database Design/Reimbursement ERD.
-- Run once on an empty database. One transaction: every table is created, or none.
BEGIN;

-- OCR confidence: 0.000 to 1.000
CREATE DOMAIN confidence AS numeric(4,3) CHECK (VALUE BETWEEN 0 AND 1);

-- Text sorted with the numbers in it by value (EREP_2 before EREP_10), as people expect: the report list's code and
-- employee sorts. ICU comes with PostgreSQL (Cloud SQL too).
CREATE COLLATION natural_sort (provider = icu, locale = 'und-u-kn-true');

-- ---------- people ----------
CREATE TABLE app_user (                          -- "user" is reserved in PostgreSQL
    email  varchar(255) PRIMARY KEY,
    name   varchar(255) NOT NULL
);

CREATE TABLE employee (
    employee_no  varchar(50)  PRIMARY KEY,
    name         varchar(255) NOT NULL
);

-- ---------- what the employee submitted ----------
-- A report is stored once, as it was sent, and never changed. There are no revisions: a rejected report is submitted
-- again in the other system under a new code. The same code sent again with the same data (the same payload_hash) is
-- a retry and stores nothing; with different data it is refused.
CREATE TABLE reimbursement_report (
    reimbursement_code  varchar(50)   PRIMARY KEY,
    employee_no         varchar(50)   NOT NULL REFERENCES employee (employee_no),
    grand_total         numeric(14,2) NOT NULL CHECK (grand_total >= 0),
    received_at         timestamptz   NOT NULL DEFAULT now(),
    payload_hash        varchar(64)   NOT NULL                                 -- SHA-256 of the sent data; same hash = a retry
);

-- An item of type "bbm": one fuel receipt. A report's items may be of different types, each in its own table.
CREATE TABLE bbm_receipt (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reimbursement_code  varchar(50)   NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    item_id             varchar(50)   NOT NULL,                                -- the caller's id, unique within a report
    product_name        varchar(255)  NOT NULL,                                -- the caller's fuel type as sent: Pertamax 92, BP 92, Diesel/Dex, ...
    date_of_expense     date          NOT NULL,
    price_per_liter     numeric(12,2) GENERATED ALWAYS AS (round(total_price / volume_liter, 2)) STORED,  -- not sent
    volume_liter        numeric(10,3) NOT NULL CHECK (volume_liter > 0),
    kilometer           integer,                                               -- optional
    total_price         numeric(14,2) NOT NULL CHECK (total_price >= 0),
    UNIQUE (reimbursement_code, item_id)
);

-- An item's files (its receipt photo or PDF). The other system's link expires (Darwinbox's after 10 minutes), so the
-- file is downloaded when the report arrives and kept in our file storage (backend/services/file_storage.py);
-- everything reads it from storage_path.
CREATE TABLE attachment (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bbm_receipt_id  integer       NOT NULL REFERENCES bbm_receipt (id) ON DELETE CASCADE,
    name            varchar(255)  NOT NULL,
    url             text          NOT NULL,                                    -- the link it was sent with (expired since)
    sha256          varchar(64)   NOT NULL,                                    -- of the file
    storage_path    varchar(1000) NOT NULL,                                    -- gs://<bucket>/attachments/<sha256>.<ext>
    content_type    varchar(100)  NOT NULL                                     -- image/jpeg, application/pdf, ...
);

CREATE TABLE comment (                           -- the reviewers' discussion of a report
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reimbursement_code  varchar(50)  NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    user_email          varchar(255) NOT NULL REFERENCES app_user (email),
    description         text         NOT NULL,
    created_at          timestamptz  NOT NULL DEFAULT now(),
    edited_at           timestamptz                          -- empty until edited
);

-- ---------- what the reviewer decided ----------
-- A matched or proceed report is approved by its OCR result; a reviewer approves or rejects the others, and can
-- reject any report. Every decision is a new row (rows are never changed or deleted), so the history stays:
-- the newest row of a report is its decision, and "reopened" takes the decision back.
CREATE TABLE review_decision (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reimbursement_code  varchar(50)  NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    decision            varchar(20)  NOT NULL CHECK (decision IN ('approved', 'rejected', 'reopened')),
    reason              text,                                                  -- why; required to reject
    user_email          varchar(255) NOT NULL REFERENCES app_user (email),
    decided_at          timestamptz  NOT NULL DEFAULT now(),
    CHECK (decision <> 'rejected' OR btrim(coalesce(reason, '')) <> '')
);

-- ---------- what the OCR read ----------
-- One OCR process per call to POST /api/reimbursements that stored new reports: the call queues their files, and the
-- OCR worker (backend/jobs/bbm_ocr/worker.py) reads them one by one.
CREATE TABLE ocr_process (
    id                     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cached_input_tokens    integer     NOT NULL DEFAULT 0,
    uncached_input_tokens  integer     NOT NULL DEFAULT 0,
    output_tokens          integer     NOT NULL DEFAULT 0,
    reasoning_tokens       integer     NOT NULL DEFAULT 0,
    total_images           integer     NOT NULL DEFAULT 0,               -- files queued
    processed_at           timestamptz NOT NULL DEFAULT now(),           -- when the call queued them
    finished_at            timestamptz                                   -- empty while a file is queued or being read
);

-- One file to read: queued with its report, then running, then done (decision and reading filled in) or failed
-- (tried too often, or a file the OCR cannot read at all). A failed attempt goes back to the queue until then.
CREATE TABLE ocr_reimbursement (
    id                      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ocr_process_id          integer       NOT NULL REFERENCES ocr_process (id),
    attachment_id           integer       NOT NULL REFERENCES attachment (id) ON DELETE CASCADE,
    status                  varchar(20)   NOT NULL DEFAULT 'queued'
                                          CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts                integer       NOT NULL DEFAULT 0 CHECK (attempts >= 0),   -- reads started
    error                   text,                                                     -- why the last attempt failed
    started_at              timestamptz,                                              -- when the last attempt started
    decision                varchar(20)   CHECK (decision IN ('matched', 'proceed', 'needs_review')),
    elapsed_seconds         numeric(10,3),
    grand_total             numeric(14,2),
    confidence_grand_total  confidence,
    CHECK ((status = 'done') = (decision IS NOT NULL AND elapsed_seconds IS NOT NULL AND started_at IS NOT NULL))
);

CREATE TABLE ocr_bbm_receipt (
    id                          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ocr_reimbursement_id        integer NOT NULL REFERENCES ocr_reimbursement (id) ON DELETE CASCADE,
    product_name                varchar(255),
    date_of_expense             varchar(100),        -- DD-MM-YYYY as the OCR read it (can be misread)
    price_per_liter             numeric(12,2),
    volume_liter                numeric(10,3),
    total_price                 numeric(14,2),
    discount                    numeric(14,2),
    confidence_product_name     confidence,
    confidence_date_of_expense  confidence,
    confidence_price_per_liter  confidence,
    confidence_volume_liter     confidence,
    confidence_total_price      confidence,
    confidence_discount         confidence
);

CREATE TABLE ocr_difference (
    id                    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ocr_reimbursement_id  integer     NOT NULL REFERENCES ocr_reimbursement (id) ON DELETE CASCADE,
    ocr_item_id           integer     REFERENCES ocr_bbm_receipt (id) ON DELETE CASCADE,
    bbm_receipt_id        integer     REFERENCES bbm_receipt (id) ON DELETE CASCADE,  -- the submitted item it was compared with
    field_name            varchar(50) NOT NULL,
    ocr_value             text,
    submitted_value       text,
    description           text        NOT NULL,
    -- When it was the only number that differed, the other numbers on the receipt decide which value is right
    -- (volume x price = amount; the amounts minus the discounts = the grand total): the side that does not fit them
    -- (NULL when they could not decide, or for a difference that is not such a number) and the value they give.
    likely_wrong          varchar(10) CHECK (likely_wrong IN ('submitted', 'ocr')),
    expected_value        numeric(16,3),
    CHECK (likely_wrong IS NOT NULL OR expected_value IS NULL)
);

-- ---------- the same receipt in several reports ----------
-- Two reports claiming the same receipt (see receipt_matches below), stored both ways round. Found once: when a report
-- arrives and when the OCR saves a reading of one of its files (store_receipt_matches), as files, items and readings
-- are never changed. What the other report is to a report (a double claim, a resubmission, ...) depends on the
-- reviewers' decisions, so it is worked out when read (reimbursement_repository).
CREATE TABLE same_receipt (
    reimbursement_code  varchar(50) NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    other_code          varchar(50) NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    PRIMARY KEY (reimbursement_code, other_code),
    CHECK (other_code <> reimbursement_code)
);

-- ---------- fuel prices ----------
-- The fuels each merchant sells and their Jakarta prices, shown on the website. No report table refers to them. The
-- other system's fuel types (bbm_receipt.product_name) map to these products in code (CLAIM_FUEL_TYPES).
CREATE TABLE fuel_product (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant   varchar(20)  NOT NULL CHECK (merchant IN ('pertamina', 'shell', 'bp', 'vivo')),
    name       varchar(100) NOT NULL,                  -- as the merchant writes it: Pertamax, Shell V-Power, Revvo 92, ...
    fuel_kind  varchar(10)  NOT NULL CHECK (fuel_kind IN ('gasoline', 'diesel')),
    ron        integer      CHECK (ron > 0),           -- octane for gasoline, empty for diesel
    active     boolean      NOT NULL DEFAULT true,     -- false once the merchant stops selling it (never deleted)
    UNIQUE (merchant, name)
);

-- A refresh of the prices from the web, queued by the website's button or by a new batch of reports, and run by the
-- OCR worker: Claude searches the merchants' own pages and news sites, and code checks every price before storing it.
-- One refresh at a time (the unique index below).
CREATE TABLE fuel_price_run (
    id                     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger                varchar(10)  NOT NULL CHECK (trigger IN ('button', 'batch')),
    requested_by           varchar(255) REFERENCES app_user (email),          -- who pressed the button; empty for a batch
    status                 varchar(10)  NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    requested_at           timestamptz  NOT NULL DEFAULT now(),
    started_at             timestamptz,
    finished_at            timestamptz,
    error                  text,                                              -- why it failed
    prices_found           integer      CHECK (prices_found >= 0),            -- the prices Claude gave
    prices_stored          integer      CHECK (prices_stored >= 0),           -- the new or changed ones stored
    rejected_prices        jsonb,                                             -- the ones the checks refused, and why
    cached_input_tokens    integer      NOT NULL DEFAULT 0,
    uncached_input_tokens  integer      NOT NULL DEFAULT 0,
    output_tokens          integer      NOT NULL DEFAULT 0,
    reasoning_tokens       integer      NOT NULL DEFAULT 0,
    web_searches           integer      NOT NULL DEFAULT 0,
    CHECK ((trigger = 'button') = (requested_by IS NOT NULL)),
    CHECK (status = 'queued' OR started_at IS NOT NULL),
    CHECK ((status IN ('done', 'failed')) = (finished_at IS NOT NULL)),
    CHECK (status <> 'failed' OR error IS NOT NULL)
);

-- A price change adds a row; older rows stay as the history. A product's price on a day is its row with the latest
-- valid_from up to that day. One row per product and day: a price from the merchant's own page replaces one from the
-- news, and a manual one is never replaced.
CREATE TABLE fuel_price (
    id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fuel_product_id    integer       NOT NULL REFERENCES fuel_product (id),
    valid_from         date          NOT NULL,
    price_per_liter    numeric(12,2) CHECK (price_per_liter > 0),   -- empty: not sold or not listed from valid_from on
    source             varchar(10)   NOT NULL CHECK (source IN ('official', 'news', 'manual')),  -- official: the merchant's page
    source_url         varchar(2000),
    source_text        varchar(500),                                -- the sentence on that page that gives the price
    fetched_at         timestamptz   NOT NULL DEFAULT now(),
    fuel_price_run_id  integer       REFERENCES fuel_price_run (id),  -- the refresh that stored it; empty for manual and seeded rows
    UNIQUE (fuel_product_id, valid_from),
    CHECK (source <> 'manual' OR fuel_price_run_id IS NULL)
);

-- PostgreSQL does not index foreign keys automatically; these keep joins fast.
-- (bbm_receipt.reimbursement_code and fuel_price.fuel_product_id are already covered by their UNIQUE constraints.)
CREATE INDEX ON reimbursement_report (employee_no);
CREATE INDEX ON attachment (bbm_receipt_id);
CREATE INDEX ON comment (reimbursement_code);
CREATE INDEX ON review_decision (reimbursement_code, decided_at DESC, id DESC);   -- also: the newest decision of a report
CREATE INDEX ON ocr_reimbursement (ocr_process_id);
CREATE INDEX ON ocr_reimbursement (id) WHERE status IN ('queued', 'running');   -- the OCR worker's queue
CREATE INDEX ON ocr_reimbursement (attempts, id) WHERE status = 'queued';    -- the order the worker takes files in
CREATE INDEX ON ocr_reimbursement (attachment_id, id DESC);                -- also: the newest OCR row of a file
CREATE INDEX ON ocr_bbm_receipt (ocr_reimbursement_id);
CREATE INDEX ON ocr_difference (ocr_reimbursement_id);
CREATE INDEX ON ocr_difference (ocr_item_id);
CREATE INDEX ON ocr_difference (bbm_receipt_id);

-- One fuel price refresh at a time: a second one can't be queued while one is queued or running.
CREATE UNIQUE INDEX ON fuel_price_run ((true)) WHERE status IN ('queued', 'running');

-- Newest first: the reports received (the lists).
CREATE INDEX ON reimbursement_report (received_at DESC);

-- Other reports claiming the same receipt (receipt_matches): a file with the same content. (The same data is looked up
-- by the employee: reimbursement_report (employee_no).)
CREATE INDEX ON attachment (sha256);
CREATE INDEX ON same_receipt (other_code);

-- ---------- finding the same receipt in several reports ----------
-- In the database, so every way reports and readings come in uses the same check: the website's API and the OCR
-- worker (reimbursement_repository, ocr_repository), the seeds and a manual rebuild (SELECT store_receipt_matches(NULL)).

-- The other reports claiming the same receipt as each report of `codes` (every report when codes is NULL), and how:
--   file  a file with the same content (the same SHA-256), whoever sent it; file_name: this report's name of it
--   data  the same employee's receipt with the same day, amount and volume: as submitted, or as any OCR reading of its
--         file read them (with the item's day too, as the OCR may misread a date). A new photo of the same receipt
--         has another SHA-256, but the same numbers.
-- One row per report, other report and what both have (day as DD-MM-YYYY text, as the OCR stores it). The website's
-- report page shows these (reimbursement_repository.find_same_receipt).
CREATE FUNCTION receipt_matches(codes varchar[])
RETURNS TABLE (reimbursement_code varchar, other_code varchar, how text, file_name varchar, day text,
               amount numeric, volume numeric)
LANGUAGE sql STABLE AS $$
    WITH scope AS (
        SELECT r.reimbursement_code, r.employee_no
        FROM reimbursement_report r
        WHERE codes IS NULL OR r.reimbursement_code = ANY (codes)
    ),
    receipt_keys AS MATERIALIZED (   -- every receipt of the scope's employees as day, amount and volume
        SELECT r.reimbursement_code, r.employee_no, to_char(i.date_of_expense, 'DD-MM-YYYY') AS day,
               i.total_price AS amount, i.volume_liter AS volume
        FROM reimbursement_report r
        JOIN bbm_receipt i ON i.reimbursement_code = r.reimbursement_code
        WHERE r.employee_no IN (SELECT employee_no FROM scope)
        UNION
        SELECT r.reimbursement_code, r.employee_no, d.day, l.total_price, l.volume_liter
        FROM reimbursement_report r
        JOIN bbm_receipt i ON i.reimbursement_code = r.reimbursement_code
        JOIN attachment a ON a.bbm_receipt_id = i.id
        JOIN ocr_reimbursement o ON o.attachment_id = a.id
        JOIN ocr_bbm_receipt l ON l.ocr_reimbursement_id = o.id
        CROSS JOIN LATERAL (VALUES (to_char(i.date_of_expense, 'DD-MM-YYYY')), (l.date_of_expense)) d (day)
        WHERE r.employee_no IN (SELECT employee_no FROM scope)
          AND l.total_price IS NOT NULL AND l.volume_liter IS NOT NULL AND d.day IS NOT NULL
    )
    SELECT s.reimbursement_code, i2.reimbursement_code, 'file', a.name, NULL::text, NULL::numeric, NULL::numeric
    FROM scope s
    JOIN bbm_receipt i ON i.reimbursement_code = s.reimbursement_code
    JOIN attachment a ON a.bbm_receipt_id = i.id
    JOIN attachment a2 ON a2.sha256 = a.sha256
    JOIN bbm_receipt i2 ON i2.id = a2.bbm_receipt_id AND i2.reimbursement_code <> s.reimbursement_code
    UNION
    -- all four at once: joined on the numbers first, a few common amounts make thousands of pairs
    SELECT k.reimbursement_code, k2.reimbursement_code, 'data', NULL, k.day, k.amount, k.volume
    FROM receipt_keys k
    JOIN receipt_keys k2 ON k2.employee_no = k.employee_no AND k2.day = k.day AND k2.amount = k.amount
                        AND k2.volume = k.volume AND k2.reimbursement_code <> k.reimbursement_code
    WHERE k.reimbursement_code IN (SELECT reimbursement_code FROM scope)
$$;

-- Store in same_receipt the reports claiming the same receipt as each report of `codes` (every report when codes is
-- NULL), both ways round. Returns how many pairs were new.
CREATE FUNCTION store_receipt_matches(codes varchar[]) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    stored integer;
BEGIN
    -- One at a time, until the transaction ends, so the next one sees what this one saved. Else a report and a
    -- reading of the same receipt saved at the same moment would each miss the other.
    PERFORM pg_advisory_xact_lock(hashtext('store_receipt_matches'));
    WITH found AS (SELECT DISTINCT m.reimbursement_code, m.other_code FROM receipt_matches(codes) m)
    INSERT INTO same_receipt (reimbursement_code, other_code)
    SELECT f.reimbursement_code, f.other_code FROM found f
    UNION
    SELECT f.other_code, f.reimbursement_code FROM found f
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS stored = ROW_COUNT;
    RETURN stored;
END
$$;

COMMIT;

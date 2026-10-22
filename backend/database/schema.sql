-- Reimbursement database (PostgreSQL 15), from Database Design/Reimbursement ERD.
-- Run once on an empty database. One transaction: every table is created, or none.
BEGIN;

-- OCR confidence: 0.000 to 1.000
CREATE DOMAIN confidence AS numeric(4,3) CHECK (VALUE BETWEEN 0 AND 1);

-- Text sorted with the numbers in it by value (RB-2 before RB-10), as people expect: the report list's code and
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
-- A report is sent again when the caller corrects it. Every send is kept as a revision; old revisions are
-- never changed, so each OCR result stays linked to the exact data it was compared with.
CREATE TABLE reimbursement_report (
    reimbursement_code  varchar(50)  PRIMARY KEY,
    employee_no         varchar(50)  NOT NULL REFERENCES employee (employee_no),
    reimbursement_type  varchar(20)  NOT NULL CHECK (reimbursement_type IN ('bbm'))
);

CREATE TABLE reimbursement_revision (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reimbursement_code  varchar(50)   NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    revision_no         integer       NOT NULL CHECK (revision_no > 0),        -- 1, 2, 3 ... the highest is current
    grand_total         numeric(14,2) NOT NULL CHECK (grand_total >= 0),
    received_at         timestamptz   NOT NULL DEFAULT now(),
    payload_hash        varchar(64)   NOT NULL,                                -- SHA-256 of the sent data; same hash = a retry
    UNIQUE (reimbursement_code, revision_no)
);

CREATE TABLE bbm_receipt (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id      integer       NOT NULL REFERENCES reimbursement_revision (id) ON DELETE CASCADE,
    item_id          varchar(50)   NOT NULL,                                   -- the caller's id, unique within a revision
    product_name     varchar(255)  NOT NULL,
    date_of_expense  date          NOT NULL,
    price_per_liter  numeric(12,2),
    volume_liter     numeric(10,3) NOT NULL CHECK (volume_liter > 0),
    kilometer        integer,
    total_price      numeric(14,2) NOT NULL CHECK (total_price >= 0),
    UNIQUE (revision_id, item_id)
);

-- The other system's link expires (Darwinbox's after 10 minutes), so the file is downloaded when the report arrives
-- and kept in our file storage (backend/services/file_storage.py); everything reads it from storage_path.
CREATE TABLE attachment (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id   integer       NOT NULL REFERENCES reimbursement_revision (id) ON DELETE CASCADE,
    name          varchar(255)  NOT NULL,
    url           text          NOT NULL,                                     -- the link it was sent with (expired since)
    sha256        varchar(64)   NOT NULL,                                     -- of the file
    storage_path  varchar(1000) NOT NULL,                                     -- gs://<bucket>/attachments/<sha256>.<ext>
    content_type  varchar(100)  NOT NULL                                      -- image/jpeg, application/pdf, ...
);

CREATE TABLE comment (                           -- on the report, so the discussion carries over to new revisions
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reimbursement_code  varchar(50)  NOT NULL REFERENCES reimbursement_report (reimbursement_code) ON DELETE CASCADE,
    user_email          varchar(255) NOT NULL REFERENCES app_user (email),
    description         text         NOT NULL,
    created_at          timestamptz  NOT NULL DEFAULT now(),
    edited_at           timestamptz                          -- empty until edited
);

-- ---------- what the reviewer decided ----------
-- A matched or proceed revision is approved by its OCR result; a reviewer approves or rejects the others, and can
-- reject any revision. Every decision is a new row (rows are never changed or deleted), so the history stays:
-- the newest row of a revision is its decision, and "reopened" takes the decision back.
CREATE TABLE review_decision (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id  integer      NOT NULL REFERENCES reimbursement_revision (id) ON DELETE CASCADE,
    decision     varchar(20)  NOT NULL CHECK (decision IN ('approved', 'rejected', 'reopened')),
    reason       text,                                                         -- why; required to reject
    user_email   varchar(255) NOT NULL REFERENCES app_user (email),
    decided_at   timestamptz  NOT NULL DEFAULT now(),
    CHECK (decision <> 'rejected' OR btrim(coalesce(reason, '')) <> '')
);

-- ---------- what the OCR read ----------
-- One OCR process per call to POST /api/reimbursements that stored new revisions: the call queues the file of every
-- new revision, and the OCR worker (backend/jobs/bbm_ocr/worker.py) reads them one by one.
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

-- One file to read: queued with the revision, then running, then done (decision and reading filled in) or failed
-- (tried too often, or a file the OCR cannot read at all). A failed attempt goes back to the queue until then.
CREATE TABLE ocr_reimbursement (
    id                      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ocr_process_id          integer       NOT NULL REFERENCES ocr_process (id),
    revision_id             integer       NOT NULL REFERENCES reimbursement_revision (id) ON DELETE CASCADE,
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

-- PostgreSQL does not index foreign keys automatically; these keep joins fast.
-- (reimbursement_revision.reimbursement_code and bbm_receipt.revision_id are already covered by their UNIQUE constraints.)
CREATE INDEX ON reimbursement_report (employee_no);
CREATE INDEX ON attachment (revision_id);
CREATE INDEX ON comment (reimbursement_code);
CREATE INDEX ON review_decision (revision_id, decided_at DESC, id DESC);   -- also: the newest decision of a revision
CREATE INDEX ON ocr_reimbursement (revision_id);
CREATE INDEX ON ocr_reimbursement (ocr_process_id);
CREATE INDEX ON ocr_reimbursement (id) WHERE status IN ('queued', 'running');   -- the OCR worker's queue
CREATE INDEX ON ocr_reimbursement (attempts, id) WHERE status = 'queued';    -- the order the worker takes files in
CREATE INDEX ON ocr_reimbursement (attachment_id, id DESC);                -- also: the newest OCR row of a file
CREATE INDEX ON ocr_bbm_receipt (ocr_reimbursement_id);
CREATE INDEX ON ocr_difference (ocr_reimbursement_id);
CREATE INDEX ON ocr_difference (ocr_item_id);
CREATE INDEX ON ocr_difference (bbm_receipt_id);

-- Newest first: the reports received (the lists).
CREATE INDEX ON reimbursement_revision (received_at DESC, id DESC);

COMMIT;

-- Dummy data: one full month of BBM reports, to see the website (and the database) with a real month's volume.
-- 800 reports, EREP_11001 .. EREP_11800, from 300 employees (06300101 .. 06300400), received in September 2026 the
-- way Darwinbox sends them: one call a week (Monday 09:00 WIB) with that week's 200 reports (the API takes up to 300
-- in one request), so every report of one week has the same received_at:
--   week 1  07-09-2026  EREP_11001 .. EREP_11200
--   week 2  14-09-2026  EREP_11201 .. EREP_11400
--   week 3  21-09-2026  EREP_11401 .. EREP_11600
--   week 4  28-09-2026  EREP_11601 .. EREP_11800
-- Their items are EXP_20001 onwards, numbered across the month like Darwinbox's expense ids.
-- Each report is a copy of one of the hand-made reports (EREP_10001 .. EREP_10082, dummy_reimbursement.sql and
-- dummy_ocr_failure.sql) whose files the OCR has finished: the items with their files, the OCR reading and its
-- differences, and the reviewers' decisions. So the receipts and readings are real ones, and the mix of statuses
-- follows the hand-made reports: mostly approved, some needing review, a few rejected or failed.
-- Copies of a report still waiting for the OCR are not made: the local OCR worker would then read hundreds of files.
-- payload_hash is not the real hash of a sent report (these are never sent again); it only has to be there.
-- Run after the other dummy seeds. Running it again replaces EREP_11000 .. EREP_11999 with a fresh copy.
BEGIN;

-- A previous run: its reports, then its OCR processes (left empty by the reports' delete)
DELETE FROM reimbursement_report WHERE reimbursement_code ~ '^EREP_11[0-9]{3}$';
DELETE FROM ocr_process p
WHERE p.processed_at IN (SELECT timestamptz '2026-09-07 09:00:00+07' + w * interval '7 days' FROM generate_series(0, 3) AS w)
  AND NOT EXISTS (SELECT 1 FROM ocr_reimbursement o WHERE o.ocr_process_id = p.id);

INSERT INTO employee (employee_no, name)
SELECT '0630' || lpad(k::text, 4, '0'), 'Employee ' || k
FROM generate_series(101, 400) AS k
ON CONFLICT (employee_no) DO UPDATE SET name = EXCLUDED.name;

-- The OCR rows of the hand-made reports (one per file read)
CREATE TEMP TABLE month_base_ocr ON COMMIT DROP AS
SELECT i.reimbursement_code, o.id, o.status
FROM ocr_reimbursement o
JOIN attachment a ON a.id = o.attachment_id
JOIN bbm_receipt i ON i.id = a.bbm_receipt_id
WHERE i.reimbursement_code ~ '^EREP_100[0-9]{2}$';

-- The reports to copy: the hand-made reports whose files the OCR has all finished
CREATE TEMP TABLE month_base ON COMMIT DROP AS
SELECT row_number() OVER (ORDER BY r.reimbursement_code COLLATE natural_sort) AS base_no,
       r.reimbursement_code, r.grand_total
FROM reimbursement_report r
WHERE r.reimbursement_code IN (SELECT reimbursement_code FROM month_base_ocr)
  AND r.reimbursement_code NOT IN (SELECT reimbursement_code FROM month_base_ocr WHERE status IN ('queued', 'running'));

-- One OCR process per weekly request
CREATE TEMP TABLE month_process ON COMMIT DROP AS
SELECT w, timestamptz '2026-09-07 09:00:00+07' + w * interval '7 days' AS received_at,
       nextval(pg_get_serial_sequence('ocr_process', 'id')) AS id
FROM generate_series(0, 3) AS w;

-- The copies: report n copies base report (n - 1) mod (number of bases) + 1; new ids taken now, to link the rows
CREATE TEMP TABLE month_report ON COMMIT DROP AS
SELECT n, 'EREP_' || (11000 + n) AS code,
       '0630' || lpad((101 + (n - 1) % 300)::text, 4, '0') AS employee_no,
       b.reimbursement_code AS base_code, b.grand_total, p.id AS process_id, p.received_at,
       (n - 1) % 200 AS place  -- its place in the request: the OCR reads the files one after another
FROM generate_series(1, 800) AS n
JOIN month_base b ON b.base_no = (n - 1) % (SELECT count(*) FROM month_base) + 1
JOIN month_process p ON p.w = (n - 1) / 200;

CREATE TEMP TABLE month_item ON COMMIT DROP AS
SELECT m.n, i.id AS base_id, nextval(pg_get_serial_sequence('bbm_receipt', 'id')) AS id,
       'EXP_' || (20000 + row_number() OVER (ORDER BY m.n, i.id)) AS item_id
FROM month_report m
JOIN bbm_receipt i ON i.reimbursement_code = m.base_code
ORDER BY m.n, i.id;  -- the new ids follow it (a sorted query's nextval runs after the sort)

CREATE TEMP TABLE month_attachment ON COMMIT DROP AS
SELECT mi.n, a.id AS base_id, mi.id AS bbm_receipt_id, nextval(pg_get_serial_sequence('attachment', 'id')) AS id
FROM month_item mi
JOIN attachment a ON a.bbm_receipt_id = mi.base_id
ORDER BY mi.n, a.id;

CREATE TEMP TABLE month_ocr ON COMMIT DROP AS
SELECT ma.n, o.id AS base_id, ma.id AS attachment_id, nextval(pg_get_serial_sequence('ocr_reimbursement', 'id')) AS id
FROM month_attachment ma
JOIN ocr_reimbursement o ON o.attachment_id = ma.base_id
ORDER BY ma.n, o.id;

-- in the base's line order, so a reading's line n stays its n-th row by id
CREATE TEMP TABLE month_line ON COMMIT DROP AS
SELECT mo.n, mo.id AS ocr_id, l.id AS base_id, nextval(pg_get_serial_sequence('ocr_bbm_receipt', 'id')) AS id
FROM month_ocr mo
JOIN ocr_bbm_receipt l ON l.ocr_reimbursement_id = mo.base_id
ORDER BY mo.n, l.id;

INSERT INTO reimbursement_report (reimbursement_code, employee_no, grand_total, received_at, payload_hash)
SELECT code, employee_no, grand_total, received_at, encode(sha256(convert_to('dummy-month ' || code, 'UTF8')), 'hex')
FROM month_report;

INSERT INTO bbm_receipt (id, reimbursement_code, item_id, product_name, date_of_expense, volume_liter, kilometer, total_price)
OVERRIDING SYSTEM VALUE
SELECT mi.id, m.code, mi.item_id, i.product_name, i.date_of_expense, i.volume_liter, i.kilometer, i.total_price
FROM month_item mi
JOIN month_report m USING (n)
JOIN bbm_receipt i ON i.id = mi.base_id;

-- sha256: not the file's own, so the copies of a receipt don't count as the same receipt claimed again
-- (schema.sql receipt_matches); one per file of a copy, so a file sent with several items stays one
INSERT INTO attachment (id, bbm_receipt_id, name, url, sha256, storage_path, content_type)
OVERRIDING SYSTEM VALUE
SELECT ma.id, ma.bbm_receipt_id, a.name, a.url, encode(sha256(convert_to('dummy-month ' || ma.n || ' ' || a.sha256, 'UTF8')), 'hex'),
       a.storage_path, a.content_type
FROM month_attachment ma
JOIN attachment a ON a.id = ma.base_id;

INSERT INTO ocr_process
    (id, cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
OVERRIDING SYSTEM VALUE
SELECT p.id,
       -- the tokens of an average file of the hand-made OCR processes, times the files
       round(f.files * t.cached), round(f.files * t.uncached), round(f.files * t.output), round(f.files * t.reasoning),
       f.files, p.received_at, p.received_at + f.files * interval '30 seconds'
FROM month_process p
JOIN (SELECT m.process_id, count(*) AS files FROM month_ocr mo JOIN month_report m USING (n) GROUP BY m.process_id) f
    ON f.process_id = p.id
CROSS JOIN (SELECT sum(cached_input_tokens)::numeric / sum(total_images) AS cached,
                   sum(uncached_input_tokens)::numeric / sum(total_images) AS uncached,
                   sum(output_tokens)::numeric / sum(total_images) AS output,
                   sum(reasoning_tokens)::numeric / sum(total_images) AS reasoning
            FROM ocr_process WHERE total_images > 0 AND id NOT IN (SELECT id FROM month_process)) t;

INSERT INTO ocr_reimbursement
    (id, ocr_process_id, attachment_id, status, attempts, error, started_at, decision, elapsed_seconds, grand_total,
     confidence_grand_total)
OVERRIDING SYSTEM VALUE
SELECT mo.id, m.process_id, mo.attachment_id, o.status, o.attempts, o.error,
       m.received_at + m.place * interval '30 seconds', o.decision, o.elapsed_seconds, o.grand_total,
       o.confidence_grand_total
FROM month_ocr mo
JOIN month_report m USING (n)
JOIN ocr_reimbursement o ON o.id = mo.base_id;

INSERT INTO ocr_bbm_receipt
    (id, ocr_reimbursement_id, product_name, date_of_expense, price_per_liter, volume_liter, total_price, discount,
     confidence_product_name, confidence_date_of_expense, confidence_price_per_liter, confidence_volume_liter,
     confidence_total_price, confidence_discount)
OVERRIDING SYSTEM VALUE
SELECT ml.id, ml.ocr_id, l.product_name, l.date_of_expense, l.price_per_liter, l.volume_liter, l.total_price, l.discount,
       l.confidence_product_name, l.confidence_date_of_expense, l.confidence_price_per_liter, l.confidence_volume_liter,
       l.confidence_total_price, l.confidence_discount
FROM month_line ml
JOIN ocr_bbm_receipt l ON l.id = ml.base_id;

INSERT INTO ocr_difference
    (ocr_reimbursement_id, ocr_item_id, bbm_receipt_id, field_name, ocr_value, submitted_value, description,
     likely_wrong, expected_value)
SELECT mo.id, ml.id, mi.id, d.field_name, d.ocr_value, d.submitted_value, d.description, d.likely_wrong,
       d.expected_value
FROM month_ocr mo
JOIN ocr_difference d ON d.ocr_reimbursement_id = mo.base_id
LEFT JOIN month_line ml ON ml.n = mo.n AND ml.base_id = d.ocr_item_id
LEFT JOIN month_item mi ON mi.n = mo.n AND mi.base_id = d.bbm_receipt_id
ORDER BY mo.n, d.id;

-- The reviewers' decisions, in their order, a day or two after the report arrived
INSERT INTO review_decision (reimbursement_code, decision, reason, user_email, decided_at)
SELECT m.code, d.decision, d.reason, d.user_email,
       m.received_at + interval '1 day' + row_number() OVER (PARTITION BY m.n ORDER BY d.decided_at, d.id) * interval '2 hours'
FROM month_report m
JOIN review_decision d ON d.reimbursement_code = m.base_code
ORDER BY m.n, d.decided_at, d.id;

-- The other reports claiming the same receipt as a copy (none, as planned: see the sha256 above), as the website's API
-- stores them when a report arrives
SELECT store_receipt_matches(ARRAY(SELECT code FROM month_report)::varchar[]) AS same_receipt_pairs \gset

COMMIT;

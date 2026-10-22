-- Dummy reports whose receipt file the OCR could not read: one per way a read fails, so the website shows each reason
-- and "Retry OCR" can be tried on them. Run after dummy_bbm_ocr.sql, or on its own (e.g. after
-- py -m backend.database.reset empty): it adds its employees itself.
-- Each report is a copy of a seeded report that the OCR matched (same employee, receipt file and values), so a retry
-- reads it and matches; except RB-072, whose file is gone from the file storage, so a retry fails again at once.
--   J  21-10-2026 07:30  RB-069 .. RB-072, 4 files, none read
--   RB-069  3.jpg    (as RB-002)  Claude did not finish within 300 seconds, 3 times
--   RB-070  26.jpeg  (as RB-019)  Claude itself could not run (the API was overloaded), 12 times
--   RB-071  34.jpg   (as RB-030)  Claude answered, but without a usable JSON result, 3 times
--   RB-072  28.jpeg  (as RB-021)  the file is not in the file storage: failed at once (retrying can't help)
-- error and attempts are what the OCR worker (backend/jobs/bbm_ocr/worker.py) stores in each case; the API error of
-- RB-070 is an example. started_at is when the last attempt started: the worker takes the file tried least first, and
-- waits while Claude is down (1 minute, doubling up to 15 when nothing else is left). A failed attempt adds no tokens
-- to its process.
-- payload_hash: computed with reimbursement_service.payload_hash, the same hash POST /api/reimbursements stores.
-- Running it again replaces these 4 reports (their revisions, items, files and OCR rows are deleted with them).
BEGIN;

INSERT INTO employee (employee_no, name) VALUES
    ('EMP-001', 'Employee One'),
    ('EMP-002', 'Employee Two'),
    ('EMP-003', 'Employee Three'),
    ('EMP-006', 'Employee Six')
ON CONFLICT (employee_no) DO UPDATE
    SET name = EXCLUDED.name;

DELETE FROM reimbursement_report WHERE reimbursement_code IN ('RB-069', 'RB-070', 'RB-071', 'RB-072');

-- Processes left without any file (this seeder's process of an earlier run).
DELETE FROM ocr_process p
WHERE NOT EXISTS (SELECT 1 FROM ocr_reimbursement o WHERE o.ocr_process_id = p.id);

INSERT INTO reimbursement_report (reimbursement_code, employee_no, reimbursement_type) VALUES
    ('RB-069', 'EMP-002', 'bbm'),
    ('RB-070', 'EMP-001', 'bbm'),
    ('RB-071', 'EMP-003', 'bbm'),
    ('RB-072', 'EMP-006', 'bbm');

INSERT INTO reimbursement_revision (reimbursement_code, revision_no, grand_total, received_at, payload_hash) VALUES
    ('RB-069', 1, 382225, '2026-10-21 07:30:00+07:00', '318d1505a082498dacad072a5aff0aaeeb7d013d9afcfc2eb32da0dc402ca269'),  -- call J, 3.jpg: correct (as RB-002)
    ('RB-070', 1, 750000, '2026-10-21 07:30:00+07:00', '427514aad9f7343023faf6fe2fff75669404fe32e0b5f04e9fadd959eda84a16'),  -- call J, 26.jpeg: correct (as RB-019)
    ('RB-071', 1, 430000, '2026-10-21 07:30:00+07:00', '9344d1059ae4d7ddd075e5599c4cf491e32a1df4209898f4981cdffdfe3f2b27'),  -- call J, 34.jpg: correct (as RB-030)
    ('RB-072', 1, 200000, '2026-10-21 07:30:00+07:00', 'b7880fcc9530ac42feec1b3ce3bdbab113e62e04075fa37bbba628edb47e57e8');  -- call J, 28.jpeg: correct (as RB-021)

INSERT INTO bbm_receipt (revision_id, item_id, product_name, date_of_expense, price_per_liter, volume_liter, kilometer, total_price)
SELECT r.id, v.item_id, v.product_name, v.date_of_expense::date, v.price_per_liter::numeric, v.volume_liter::numeric,
       v.kilometer, v.total_price::numeric
FROM (VALUES
    ('RB-069', 1, 'RB-069-1', 'bp92', '2026-01-20', 12500, 31.578, 22026, 394725),
    ('RB-070', 1, 'RB-070-1', 'pertamina dex', '2026-01-07', 13600, 55.147, 48157, 750000),
    ('RB-071', 1, 'RB-071-1', 'shell super', '2025-12-17', 13000, 33.07, 36284, 430000),
    ('RB-072', 1, 'RB-072-1', 'pertamax green', '2026-06-27', 17000, 11.765, 20181, 200000)
) AS v (reimbursement_code, revision_no, item_id, product_name, date_of_expense, price_per_liter, volume_liter, kilometer, total_price)
JOIN reimbursement_revision r USING (reimbursement_code, revision_no)
ORDER BY r.id;

-- RB-072's storage_path points to a file that is not there: what the worker finds when a stored file was lost.
INSERT INTO attachment (revision_id, name, url, sha256, storage_path, content_type)
SELECT r.id, v.name, v.url, v.sha256, v.storage_path, v.content_type
FROM (VALUES
    ('RB-069', 1, '3.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/3.jpg', '0d74621b8c2870bc2f07d8222ef392ffbf40d2e8aae897e6346309f1e0196c2f',
     'local:backend/database/dummy_bbm_receipt/3.jpg', 'image/jpeg'),
    ('RB-070', 1, '26.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/26.jpeg', '66937f14456eb31e6ccb93edb398fafe1611cb865f12f73409a5d40cc9654894',
     'local:backend/database/dummy_bbm_receipt/26.jpeg', 'image/jpeg'),
    ('RB-071', 1, '34.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/34.jpg', 'b9a08f1bf01a48970f83d981ceb2af7422868d349c40c629c5acb01130197f06',
     'local:backend/database/dummy_bbm_receipt/34.jpg', 'image/jpeg'),
    ('RB-072', 1, '28.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/28.jpeg', 'e03503b78314fbaf153929bf5b5060b38b20b633ed556988dc901b9d5a71ee1b',
     'local:backend/database/dummy_bbm_receipt/lost/28.jpeg', 'image/jpeg')
) AS v (reimbursement_code, revision_no, name, url, sha256, storage_path, content_type)
JOIN reimbursement_revision r USING (reimbursement_code, revision_no)
ORDER BY r.id;

-- process J: 4 files, all failed (the last one 09:05:46, after RB-070's 12th try)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (0, 0, 0, 0, 4, '2026-10-21 07:30:00.000+07:00', '2026-10-21 09:05:46.303+07:00')
    RETURNING id
)
INSERT INTO ocr_reimbursement (ocr_process_id, revision_id, attachment_id, status, attempts, error, started_at)
SELECT p.id, r.id, a.id, 'failed', v.attempts, v.error, v.started_at::timestamptz
FROM p, (VALUES
    ('RB-069', 3, 'Claude did not finish within 300 seconds.', '2026-10-21 07:43:33.062+07:00'),
    ('RB-070', 12, E'Claude execution failed:\nAPI Error: 529 Overloaded', '2026-10-21 09:05:43.185+07:00'),
    ('RB-071', 3, E'Claude completed successfully, but no valid JSON result could be extracted from its response.\nClaude stderr:\n',
     '2026-10-21 07:49:36.434+07:00'),
    ('RB-072', 1, 'local:backend/database/dummy_bbm_receipt/lost/28.jpeg is not in the local file storage.',
     '2026-10-21 07:36:48.019+07:00')
) AS v (reimbursement_code, attempts, error, started_at)
JOIN reimbursement_revision r ON r.reimbursement_code = v.reimbursement_code AND r.revision_no = 1
JOIN attachment a ON a.revision_id = r.id
ORDER BY a.id;

COMMIT;

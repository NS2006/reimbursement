-- Dummy reports whose receipt file the OCR could not read: one per way a read fails, so the website shows each reason
-- and "Retry OCR" can be tried on them. Run after dummy_bbm_ocr.sql, or on its own (e.g. after
-- py -m backend.database.reset empty): it adds its employees itself.
-- Each report is a copy of a seeded report that the OCR matched (same employee, receipt file and values), so a retry
-- reads it and matches; except EREP_10072, whose file is gone from the file storage, so a retry fails again at once.
-- Being copies, they also claim those receipts a second time: they need a reviewer as possible double claims too.
--   J  21-10-2026 07:30  EREP_10069 .. EREP_10072, 4 files, none read
--   EREP_10069  3.jpg    (as EREP_10002)  Claude did not finish within 300 seconds, 3 times
--   EREP_10070  26.jpeg  (as EREP_10019)  Claude itself could not run (the API was overloaded), 12 times
--   EREP_10071  34.jpg   (as EREP_10030)  Claude answered, but without a usable JSON result, 3 times
--   EREP_10072  28.jpeg  (as EREP_10021)  the file is not in the file storage: failed at once (retrying can't help)
-- error and attempts are what the OCR worker (backend/jobs/bbm_ocr/worker.py) stores in each case; the API error of
-- EREP_10070 is an example. started_at is when the last attempt started: the worker takes the file tried least first,
-- and waits while Claude is down (1 minute, doubling up to 15 when nothing else is left). A failed attempt adds no
-- tokens to its process.
-- payload_hash: the hash POST /api/reimbursements stores (reimbursement_service.payload_hash), as in
-- dummy_reimbursement.sql.
-- Running it again replaces these 4 reports (their items, files and OCR rows are deleted with them).
BEGIN;

INSERT INTO employee (employee_no, name) VALUES
    ('06300001', 'Employee One'),
    ('06300002', 'Employee Two'),
    ('06300003', 'Employee Three'),
    ('06300006', 'Employee Six')
ON CONFLICT (employee_no) DO UPDATE
    SET name = EXCLUDED.name;

DELETE FROM reimbursement_report WHERE reimbursement_code IN ('EREP_10069', 'EREP_10070', 'EREP_10071', 'EREP_10072');

-- Processes left without any file (this seeder's process of an earlier run).
DELETE FROM ocr_process p
WHERE NOT EXISTS (SELECT 1 FROM ocr_reimbursement o WHERE o.ocr_process_id = p.id);

INSERT INTO reimbursement_report (reimbursement_code, employee_no, grand_total, received_at, payload_hash) VALUES
    ('EREP_10069', '06300002', 382225, '2026-10-21 07:30:00+07:00', '827d5c4d4fe93e38c1c8e533ac9d76217da2c0828e866449ae86ed8e5b84958e'),  -- call J, 3.jpg: correct (as EREP_10002)
    ('EREP_10070', '06300001', 750000, '2026-10-21 07:30:00+07:00', '965255cb40d67aabbb1c9b69c0fa457f8374d005b6617517b479da7a4b9d233d'),  -- call J, 26.jpeg: correct (as EREP_10019)
    ('EREP_10071', '06300003', 430000, '2026-10-21 07:30:00+07:00', '98eb1978b640534632faf8ac3a4dbe286d13202ab9542576e74f62ca60a6d5fd'),  -- call J, 34.jpg: correct (as EREP_10030)
    ('EREP_10072', '06300006', 200000, '2026-10-21 07:30:00+07:00', '63cd758c1dca2c99a49659b6a173ebbce7f6ddc00b91a639fb94104b74d5f195');  -- call J, 28.jpeg: correct (as EREP_10021)

INSERT INTO bbm_receipt (reimbursement_code, item_id, product_name, date_of_expense, volume_liter, kilometer, total_price)
VALUES
    ('EREP_10069', 'EXP_10094', 'BP 92', '2026-01-20', 31.578, 22026, 394725),
    ('EREP_10070', 'EXP_10095', 'Diesel/Dex', '2026-01-07', 55.147, 48157, 750000),
    ('EREP_10071', 'EXP_10096', 'Shell Super 92', '2025-12-17', 33.07, 36284, 430000),
    ('EREP_10072', 'EXP_10097', 'Performa > 92', '2026-06-27', 11.765, 20181, 200000);

-- EREP_10072's storage_path points to a file that is not there: what the worker finds when a stored file was lost.
INSERT INTO attachment (bbm_receipt_id, name, url, sha256, storage_path, content_type)
SELECT i.id, v.name, v.url, v.sha256, v.storage_path, v.content_type
FROM (VALUES
    ('EREP_10069', '3.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/3.jpg', '0d74621b8c2870bc2f07d8222ef392ffbf40d2e8aae897e6346309f1e0196c2f',
     'local:backend/database/dummy_bbm_receipt/3.jpg', 'image/jpeg'),
    ('EREP_10070', '26.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/26.jpeg', '66937f14456eb31e6ccb93edb398fafe1611cb865f12f73409a5d40cc9654894',
     'local:backend/database/dummy_bbm_receipt/26.jpeg', 'image/jpeg'),
    ('EREP_10071', '34.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/34.jpg', 'b9a08f1bf01a48970f83d981ceb2af7422868d349c40c629c5acb01130197f06',
     'local:backend/database/dummy_bbm_receipt/34.jpg', 'image/jpeg'),
    ('EREP_10072', '28.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/28.jpeg', 'e03503b78314fbaf153929bf5b5060b38b20b633ed556988dc901b9d5a71ee1b',
     'local:backend/database/dummy_bbm_receipt/lost/28.jpeg', 'image/jpeg')
) AS v (reimbursement_code, name, url, sha256, storage_path, content_type)
JOIN bbm_receipt i USING (reimbursement_code)
ORDER BY i.id;

-- process J: 4 files, all failed (the last one 09:05:46, after EREP_10070's 12th try)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (0, 0, 0, 0, 4, '2026-10-21 07:30:00.000+07:00', '2026-10-21 09:05:46.303+07:00')
    RETURNING id
)
INSERT INTO ocr_reimbursement (ocr_process_id, attachment_id, status, attempts, error, started_at)
SELECT p.id, a.id, 'failed', v.attempts, v.error, v.started_at::timestamptz
FROM p, (VALUES
    ('EREP_10069', 3, 'Claude did not finish within 300 seconds.', '2026-10-21 07:43:33.062+07:00'),
    ('EREP_10070', 12, E'Claude execution failed:\nAPI Error: 529 Overloaded', '2026-10-21 09:05:43.185+07:00'),
    ('EREP_10071', 3, E'Claude completed successfully, but no valid JSON result could be extracted from its response.\nClaude stderr:\n',
     '2026-10-21 07:49:36.434+07:00'),
    ('EREP_10072', 1, 'local:backend/database/dummy_bbm_receipt/lost/28.jpeg is not in the local file storage.',
     '2026-10-21 07:36:48.019+07:00')
) AS v (reimbursement_code, attempts, error, started_at)
JOIN bbm_receipt i USING (reimbursement_code)
JOIN attachment a ON a.bbm_receipt_id = i.id
ORDER BY a.id;

COMMIT;

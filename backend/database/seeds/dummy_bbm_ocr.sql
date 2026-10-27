-- Dummy OCR results for the dummy reimbursements (run after dummy_reimbursement.sql).
-- Real data, not invented: the readings, confidences, token counts and timings are the Haiku OCR output in
-- backend/jobs/bbm_ocr/results_haiku_10_epochs/max_0 (dates written as DD-MM-YYYY, as the OCR now returns them), and
-- every decision, difference and description is what the OCR worker (backend/jobs/bbm_ocr/worker.py) stores for that
-- reading: receipt_validation.py compares it with the submitted data (each item is one receipt; the file's total is
-- checked against the grand total) and receipt_records.py makes the rows.
-- Every call to POST /api/reimbursements queues the files of its new reports in one OCR process, and the worker reads
-- them right after the call, one after the other. A file attached to several items of a report (a photo of several
-- receipts) is read once: its row points at the file's first attachment, and the reading is compared with all those
-- items.
--   A  10-08-2026 09:12  14 files, epoch 03
--   B  24-08-2026 14:40  8 files, epoch 01
--   C  07-09-2026 10:05  8 files, epoch 01
--   D  21-09-2026 11:20  14 files, epoch 04
--   E  05-10-2026 09:45  10 files, epoch 05
--   F  12-10-2026 13:30  12 files, epoch 06; EREP_10062 37.jpg failed
--   G  18-10-2026 10:10  5 files queued, not read yet
--   H  19-10-2026 14:15  6 files queued, not read yet (EREP_10067 has a photo per item)
--   I  20-10-2026 08:30  2 files, epoch 07 (EREP_10081 and EREP_10082, receipts claimed again after an approval)
-- EREP_10062 37.jpg is set up as a file the OCR could not read (its photo is fine), to show that state: it timed out
-- three times, so it failed and needs a reviewer (dummy_ocr_failure.sql adds a report for each other way a read fails).
-- Calls G and H are still queued: run the worker to read them
-- (py -m backend.jobs.bbm_ocr.worker --once; it reads the files from backend/database/dummy_bbm_receipt).
-- decision: matched      = the file agrees with the submitted data
--           proceed      = it differs, but every difference is an OCR misread (the receipt's own math proves it)
--                          and the receipt backs the grand total
--           needs_review = a reviewer must check the file; also when the receipt's numbers don't back the grand total
--                          (EREP_10075: the OCR read 31.76 L, so volume x price per liter backs only 374,768 of
--                          410,168)
-- Running it again replaces the dummy reports' OCR results.
BEGIN;

DELETE FROM ocr_reimbursement o
USING attachment a, bbm_receipt i, reimbursement_report p
WHERE a.id = o.attachment_id AND i.id = a.bbm_receipt_id AND p.reimbursement_code = i.reimbursement_code
  AND p.employee_no IN ('06300001', '06300002', '06300003', '06300004', '06300005', '06300006');

-- Processes left without any file (the dummy processes of an earlier seeding).
DELETE FROM ocr_process p
WHERE NOT EXISTS (SELECT 1 FROM ocr_reimbursement o WHERE o.ocr_process_id = p.id);

-- call letter in this file -> its ocr_process id
CREATE TEMP TABLE seed_ocr_process (process varchar(1) PRIMARY KEY, id integer NOT NULL) ON COMMIT DROP;

-- process A: 14 files (OCR reading of epoch 3)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (173943, 25460, 28903, 24368, 14, '2026-08-10 09:12:00.000+07:00', '2026-08-10 09:16:40.108+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'A', id FROM p;

-- process B: 8 files (OCR reading of epoch 1)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (72133, 29049, 17501, 13925, 8, '2026-08-24 14:40:00.000+07:00', '2026-08-24 14:42:13.263+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'B', id FROM p;

-- process C: 8 files (OCR reading of epoch 1)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (72131, 26421, 16541, 13321, 8, '2026-09-07 10:05:00.000+07:00', '2026-09-07 10:07:13.956+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'C', id FROM p;

-- process D: 14 files (OCR reading of epoch 4)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (170526, 11937, 32131, 27748, 14, '2026-09-21 11:20:00.000+07:00', '2026-09-21 11:26:41.381+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'D', id FROM p;

-- process E: 10 files (OCR reading of epoch 5)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (107879, 11450, 22839, 19623, 10, '2026-10-05 09:45:00.000+07:00', '2026-10-05 09:48:36.882+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'E', id FROM p;

-- process F: 12 files (OCR reading of epoch 6)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (124180, 17971, 15105, 11135, 12, '2026-10-12 13:30:00.000+07:00', '2026-10-12 13:48:51.626+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'F', id FROM p;

-- process G: 5 files (still queued)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (0, 0, 0, 0, 5, '2026-10-18 10:10:00.000+07:00', NULL)
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'G', id FROM p;

-- process H: 6 files (still queued)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (0, 0, 0, 0, 6, '2026-10-19 14:15:00.000+07:00', NULL)
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'H', id FROM p;

-- process I: 2 files (OCR reading of epoch 7)
WITH p AS (
    INSERT INTO ocr_process (cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, total_images, processed_at, finished_at)
    VALUES (21925, 1238, 2691, 2088, 2, '2026-10-20 08:30:00.000+07:00', '2026-10-20 08:30:35.588+07:00')
    RETURNING id
)
INSERT INTO seed_ocr_process SELECT 'I', id FROM p;

-- One row per file of a report, found by (reimbursement_code, file name): done (with its decision), failed, or queued.
-- It points at the file's first attachment (the file of a photo of several receipts is attached to each of their items).
-- started_at is when the last attempt started; a done reading finished elapsed_seconds later.
INSERT INTO ocr_reimbursement (ocr_process_id, attachment_id, status, attempts, error, started_at, decision, elapsed_seconds,
                               grand_total, confidence_grand_total)
SELECT b.id, a.id, v.status, v.attempts, v.error, v.started_at::timestamptz, v.decision, v.elapsed_seconds::numeric,
       v.grand_total::numeric, v.confidence_grand_total::numeric
FROM (VALUES
    ('A', 'EREP_10001', '1.jpeg', 'done', 1, NULL, '2026-08-10 09:12:03.000+07:00', 'matched', 15.807, 1358170, 0.95),
    ('A', 'EREP_10002', '3.jpg', 'done', 1, NULL, '2026-08-10 09:12:20.807+07:00', 'matched', 16.841, 382225, 0.92),
    ('A', 'EREP_10003', '11.jpeg', 'done', 1, NULL, '2026-08-10 09:12:39.648+07:00', 'matched', 13.629, 253200, 0.92),
    ('A', 'EREP_10004', '14.jpeg', 'done', 1, NULL, '2026-08-10 09:12:55.277+07:00', 'needs_review', 15.613, 450000, 0.92),
    ('A', 'EREP_10005', '15.jpeg', 'done', 1, NULL, '2026-08-10 09:13:12.890+07:00', 'proceed', 25.168, 382980, 0.95),
    ('A', 'EREP_10006', '16.jpg', 'done', 1, NULL, '2026-08-10 09:13:40.058+07:00', 'matched', 9.027, 549549, 0.9),
    ('A', 'EREP_10007', '17.jpg', 'done', 1, NULL, '2026-08-10 09:13:51.085+07:00', 'needs_review', 24.015, 35000, 0.9),
    ('A', 'EREP_10008', '21.jpeg', 'done', 1, NULL, '2026-08-10 09:14:17.100+07:00', 'needs_review', 16.16, 380746, 0.95),
    ('A', 'EREP_10009', '2.jpg', 'done', 1, NULL, '2026-08-10 09:14:35.260+07:00', 'matched', 13.408, 15000, 0.9),
    ('A', 'EREP_10053', '4.jpg', 'done', 1, NULL, '2026-08-10 09:14:50.668+07:00', 'matched', 16.933, 100000, 0.93),
    ('A', 'EREP_10054', '8.jpeg', 'done', 1, NULL, '2026-08-10 09:15:09.601+07:00', 'matched', 26.703, 150000, 0.95),
    ('A', 'EREP_10010', '29.jpg', 'done', 1, NULL, '2026-08-10 09:15:38.304+07:00', 'needs_review', 14.619, 646180, 0.93),
    ('A', 'EREP_10011', '32.jpeg', 'done', 1, NULL, '2026-08-10 09:15:54.923+07:00', 'matched', 13.804, 519303, 0.9),
    ('A', 'EREP_10012', '39.png', 'done', 1, NULL, '2026-08-10 09:16:10.727+07:00', 'needs_review', 29.381, 410168, 0.85),
    ('B', 'EREP_10013', '60.jpg', 'done', 1, NULL, '2026-08-24 14:40:03.000+07:00', 'proceed', 19.308, 1769560, 0.8),
    ('B', 'EREP_10014', '57.jpeg', 'done', 1, NULL, '2026-08-24 14:40:24.308+07:00', 'matched', 19.022, 2550000, 0.9),
    ('B', 'EREP_10015', '5.jpeg', 'done', 1, NULL, '2026-08-24 14:40:45.330+07:00', 'matched', 10.161, 400119, 0.92),
    ('B', 'EREP_10016', '6.jpg', 'done', 1, NULL, '2026-08-24 14:40:57.491+07:00', 'matched', 10.528, 450060, 0.9),
    ('B', 'EREP_10017', '10.jpg', 'done', 1, NULL, '2026-08-24 14:41:10.019+07:00', 'matched', 10.265, 250000, 0.92),
    ('B', 'EREP_10018', '18.jpeg', 'done', 1, NULL, '2026-08-24 14:41:22.284+07:00', 'needs_review', 11.368, 489157, 0.93),
    ('B', 'EREP_10019', '26.jpeg', 'done', 1, NULL, '2026-08-24 14:41:35.652+07:00', 'matched', 9.867, 750000, 0.95),
    ('B', 'EREP_10020', '64.jpeg', 'done', 1, NULL, '2026-08-24 14:41:47.519+07:00', 'needs_review', 25.744, 1000000, 0.85),
    ('C', 'EREP_10073', '17.jpg', 'done', 1, NULL, '2026-09-07 10:05:03.000+07:00', 'needs_review', 21.455, 35000, 0.9),
    ('C', 'EREP_10074', '64.jpeg', 'done', 1, NULL, '2026-09-07 10:05:26.455+07:00', 'matched', 25.744, 1000000, 0.85),
    ('C', 'EREP_10021', '28.jpeg', 'done', 1, NULL, '2026-09-07 10:05:54.199+07:00', 'matched', 9.757, 200000, 0.93),
    ('C', 'EREP_10022', '24.jpeg', 'done', 1, NULL, '2026-09-07 10:06:05.956+07:00', 'matched', 12.584, 500000, 0.95),
    ('C', 'EREP_10023', '51.jpg', 'done', 1, NULL, '2026-09-07 10:06:20.540+07:00', 'matched', 11.69, 686468, 0.93),
    ('C', 'EREP_10055', '52.jpg', 'done', 1, NULL, '2026-09-07 10:06:34.230+07:00', 'matched', 9.476, 441555, 0.95),
    ('C', 'EREP_10024', '62.jpg', 'done', 1, NULL, '2026-09-07 10:06:45.706+07:00', 'needs_review', 15.933, 750000, 0.9),
    ('C', 'EREP_10025', '13.jpg', 'done', 1, NULL, '2026-09-07 10:07:03.639+07:00', 'matched', 10.317, 300000, 0.95),
    ('D', 'EREP_10075', '39.png', 'done', 1, NULL, '2026-09-21 11:20:03.000+07:00', 'needs_review', 26.418, 410168, 0.8),
    ('D', 'EREP_10076', '18.jpeg', 'done', 1, NULL, '2026-09-21 11:20:31.418+07:00', 'needs_review', 33.514, 489157, 0.9),
    ('D', 'EREP_10026', '22.jpg', 'done', 1, NULL, '2026-09-21 11:21:06.932+07:00', 'matched', 13.696, 430080, 0.9),
    ('D', 'EREP_10027', '23.jpeg', 'done', 1, NULL, '2026-09-21 11:21:22.628+07:00', 'matched', 15.11, 500000, 0.9),
    ('D', 'EREP_10028', '31.jpeg', 'done', 1, NULL, '2026-09-21 11:21:39.738+07:00', 'matched', 16.436, 200000, 0.88),
    ('D', 'EREP_10029', '40.jpg', 'done', 1, NULL, '2026-09-21 11:21:58.174+07:00', 'needs_review', 18.908, 450000, 0.92),
    ('D', 'EREP_10030', '34.jpg', 'done', 1, NULL, '2026-09-21 11:22:19.082+07:00', 'matched', 13.866, 430000, 0.95),
    ('D', 'EREP_10031', '45.jpg', 'done', 1, NULL, '2026-09-21 11:22:34.948+07:00', 'matched', 21.854, 402230, 0.9),
    ('D', 'EREP_10032', '27.jpeg', 'done', 1, NULL, '2026-09-21 11:22:58.802+07:00', 'needs_review', 23.484, 411066, 0.93),
    ('D', 'EREP_10056', '30.jpg', 'done', 1, NULL, '2026-09-21 11:23:24.286+07:00', 'matched', 15.484, 815590, 0.9),
    ('D', 'EREP_10033', '59.jpg', 'done', 1, NULL, '2026-09-21 11:23:41.770+07:00', 'matched', 27.6, 1005789, 0.92),
    ('D', 'EREP_10034', '12.jpg', 'done', 1, NULL, '2026-09-21 11:24:11.370+07:00', 'matched', 20.73, 20630, 0.9),
    ('D', 'EREP_10057', '19.jpeg', 'done', 1, NULL, '2026-09-21 11:24:34.100+07:00', 'matched', 97.095, 40000, 0.95),
    ('D', 'EREP_10058', '20.jpg', 'done', 1, NULL, '2026-09-21 11:26:13.195+07:00', 'matched', 28.186, 40000, 0.95),
    ('E', 'EREP_10077', '29.jpg', 'done', 1, NULL, '2026-10-05 09:45:03.000+07:00', 'matched', 20.304, 646180, 0.92),
    ('E', 'EREP_10035', '58.jpg', 'done', 1, NULL, '2026-10-05 09:45:25.304+07:00', 'matched', 53.841, 863100, 0.75),
    ('E', 'EREP_10036', '46.jpeg', 'done', 1, NULL, '2026-10-05 09:46:21.145+07:00', 'matched', 14.651, 370000, 0.95),
    ('E', 'EREP_10037', '33.jpeg', 'done', 1, NULL, '2026-10-05 09:46:37.796+07:00', 'matched', 14.223, 400000, 0.9),
    ('E', 'EREP_10038', '35.jpg', 'done', 1, NULL, '2026-10-05 09:46:54.019+07:00', 'needs_review', 11.399, 438750, 0.95),
    ('E', 'EREP_10039', '47.jpg', 'done', 1, NULL, '2026-10-05 09:47:07.418+07:00', 'matched', 11.541, 650000, 0.92),
    ('E', 'EREP_10040', '38.jpg', 'done', 1, NULL, '2026-10-05 09:47:20.959+07:00', 'matched', 16.721, 400000, 0.93),
    ('E', 'EREP_10041', '49.jpg', 'done', 1, NULL, '2026-10-05 09:47:39.680+07:00', 'matched', 14.909, 399380, 0.95),
    ('E', 'EREP_10059', '50.jpg', 'done', 1, NULL, '2026-10-05 09:47:56.589+07:00', 'matched', 12.673, 231120, 0.93),
    ('E', 'EREP_10042', '55.jpeg', 'done', 1, NULL, '2026-10-05 09:48:11.262+07:00', 'matched', 25.62, 349546, 0.9),
    ('F', 'EREP_10078', '18.jpeg', 'done', 1, NULL, '2026-10-12 13:30:03.000+07:00', 'matched', 17.37, 489157, 0.95),
    ('F', 'EREP_10079', '62.jpg', 'done', 1, NULL, '2026-10-12 13:30:22.370+07:00', 'matched', 17.473, 750000, 0.93),
    ('F', 'EREP_10043', '41.jpeg', 'done', 1, NULL, '2026-10-12 13:30:41.843+07:00', 'matched', 22.098, 200000, 0.85),
    ('F', 'EREP_10060', '42.jpeg', 'done', 1, NULL, '2026-10-12 13:31:05.941+07:00', 'matched', 30.959, 400000, 0.95),
    ('F', 'EREP_10044', '43.jpg', 'done', 1, NULL, '2026-10-12 13:31:38.900+07:00', 'matched', 15.977, 400000, 0.95),
    ('F', 'EREP_10061', '44.jpg', 'done', 1, NULL, '2026-10-12 13:31:56.877+07:00', 'matched', 11.879, 382500, 0.93),
    ('F', 'EREP_10045', '53.jpeg', 'done', 1, NULL, '2026-10-12 13:32:10.756+07:00', 'matched', 24.293, 858652, 0.93),
    ('F', 'EREP_10046', '54.jpeg', 'done', 1, NULL, '2026-10-12 13:32:37.049+07:00', 'needs_review', 16.053, 404166, 0.93),
    ('F', 'EREP_10047', '48.png', 'done', 1, NULL, '2026-10-12 13:32:55.102+07:00', 'matched', 17.762, 722020, 0.93),
    ('F', 'EREP_10048', '61.png', 'done', 1, NULL, '2026-10-12 13:33:14.864+07:00', 'matched', 13.425, 537774, 0.93),
    ('F', 'EREP_10049', '25.jpeg', 'done', 1, NULL, '2026-10-12 13:33:30.289+07:00', 'matched', 15.337, 50000, 0.95),
    ('F', 'EREP_10062', '37.jpg', 'failed', 3, 'Claude did not finish within 300 seconds.', '2026-10-12 13:43:51.626+07:00', NULL, NULL, NULL, NULL),
    ('G', 'EREP_10080', '27.jpeg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('G', 'EREP_10050', '63.jpg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('G', 'EREP_10051', '56.jpeg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('G', 'EREP_10052', '7.jpg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('G', 'EREP_10063', '9.jpeg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('H', 'EREP_10064', 'receipts_2_4_8.pdf', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('H', 'EREP_10065', 'receipts_51_52.pdf', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('H', 'EREP_10066', 'receipts_49_50.pdf', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('H', 'EREP_10067', '43.jpg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('H', 'EREP_10067', '44.jpg', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('H', 'EREP_10068', 'receipts_64.pdf', 'queued', 0, NULL, NULL, NULL, NULL, NULL, NULL),
    ('I', 'EREP_10081', '14.jpeg', 'done', 1, NULL, '2026-10-20 08:30:03.000+07:00', 'needs_review', 17.078, 450000, 0.9),
    ('I', 'EREP_10082', '16.jpg', 'done', 1, NULL, '2026-10-20 08:30:20.078+07:00', 'matched', 15.51, 549549, 0.9)
) AS v (process, reimbursement_code, attachment_name, status, attempts, error, started_at, decision, elapsed_seconds,
        grand_total, confidence_grand_total)
JOIN seed_ocr_process b USING (process)
JOIN LATERAL (SELECT a.id FROM attachment a JOIN bbm_receipt i ON i.id = a.bbm_receipt_id
              WHERE i.reimbursement_code = v.reimbursement_code AND a.name = v.attachment_name
              ORDER BY a.id LIMIT 1) a ON true
ORDER BY b.id, a.id;

-- What the OCR read, one row per product line (date_of_expense as DD-MM-YYYY; it is text, as the OCR may misread it).
-- The receipt's date is repeated on each of its lines; its discount is kept on its first line only.
-- Inserted in line order, so a result's line n is its n-th row by id (used by the differences below).
INSERT INTO ocr_bbm_receipt (ocr_reimbursement_id, product_name, date_of_expense, price_per_liter, volume_liter, total_price, discount,
                             confidence_product_name, confidence_date_of_expense, confidence_price_per_liter,
                             confidence_volume_liter, confidence_total_price, confidence_discount)
SELECT o.id, v.product_name, v.date_of_expense, v.price_per_liter::numeric, v.volume_liter::numeric, v.total_price::numeric,
       v.discount::numeric, v.c_product_name::numeric, v.c_date::numeric, v.c_price_per_liter::numeric,
       v.c_volume_liter::numeric, v.c_total_price::numeric, v.c_discount::numeric
FROM (VALUES
    ('EREP_10001', '1.jpeg', 1, 'PERTAMINA_DEX', '26-05-2026', 27900, 48.68, 1358170, 0, 0.95, 0.93, 0.93, 0.9, 0.95, 0.9),
    ('EREP_10002', '3.jpg', 1, 'BP92', '20-01-2026', 12500, 31.578, 394725, 12500, 0.95, 0.9, 0.93, 0.9, 0.95, 0.9),
    ('EREP_10003', '11.jpeg', 1, 'PERTALITE', '06-04-2026', 16088, 25.32, 407348, 154148, 0.97, 0.9, 0.9, 0.93, 0.9, 0.88),
    ('EREP_10004', '14.jpeg', 1, 'PERTAMAX Hose 10.3', '18-12-2025', 12750, 35.291, 450000, 0, 0.9, 0.93, 0.93, 0.7, 0.92, 0.9),
    ('EREP_10081', '14.jpeg', 1, 'PERTAMAX Hose 10.3', '18-12-2025', 12750, 35.291, 450000, 0, 0.85, 0.9, 0.9, 0.85, 0.9, 0.9),
    ('EREP_10005', '15.jpeg', 1, 'Revvo 92', '02-12-2025', 13000, NULL, 382980, 0, 0.9, 0.9, 0.9, 0, 0.9, 0.95),
    ('EREP_10006', '16.jpg', 1, 'V-POWER DIESEL', '08-01-2026', 13860, 39.65, 549549, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10082', '16.jpg', 1, 'V-POWER DIESEL', '08-01-2026', 13860, 39.65, 549549, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.9),
    ('EREP_10007', '17.jpg', 1, 'PERTAMAX', '10-05-2026', 12300, 2.85, 35000, 0, 0.85, 0.4, 0.9, 0.75, 0.9, 0.9),
    ('EREP_10008', '21.jpeg', 1, 'SHELL SUPER', '10-01-2026', 12700, 29.98, 380746, 0, 0.95, 0.93, 0.95, 0.93, 0.95, 0.95),
    ('EREP_10009', '2.jpg', 1, 'PERTAMAX', '02-05-2026', 12300, 1.22, 15000, 0, 0.95, 0.9, 0.9, 0.85, 0.9, 0.95),
    ('EREP_10053', '4.jpg', 1, 'PERTAMAX', '28-06-2026', 16250, 6.15, 100000, 0, 0.97, 0.9, 0.93, 0.9, 0.93, 0.9),
    ('EREP_10054', '8.jpeg', 1, 'PERTAMAX', '13-05-2026', 12300, 12.195, 150000, 0, 0.95, 0.85, 0.93, 0.9, 0.95, 0.9),
    ('EREP_10010', '29.jpg', 1, 'PERTAMAX TURBO', '04-02-2026', 12700, 50.88, 646180, 0, 0.65, 0.9, 0.95, 0.9, 0.93, 0.9),
    ('EREP_10011', '32.jpeg', 1, 'Super', '23-01-2026', 12700, 40.89, 519303, 0, 0.85, 0.9, 0.9, 0.9, 0.9, 0.9),
    ('EREP_10012', '39.png', 1, 'PERTAMAX', '26-02-2026', 11800, 34.76, 410168, 0, 0.92, 0.9, 0.85, 0.45, 0.85, 0.9),
    ('EREP_10013', '60.jpg', 1, 'Pertamax', '07-12-2025', 12750, 50.98, 650000, 0, 0.95, 0.8, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10013', '60.jpg', 2, 'SHELL SUPER', '12-12-2025', 13000, NULL, 397540, 0, 0.75, 0.9, 0.9, 0, 0.85, 0.95),
    ('EREP_10013', '60.jpg', 3, 'SHELL SUPER', '29-12-2025', 13000, 55.54, 722020, 0, 0.85, 0.9, 0.9, 0.85, 0.9, 0.95),
    ('EREP_10014', '57.jpeg', 1, 'BP92', '07-04-2026', 12390, 32.285, 400000, 0, 0.95, 0.85, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10014', '57.jpeg', 2, 'BP92', '10-04-2026', 12390, 36.32, 450000, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10014', '57.jpeg', 3, 'BP92', '15-04-2026', 12390, 36.32, 450000, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10014', '57.jpeg', 4, 'BP92', '20-04-2026', 12390, 36.32, 450000, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10014', '57.jpeg', 5, 'BP92', '24-04-2026', 12390, 28.25, 350000, 0, 0.95, 0.88, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10014', '57.jpeg', 6, 'BP92', '28-04-2026', 12390, 36.32, 450000, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10015', '5.jpeg', 1, 'PERTAMAX', '09-06-2026', 12300, 32.53, 400119, 0, 0.97, 0.92, 0.95, 0.92, 0.92, 0.95),
    ('EREP_10016', '6.jpg', 1, 'PERTAMAX', '27-03-2026', 12300, 36.59, 450060, 0, 0.97, 0.93, 0.95, 0.9, 0.9, 0.95),
    ('EREP_10017', '10.jpg', 1, 'PERTAMAX', '19-04-2026', 12300, 20.32, 250000, 0, 0.95, 0.9, 0.9, 0.9, 0.92, 0.9),
    ('EREP_10018', '18.jpeg', 1, 'BP92', '23-05-2026', 12390, 39.48, 489157, 0, 0.97, 0.9, 0.9, 0.9, 0.92, 0.95),
    ('EREP_10019', '26.jpeg', 1, 'PERTAMINA_DEX', '07-01-2026', 13600, 55.147, 750000, 0, 0.93, 0.9, 0.92, 0.9, 0.93, 0.9),
    ('EREP_10020', '64.jpeg', 1, 'PERTAMAX 92', '06-01-2026', 12350, 32.38, 400000, 0, 0.95, 0.88, 0.95, 0.85, 0.92, 1),
    ('EREP_10020', '64.jpeg', 2, 'PERTAMAX', '20-01-2026', 12350, 16.19, 200000, 0, 0.95, 0.9, 0.9, 0.85, 0.88, 0.9),
    ('EREP_10020', '64.jpeg', 3, 'PERTAMAX', '27-01-2026', 12350, 32.389, 400000, 0, 0.95, 0.92, 0.93, 0.85, 0.93, 0.95),
    ('EREP_10073', '17.jpg', 1, 'PERTAMAX', NULL, 12300, 2.85, 35000, 0, 0.9, 0, 0.95, 0.7, 0.9, 0.95),
    ('EREP_10074', '64.jpeg', 1, 'PERTAMAX 92', '06-01-2026', 12350, 32.38, 400000, 0, 0.95, 0.88, 0.95, 0.85, 0.92, 1),
    ('EREP_10074', '64.jpeg', 2, 'PERTAMAX', '20-01-2026', 12350, 16.19, 200000, 0, 0.95, 0.9, 0.9, 0.85, 0.88, 0.9),
    ('EREP_10074', '64.jpeg', 3, 'PERTAMAX', '27-01-2026', 12350, 32.389, 400000, 0, 0.95, 0.92, 0.93, 0.85, 0.93, 0.95),
    ('EREP_10021', '28.jpeg', 1, 'PERTAMAX GREEN', '27-06-2026', 17000, 11.765, 200000, 0, 0.95, 0.93, 0.93, 0.9, 0.93, 0.9),
    ('EREP_10022', '24.jpeg', 1, 'Revvo 92', '08-12-2025', 13000, 38.46, 500000, 0, 0.9, 0.85, 0.9, 0.85, 0.95, 0.95),
    ('EREP_10023', '51.jpg', 1, 'BP92', '27-04-2026', 12390, 55.405, 686468, 0, 0.97, 0.9, 0.9, 0.9, 0.93, 0.95),
    ('EREP_10055', '52.jpg', 1, 'BP92', '12-04-2026', 12390, 35.638, 441555, 0, 0.95, 0.9, 0.9, 0.9, 0.93, 1),
    ('EREP_10024', '62.jpg', 1, 'PERTAMAX', '02-02-2026', 12500, 12, 150000, 0, 0.95, 0.9, 0.93, 0.92, 0.93, 0.9),
    ('EREP_10024', '62.jpg', 2, 'PERTAMAX', '09-02-2026', 12500, 12, 150000, 0, 0.95, 0.88, 0.93, 0.92, 0.93, 0.9),
    ('EREP_10024', '62.jpg', 3, 'PERTAMAX', '16-02-2026', 12500, 12, 150000, 0, 0.95, 0.9, 0.93, 0.92, 0.93, 0.9),
    ('EREP_10024', '62.jpg', 4, 'PERTAMAX', '23-02-2026', 12500, 8, 100000, 0, 0.95, 0.9, 0.93, 0.9, 0.92, 0.9),
    ('EREP_10024', '62.jpg', 5, 'PERTAMAX', '25-02-2026', 12500, 16, 200000, 0, 0.95, 0.9, 0.93, 0.9, 0.92, 0.9),
    ('EREP_10025', '13.jpg', 1, 'Pertamax', '30-07-2026', NULL, 18.46, 300000, 0, 0.97, 0.95, 0, 0.95, 0.95, 0.95),
    ('EREP_10075', '39.png', 1, 'PERTAMAX', '26-02-2026', 11800, 31.76, 410168, 0, 0.9, 0.9, 0.8, 0.4, 0.8, 0.9),
    ('EREP_10076', '18.jpeg', 1, 'BP92', '23-05-2026', 12390, 39.48, 489157, 0, 0.97, 0.9, 0.9, 0.9, 0.9, 0.95),
    ('EREP_10026', '22.jpg', 1, 'PERTAMAX', '27-01-2026', 12350, 34.824, 430080, 0, 0.9, 0.9, 0.9, 0.85, 0.9, 0.9),
    ('EREP_10027', '23.jpeg', 1, 'PERTAMAX', '01-12-2025', 12750, 39.21, 500000, 0, 0.9, 0.9, 0.9, 0.88, 0.9, 0.95),
    ('EREP_10028', '31.jpeg', 1, 'PERTALITE', '26-02-2026', 10000, 20, 200000, 0, 0.95, 0.9, 0.9, 0.9, 0.92, 0.95),
    ('EREP_10029', '40.jpg', 1, 'BP92', '08-06-2026', 12390, 36.32, 450000, 0, 0.95, 0.85, 0.9, 0.9, 0.95, 0.9),
    ('EREP_10030', '34.jpg', 1, 'SHELL SUPER', '17-12-2025', 13000, 33.07, 430000, 0, 0.95, 0.95, 0.95, 0.9, 0.95, 0.9),
    ('EREP_10031', '45.jpg', 1, 'PERTAMAX-TURBO', '07-08-2026', 18300, 21.98, 402230, 0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.9),
    ('EREP_10032', '27.jpeg', 1, 'PERTAMAX', '29-03-2026', 12300, 33.42, 411066, 0, 0.95, 0.9, 0.93, 0.9, 0.93, 0.95),
    ('EREP_10056', '30.jpg', 1, 'PERTAMAX', '02-08-2026', 15950, 51.13, 815590, 0, 0.95, 0.9, 0.93, 0.9, 0.9, 0.95),
    ('EREP_10033', '59.jpg', 1, 'Revvo 92', '13-02-2026', 12050, 19.77, 238228, 0, 0.9, 0.88, 0.93, 0.93, 0.93, 0.9),
    ('EREP_10033', '59.jpg', 2, 'BP92', '02-02-2026', 12050, 23.698, 285561, 0, 0.9, 0.93, 0.9, 0.9, 0.92, 0.9),
    ('EREP_10033', '59.jpg', 3, 'Revvo 92', '25-02-2026', 12050, 40, 482000, 0, 0.9, 0.88, 0.9, 0.9, 0.92, 0.9),
    ('EREP_10034', '12.jpg', 1, 'PERTAMAX', '29-05-2026', 12600, 1.64, 20630, 0, 0.95, 0.9, 0.9, 0.85, 0.9, 0.95),
    ('EREP_10057', '19.jpeg', 1, 'PERTAMAX', '03-06-2026', 12600, 3.18, 40000, 0, 0.97, 0.85, 0.95, 0.88, 0.95, 0.95),
    ('EREP_10058', '20.jpg', 1, 'PERTAMAX', '08-05-2026', 12600, 3.18, 40000, 0, 0.95, 0.9, 0.95, 0.85, 0.95, 0.95),
    ('EREP_10077', '29.jpg', 1, 'PERTAMAX TURBO', '04-02-2026', 12700, 50.88, 646180, 0, 0.75, 0.9, 0.95, 0.9, 0.9, 0.95),
    ('EREP_10035', '58.jpg', 1, 'PERTALITE', '01-03-2026', 10000, 35.02, 350200, 0, 0.9, 0.8, 0.85, 0.8, 0.85, 0.9),
    ('EREP_10035', '58.jpg', 2, 'PERTALITE', '10-03-2026', 10449, 32.79, 342623, 14723, 0.95, 0.9, 0.9, 0.9, 0.9, 0.9),
    ('EREP_10035', '58.jpg', 3, 'PERTALITE', '18-03-2026', 10000, 18.5, 185000, 0, 0.9, 0.9, 0.8, 0.6, 0.8, 0.85),
    ('EREP_10036', '46.jpeg', 1, 'BP92', '12-03-2026', 12390, 29.865, 370000, 0, 0.97, 0.92, 0.92, 0.9, 0.95, 0.95),
    ('EREP_10037', '33.jpeg', 1, 'PERTAMAX 92', '06-01-2026', 12350, 32.38, 400000, 0, 0.95, 0.85, 0.9, 0.85, 0.9, 0.95),
    ('EREP_10038', '35.jpg', 1, 'PERTAMAX', '17-07-2026', 16250, 27, 438750, 0, 0.97, 0.9, 0.9, 0.93, 0.95, 0.95),
    ('EREP_10039', '47.jpg', 1, 'Pertamax', '07-12-2025', 12750, 50.98, 650000, 0, 0.95, 0.88, 0.9, 0.88, 0.9, 0.9),
    ('EREP_10040', '38.jpg', 1, 'Pertamax', '18-02-2026', 11800, 33.89, 400000, 0, 0.95, 0.9, 0.92, 0.88, 0.93, 0.95),
    ('EREP_10041', '49.jpg', 1, 'PERTAMAX', '10-03-2026', 12300, 32.47, 399380, 0, 0.95, 0.85, 0.95, 0.93, 0.95, 0.95),
    ('EREP_10059', '50.jpg', 1, 'PERTAMAX', '20-04-2026', 12300, 18.79, 231120, 0, 0.95, 0.9, 0.92, 0.9, 0.93, 0.9),
    ('EREP_10042', '55.jpeg', 1, 'BP92', '23-02-2026', 12050, 30.008, 361596, 12050, 0.97, 0.9, 0.9, 0.88, 0.9, 0.92),
    ('EREP_10078', '18.jpeg', 1, 'BP92', '23-05-2026', 12390, 39.48, 489157, 0, 0.95, 0.9, 0.9, 0.9, 0.92, 0.95),
    ('EREP_10079', '62.jpg', 1, 'PERTAMAX', '02-02-2026', 12500, 12, 150000, 0, 0.97, 0.9, 0.93, 0.92, 0.93, 0.95),
    ('EREP_10079', '62.jpg', 2, 'PERTAMAX', '09-02-2026', 12500, 12, 150000, 0, 0.97, 0.9, 0.93, 0.92, 0.93, 0.95),
    ('EREP_10079', '62.jpg', 3, 'PERTAMAX', '16-02-2026', 12500, 12, 150000, 0, 0.97, 0.9, 0.93, 0.92, 0.93, 0.95),
    ('EREP_10079', '62.jpg', 4, 'PERTAMAX', '23-02-2026', 12500, 8, 100000, 0, 0.97, 0.9, 0.93, 0.92, 0.93, 0.95),
    ('EREP_10079', '62.jpg', 5, 'PERTAMAX', '25-02-2026', 12500, 16, 200000, 0, 0.97, 0.9, 0.93, 0.92, 0.93, 0.95),
    ('EREP_10043', '41.jpeg', 1, 'PERTAMAX', '20-01-2026', 12350, 16.19, 200000, 0, 0.95, 0.9, 0.85, 0.85, 0.9, 0.9),
    ('EREP_10060', '42.jpeg', 1, 'PERTAMAX', '27-01-2026', 12350, 32.389, 400000, 0, 0.97, 0.9, 0.9, 0.9, 0.95, 0.9),
    ('EREP_10044', '43.jpg', 1, 'PERTAMAX', '09-07-2026', 16250, 24.61, 400000, 0, 0.95, 0.9, 0.93, 0.9, 0.94, 0.9),
    ('EREP_10061', '44.jpg', 1, 'PERTAMAX', '05-12-2025', 12750, 30, 382500, 0, 0.97, 0.85, 0.92, 0.93, 0.93, 0.9),
    ('EREP_10045', '53.jpeg', 1, 'PERTAMAX', '14-08-2026', 15950, 53.834, 858652, 0, 0.97, 0.88, 0.93, 0.92, 0.93, 0.9),
    ('EREP_10046', '54.jpeg', 1, 'PERTAMAX', '03-05-2026', 12300, 32.859, 404166, 0, 0.97, 0.9, 0.93, 0.9, 0.93, 0.95),
    ('EREP_10047', '48.png', 1, 'SHELL SUPER', '29-12-2025', 13000, 55.54, 722020, 0, 0.95, 0.9, 0.93, 0.9, 0.93, 0.95),
    ('EREP_10048', '61.png', 1, 'BP92', '04-10-2026', 16130, 33.34, 537774, 0, 0.97, 0.9, 0.88, 0.88, 0.93, 0.95),
    ('EREP_10049', '25.jpeg', 1, 'PERTAMAX', '22-07-2026', 16650, 3, 50000, 0, 0.97, 0.95, 0.95, 0.93, 0.95, 1)
) AS v (reimbursement_code, attachment_name, line_no, product_name, date_of_expense, price_per_liter, volume_liter,
        total_price, discount, c_product_name, c_date, c_price_per_liter, c_volume_liter, c_total_price, c_discount)
JOIN bbm_receipt i ON i.reimbursement_code = v.reimbursement_code
JOIN attachment a ON a.bbm_receipt_id = i.id AND a.name = v.attachment_name
JOIN ocr_reimbursement o ON o.attachment_id = a.id
ORDER BY o.id, v.line_no;

-- Where the file and the submitted data differ: the OCR line (by its number) and the submitted item it was compared with.
-- A receipt-level difference (date_of_expense) points at the receipt's first line and item; the grand total is checked
-- for the whole file (no line, no item). A receipt or product on one side only has no line (not in the file) or no
-- item (not submitted). likely_wrong / expected_value: what the arithmetic check found, when it could decide
-- (see receipt_records._verdict).
INSERT INTO ocr_difference (ocr_reimbursement_id, ocr_item_id, bbm_receipt_id, field_name, ocr_value, submitted_value, description,
                            likely_wrong, expected_value)
SELECT o.id, l.id, s.id, v.field_name, v.ocr_value, v.submitted_value, v.description, v.likely_wrong, v.expected_value
FROM (VALUES
    ('EREP_10004', '14.jpeg', 1, 'EXP_10004', 'product_name', 'PERTAMAX Hose 10.3', 'Pertamax 92',
     'The values differ (OCR confidence is high: 0.90). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10081', '14.jpeg', 1, 'EXP_10112', 'product_name', 'PERTAMAX Hose 10.3', 'Pertamax 92',
     'The values differ and OCR confidence is low (0.85), so it may be a misread. Check the image.', NULL, NULL),
    ('EREP_10081', '14.jpeg', 1, 'EXP_10112', 'total_price', '450000', '540000',
     'The OCR total_price (450,000) fits the other numbers on the receipt (quantity x unit_price = 449,960.25); the submitted value (540000) does not. The submitted value is probably wrong.', 'submitted', 449960.25),
    ('EREP_10081', '14.jpeg', NULL, NULL, 'grand_total', '450000', '540000',
     'Several numbers differ in this file, so one OCR misread cannot explain it. The values differ (OCR confidence is high: 0.90). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10005', '15.jpeg', 1, 'EXP_10005', 'volume_liter', NULL, '29.46',
     'The submitted quantity (29.46) fits the other numbers on the receipt (total_price / unit_price = 29.46); the OCR value (None) does not. Looks like an OCR misread.', 'ocr', 29.46),
    ('EREP_10007', '17.jpg', 1, 'EXP_10007', 'date_of_expense', '10-05-2026', '29-05-2026',
     'The values differ and OCR confidence is low (0.40), so it may be a misread. Check the image.', NULL, NULL),
    ('EREP_10007', '17.jpg', 1, 'EXP_10007', 'volume_liter', '2.85', '28.5',
     'The OCR quantity (2.85) fits the other numbers on the receipt (total_price / unit_price = 2.85); the submitted value (28.5) does not. The submitted value is probably wrong.', 'submitted', 2.846),
    ('EREP_10008', '21.jpeg', 1, 'EXP_10008', 'date_of_expense', '10-01-2026', '01-10-2026',
     'The values differ (OCR confidence is high: 0.93). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10010', '29.jpg', 1, 'EXP_10010', 'total_price', '646180', '664180',
     'The OCR total_price (646,180) fits the other numbers on the receipt (quantity x unit_price = 646,176); the submitted value (664180) does not. The submitted value is probably wrong.', 'submitted', 646176),
    ('EREP_10010', '29.jpg', NULL, NULL, 'grand_total', '646180', '664180',
     'Several numbers differ in this file, so one OCR misread cannot explain it. The values differ (OCR confidence is high: 0.93). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10012', '39.png', 1, 'EXP_10012', 'product_name', 'PERTAMAX', 'Performa > 92',
     'The values differ (OCR confidence is high: 0.92). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10013', '60.jpg', 2, 'EXP_10014', 'volume_liter', NULL, '30.58',
     'The submitted quantity (30.58) fits the other numbers on the receipt (total_price / unit_price = 30.58); the OCR value (None) does not. Looks like an OCR misread.', 'ocr', 30.58),
    ('EREP_10018', '18.jpeg', 1, 'EXP_10025', 'volume_liter', '39.48', '394.8',
     'The OCR quantity (39.48) fits the other numbers on the receipt (total_price / unit_price = 39.48); the submitted value (394.8) does not. The submitted value is probably wrong.', 'submitted', 39.48),
    ('EREP_10020', '64.jpeg', 2, NULL, 'product_name', 'PERTAMAX', NULL,
     'The image shows a receipt that was not submitted. Check the image.', NULL, NULL),
    ('EREP_10020', '64.jpeg', NULL, NULL, 'grand_total', '1000000', '800000',
     'Several numbers differ in this file, so one OCR misread cannot explain it. The values differ and OCR confidence is low (0.85), so it may be a misread. Check the image.', NULL, NULL),
    ('EREP_10073', '17.jpg', 1, 'EXP_10098', 'date_of_expense', NULL, '29-05-2026',
     'The receipt reading is empty for this field (unreadable). Check the image.', NULL, NULL),
    ('EREP_10024', '62.jpg', 4, 'EXP_10036', 'total_price', '100000', '10000',
     'The OCR total_price (100,000) fits the other numbers on the receipt (quantity x unit_price = 100,000); the submitted value (10000) does not. The submitted value is probably wrong.', 'submitted', 100000),
    ('EREP_10024', '62.jpg', NULL, NULL, 'grand_total', '750000', '660000',
     'Several numbers differ in this file, so one OCR misread cannot explain it. The values differ (OCR confidence is high: 0.90). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10075', '39.png', 1, 'EXP_10102', 'volume_liter', '31.76', '34.76',
     'The values differ and OCR confidence is low (0.40), so it may be a misread. Check the image.', NULL, NULL),
    ('EREP_10075', '39.png', NULL, NULL, 'grand_total', '410168', '410168',
     'The receipts don''t back the 410,168 claimed: their amounts are more than volume x price per liter gives. All their numbers back only 374,768. A number may have been changed, or the OCR misread one. Check the image.', NULL, NULL),
    ('EREP_10076', '18.jpeg', 1, 'EXP_10103', 'date_of_expense', '23-05-2026', '23-06-2026',
     'The values differ (OCR confidence is high: 0.90). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10029', '40.jpg', 1, 'EXP_10042', 'date_of_expense', '08-06-2026', '08-05-2026',
     'The values differ and OCR confidence is low (0.85), so it may be a misread. Check the image.', NULL, NULL),
    ('EREP_10032', '27.jpeg', NULL, 'EXP_10046', 'product_name', NULL, 'Pertamax 92',
     'A submitted receipt was not found in the image. Check the image.', NULL, NULL),
    ('EREP_10032', '27.jpeg', NULL, NULL, 'grand_total', '411066', '661066',
     'Several numbers differ in this file, so one OCR misread cannot explain it. The values differ (OCR confidence is high: 0.93). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10038', '35.jpg', 1, 'EXP_10056', 'date_of_expense', '17-07-2026', '17-07-2025',
     'The values differ (OCR confidence is high: 0.90). Check the image to see which one is right.', NULL, NULL),
    ('EREP_10046', '54.jpeg', 1, 'EXP_10064', 'total_price', '404166', '440166',
     'The OCR total_price (404,166) fits the other numbers on the receipt (quantity x unit_price = 404,165.7); the submitted value (440166) does not. The submitted value is probably wrong.', 'submitted', 404165.7)
) AS v (reimbursement_code, attachment_name, ocr_line_no, item_id, field_name, ocr_value, submitted_value, description,
        likely_wrong, expected_value)
JOIN bbm_receipt i ON i.reimbursement_code = v.reimbursement_code
JOIN attachment a ON a.bbm_receipt_id = i.id AND a.name = v.attachment_name
JOIN ocr_reimbursement o ON o.attachment_id = a.id
LEFT JOIN (SELECT id, ocr_reimbursement_id, row_number() OVER (PARTITION BY ocr_reimbursement_id ORDER BY id) AS line_no
           FROM ocr_bbm_receipt) l ON l.ocr_reimbursement_id = o.id AND l.line_no = v.ocr_line_no
LEFT JOIN bbm_receipt s ON s.reimbursement_code = v.reimbursement_code AND s.item_id = v.item_id
ORDER BY o.id, l.line_no NULLS LAST, s.id NULLS LAST, v.field_name;

COMMIT;

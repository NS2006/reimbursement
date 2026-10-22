-- Dummy reimbursement data for testing: 6 employees, 68 BBM reports, their items and receipt files.
-- Uses all 63 photos of backend/jobs/bbm_ocr/images (copied to backend/database/dummy_bbm_receipt/), one per report:
-- a BBM report has one attachment (the attachment table allows more for other reimbursement types). The values
-- come from backend/jobs/bbm_ocr/ground_truth/gt.json, so they are what each photo shows.
-- RB-064 .. RB-068 have a PDF file instead, made from some of these photos (a page per photo), to test PDF files;
-- they claim the same receipts as the photo reports again.
-- The other system sent the reports in 8 calls to POST /api/reimbursements; every report of one call has the same
-- received_at (the request's time):
--   A  10-08-2026 09:12  RB-001 .. RB-012, RB-053, RB-054
--   B  24-08-2026 14:40  RB-013 .. RB-020
--   C  07-09-2026 10:05  RB-021 .. RB-025, RB-055; revisions RB-007 r2, RB-020 r2
--   D  21-09-2026 11:20  RB-026 .. RB-034, RB-056 .. RB-058; revisions RB-012 r2, RB-018 r2
--   E  05-10-2026 09:45  RB-035 .. RB-042, RB-059; revisions RB-010 r2
--   F  12-10-2026 13:30  RB-043 .. RB-049, RB-060 .. RB-062; revisions RB-018 r3, RB-024 r2
--   G  18-10-2026 10:10  RB-050 .. RB-052, RB-063; revisions RB-032 r2
--   H  19-10-2026 14:15  RB-064 .. RB-068 (PDF files)
--   I  20-10-2026 08:30  revisions RB-004 r2, RB-006 r2
-- Most reports match their photos. Some have a deliberate mistake (marked WRONG) to test the validation, and several
-- were sent again corrected (revision 2 or 3). RB-004 and RB-006 were sent again after revision 1 was approved (by a
-- reviewer and by the OCR), which the website marks "Revised after approval". Some photos show several receipts (a month of fills on one photo),
-- so their report has several items.
-- Photos of the same receipt (the system does not look for double claims yet; good test cases when it does):
--   29.jpg / 63.jpg: the same Pertamax Turbo receipt (04-02-2026, Rp 646,180)
--   47.jpg / 60.jpg: 60.jpg shows 47.jpg's receipt (07-12-2025, Rp 650,000)
--   48.png / 60.jpg: 60.jpg shows 48.png's receipt (29-12-2025, Rp 722,020)
--   33.jpeg, 41.jpeg, 42.jpeg / 64.jpeg: 64.jpeg shows the three receipts of January 2026
-- total_price is the item amount before discount (as printed); grand_total is what was paid (after discount).
-- kilometer is made up: each employee's odometer grows with the litres of the fill before.
-- url: the link the file was sent with; the local backend serves the dummy files at /api/dummy-receipts/<file>
-- (py -m backend.app), so a report can be sent to POST /api/reimbursements locally.
-- storage_path: where the file is kept; the dummy reports use the dummy folder itself (see file_storage.py).
-- payload_hash: computed with reimbursement_service.payload_hash, the same hash POST /api/reimbursements stores.
-- Run after schema.sql. Running it again resets the dummy employees' reports
-- (their revisions, items, photos, comments and OCR results are deleted with them, then inserted fresh).
BEGIN;

INSERT INTO employee (employee_no, name) VALUES
    ('EMP-001', 'Employee One'),
    ('EMP-002', 'Employee Two'),
    ('EMP-003', 'Employee Three'),
    ('EMP-004', 'Employee Four'),
    ('EMP-005', 'Employee Five'),
    ('EMP-006', 'Employee Six')
ON CONFLICT (employee_no) DO UPDATE
    SET name = EXCLUDED.name;

DELETE FROM reimbursement_report WHERE employee_no IN ('EMP-001', 'EMP-002', 'EMP-003', 'EMP-004', 'EMP-005', 'EMP-006');

INSERT INTO reimbursement_report (reimbursement_code, employee_no, reimbursement_type) VALUES
    ('RB-001', 'EMP-001', 'bbm'),
    ('RB-002', 'EMP-002', 'bbm'),
    ('RB-003', 'EMP-006', 'bbm'),
    ('RB-004', 'EMP-006', 'bbm'),
    ('RB-005', 'EMP-003', 'bbm'),
    ('RB-006', 'EMP-001', 'bbm'),
    ('RB-007', 'EMP-006', 'bbm'),
    ('RB-008', 'EMP-003', 'bbm'),
    ('RB-009', 'EMP-004', 'bbm'),
    ('RB-010', 'EMP-006', 'bbm'),
    ('RB-011', 'EMP-006', 'bbm'),
    ('RB-012', 'EMP-006', 'bbm'),
    ('RB-013', 'EMP-003', 'bbm'),
    ('RB-014', 'EMP-002', 'bbm'),
    ('RB-015', 'EMP-005', 'bbm'),
    ('RB-016', 'EMP-005', 'bbm'),
    ('RB-017', 'EMP-004', 'bbm'),
    ('RB-018', 'EMP-002', 'bbm'),
    ('RB-019', 'EMP-001', 'bbm'),
    ('RB-020', 'EMP-005', 'bbm'),
    ('RB-021', 'EMP-006', 'bbm'),
    ('RB-022', 'EMP-003', 'bbm'),
    ('RB-023', 'EMP-002', 'bbm'),
    ('RB-024', 'EMP-004', 'bbm'),
    ('RB-025', 'EMP-005', 'bbm'),
    ('RB-026', 'EMP-005', 'bbm'),
    ('RB-027', 'EMP-005', 'bbm'),
    ('RB-028', 'EMP-006', 'bbm'),
    ('RB-029', 'EMP-002', 'bbm'),
    ('RB-030', 'EMP-003', 'bbm'),
    ('RB-031', 'EMP-006', 'bbm'),
    ('RB-032', 'EMP-005', 'bbm'),
    ('RB-033', 'EMP-003', 'bbm'),
    ('RB-034', 'EMP-004', 'bbm'),
    ('RB-035', 'EMP-006', 'bbm'),
    ('RB-036', 'EMP-002', 'bbm'),
    ('RB-037', 'EMP-005', 'bbm'),
    ('RB-038', 'EMP-005', 'bbm'),
    ('RB-039', 'EMP-003', 'bbm'),
    ('RB-040', 'EMP-005', 'bbm'),
    ('RB-041', 'EMP-006', 'bbm'),
    ('RB-042', 'EMP-002', 'bbm'),
    ('RB-043', 'EMP-005', 'bbm'),
    ('RB-044', 'EMP-005', 'bbm'),
    ('RB-045', 'EMP-006', 'bbm'),
    ('RB-046', 'EMP-006', 'bbm'),
    ('RB-047', 'EMP-003', 'bbm'),
    ('RB-048', 'EMP-002', 'bbm'),
    ('RB-049', 'EMP-004', 'bbm'),
    ('RB-050', 'EMP-006', 'bbm'),
    ('RB-051', 'EMP-003', 'bbm'),
    ('RB-052', 'EMP-002', 'bbm'),
    ('RB-053', 'EMP-004', 'bbm'),
    ('RB-054', 'EMP-004', 'bbm'),
    ('RB-055', 'EMP-002', 'bbm'),
    ('RB-056', 'EMP-005', 'bbm'),
    ('RB-057', 'EMP-004', 'bbm'),
    ('RB-058', 'EMP-004', 'bbm'),
    ('RB-059', 'EMP-006', 'bbm'),
    ('RB-060', 'EMP-005', 'bbm'),
    ('RB-061', 'EMP-005', 'bbm'),
    ('RB-062', 'EMP-004', 'bbm'),
    ('RB-063', 'EMP-002', 'bbm'),
    ('RB-064', 'EMP-004', 'bbm'),
    ('RB-065', 'EMP-002', 'bbm'),
    ('RB-066', 'EMP-006', 'bbm'),
    ('RB-067', 'EMP-005', 'bbm'),
    ('RB-068', 'EMP-005', 'bbm');

-- In the order they were received.
INSERT INTO reimbursement_revision (reimbursement_code, revision_no, grand_total, received_at, payload_hash) VALUES
    ('RB-001', 1, 1358170, '2026-08-10 09:12:00+07:00', '59604e8f4a77da4dc9432114663bcbd5cc04a967e3756e9242b41ba39cb42745'),  -- call A, 1.jpeg: correct
    ('RB-002', 1, 382225, '2026-08-10 09:12:00+07:00', '7336c2a87671993182a6a4f1f8f7cdf59d71ad5ef4456de08a1d035180b71a80'),  -- call A, 3.jpg: correct
    ('RB-003', 1, 253200, '2026-08-10 09:12:00+07:00', '569867160986f4966e43c2b8194deab958237eb3be9af41a4f977243c71023ef'),  -- call A, 11.jpeg: correct
    ('RB-004', 1, 450000, '2026-08-10 09:12:00+07:00', '9b45aec18b82fa2d95b1e312653a269d4e61400810404f9f999e60b2eda92642'),  -- call A, 14.jpeg: correct
    ('RB-005', 1, 382980, '2026-08-10 09:12:00+07:00', '55155ad452b3245a9c9797cf90d3c6c8bffc095f1fe90010e88addf8d8a794b9'),  -- call A, 15.jpeg: correct
    ('RB-006', 1, 549549, '2026-08-10 09:12:00+07:00', 'bbe1516c60109547e7c46b41b9c9dbe6083efcb007e3a593f08f9f2bc6a58206'),  -- call A, 16.jpg: correct
    ('RB-007', 1, 35000, '2026-08-10 09:12:00+07:00', 'ea797ae0a66775e7c05371fd36925282b6feee598a46ee0ad8594100f457f4b8'),  -- call A, 17.jpg: WRONG: volume 28.5 L, the photo says 2.85 L
    ('RB-008', 1, 380746, '2026-08-10 09:12:00+07:00', 'a6662e580d1252771b768d0a24d5610efe5154fccaf235d3fb5ca9fa6b4ca1aa'),  -- call A, 21.jpeg: WRONG: date 01-10-2026, the photo says 10/01/2026 (day and month swapped)
    ('RB-009', 1, 15000, '2026-08-10 09:12:00+07:00', 'c0b92afb4e1b084da917db8c22af3ba90aa409c02f57845026c18a79e0ef6a5f'),  -- call A, 2.jpg: correct
    ('RB-053', 1, 100000, '2026-08-10 09:12:00+07:00', 'f1468503ad7da8ac4f10329f17ce1af48bd515415e2b7a3f938f9f8acfcee9a9'),  -- call A, 4.jpg: correct
    ('RB-054', 1, 150000, '2026-08-10 09:12:00+07:00', 'ff3a7cb794e70b45e45f676f05fbc5a6e62e0535fabeb6a4ba865b8e05380364'),  -- call A, 8.jpeg: correct
    ('RB-010', 1, 664180, '2026-08-10 09:12:00+07:00', 'f483fc6fa309c6602909797cf214e64ddc920785343b05b4dee02ed980072251'),  -- call A, 29.jpg: WRONG: amount 664,180, the photo says 646,180 (also in grand_total)
    ('RB-011', 1, 519303, '2026-08-10 09:12:00+07:00', '647c01b303865d37a269d8c055041481ee46be49f15814a31214807524cac6c6'),  -- call A, 32.jpeg: WRONG: price per liter 17,200, the photo says 12,700
    ('RB-012', 1, 410168, '2026-08-10 09:12:00+07:00', '9a7a34c61bd7aa215c049704d5332cb2f6344ab9742a7a86dcd9451e1100ca76'),  -- call A, 39.png: WRONG: product pertamax turbo, the photo says pertamax
    ('RB-013', 1, 1769560, '2026-08-24 14:40:00+07:00', 'fb6fb290c98c8bc9ffffcaa60e0b8f5cbb72413106be721c8920bb996f7337f3'),  -- call B, 60.jpg: correct
    ('RB-014', 1, 2550000, '2026-08-24 14:40:00+07:00', 'd821b4022f29abdc98b0a3c54b50733f0cafb2b2278795c5f24956bc31b94b5e'),  -- call B, 57.jpeg: correct
    ('RB-015', 1, 400119, '2026-08-24 14:40:00+07:00', 'b875ef8f19f92a27eb098f412204487bd31ca4d3d71d339c28b56747e04c04da'),  -- call B, 5.jpeg: correct
    ('RB-016', 1, 450060, '2026-08-24 14:40:00+07:00', '60f41b7fb4038acb37457997203db370e0e98e0621e21fa1d9fc1b31e1f7506c'),  -- call B, 6.jpg: correct
    ('RB-017', 1, 250000, '2026-08-24 14:40:00+07:00', 'b0fbe3b7609aaab883e34a334aff0f65a485a2b63976864c232a297d5bc7b88f'),  -- call B, 10.jpg: correct
    ('RB-018', 1, 489157, '2026-08-24 14:40:00+07:00', '4fdd8e0ac5bd2556cf657f78c06a09129daf0567c19651a26f0116edd6d25653'),  -- call B, 18.jpeg: WRONG: volume typed 10 times too large
    ('RB-019', 1, 750000, '2026-08-24 14:40:00+07:00', 'aaffbb28b974abc443cd854140ee433b5bbafe03c1ecac676ceeb377a6320ec7'),  -- call B, 26.jpeg: correct
    ('RB-020', 1, 800000, '2026-08-24 14:40:00+07:00', 'c712d321a595024ba5f07888f6a55fb8e1f5a91300c7e84a9b7bd36a527049a9'),  -- call B, 64.jpeg: WRONG: the 2nd receipt on the photo (20-01-2026, Rp 200,000) is missing
    ('RB-007', 2, 35000, '2026-09-07 10:05:00+07:00', '66a6acb6f64b61a5d0732dabf5b650014baa275cc313d6430d8fff61c2805128'),  -- call C, 17.jpg: volume corrected
    ('RB-020', 2, 1000000, '2026-09-07 10:05:00+07:00', '336bb3670d5b72e5707875297e816fb69d1f31fc8a760d53a858c6b621e08370'),  -- call C, 64.jpeg: the missing receipt added (the OCR of revision 1 found it)
    ('RB-021', 1, 200000, '2026-09-07 10:05:00+07:00', 'a6c4f69740e3350200144993c407cb717e99d952ae260de41e1dde200f0620a0'),  -- call C, 28.jpeg: correct
    ('RB-022', 1, 500000, '2026-09-07 10:05:00+07:00', 'ca2a928c617e1ea72fea77fb616115ac9e39188717855f063094380652af4097'),  -- call C, 24.jpeg: correct
    ('RB-023', 1, 686468, '2026-09-07 10:05:00+07:00', '68bc4e3f4a9bf1e8ad3db0641ccd7792a04ff8b1493c72dd57e74f6aaa063c8b'),  -- call C, 51.jpg: correct
    ('RB-055', 1, 441555, '2026-09-07 10:05:00+07:00', '177a2877f0fa8faadc7f16c5a5db9d08d3797abbfc8380e66691b70d7141379f'),  -- call C, 52.jpg: correct
    ('RB-024', 1, 660000, '2026-09-07 10:05:00+07:00', '5ffc053c6422ed00f4b80bad6341cd99c40568b7b1eff19f4a6a1c9466a85f23'),  -- call C, 62.jpg: WRONG: amount of the 4th receipt 10,000, the photo says 100,000
    ('RB-025', 1, 300000, '2026-09-07 10:05:00+07:00', '06ea804d74e1daffc3ce8176bfdcd47bffa1cc9448216c914dbdc80682965926'),  -- call C, 13.jpg: correct
    ('RB-012', 2, 410168, '2026-09-21 11:20:00+07:00', '1f83213dc098a196757b7d485be9a0086c1767bad0f342915674d795abce5758'),  -- call D, 39.png: product corrected
    ('RB-018', 2, 489157, '2026-09-21 11:20:00+07:00', '798178298d6fea7a97f8166136a1c1fa8cc18f2f62e62f0613a6f2fc0574652f'),  -- call D, 18.jpeg: WRONG: volume corrected, but the date is now 23-06-2026; the photo says 2026-05-23
    ('RB-026', 1, 430080, '2026-09-21 11:20:00+07:00', 'e50116e7d94ce6e1036437f6410c85bee66770f7cd736c3b79da8a47f560cf47'),  -- call D, 22.jpg: correct
    ('RB-027', 1, 500000, '2026-09-21 11:20:00+07:00', '09a14d11a6460a120e67edf9356768d4f1e03aa2a2b141c57246cedda18946bb'),  -- call D, 23.jpeg: correct
    ('RB-028', 1, 200000, '2026-09-21 11:20:00+07:00', '2795089272cedd2ee8f3316c8f9b926b8ed983c9176f3c90cd90adfbd28ec45f'),  -- call D, 31.jpeg: correct
    ('RB-029', 1, 450000, '2026-09-21 11:20:00+07:00', 'b128434eba46c41919a305641531c4bd515fd9e0c6b4f97a304f56573cabb45d'),  -- call D, 40.jpg: correct
    ('RB-030', 1, 430000, '2026-09-21 11:20:00+07:00', '6bcadf4f6cd2eba514c32a4203c91a84f85cd9810c7d03879dbc4c07f95a6b51'),  -- call D, 34.jpg: correct
    ('RB-031', 1, 402230, '2026-09-21 11:20:00+07:00', '8ca927ae7cf8eabea3e4f4cbf5762d095961fcce984a6e218f25e1c37ca430fc'),  -- call D, 45.jpg: correct
    ('RB-032', 1, 661066, '2026-09-21 11:20:00+07:00', '78513e6113b644abda2101494babe146654035ea45ed35e2b0aa4d7d4cbba587'),  -- call D, 27.jpeg: WRONG: an extra item (30-03-2026, Rp 250,000) that is not on the photo
    ('RB-056', 1, 815590, '2026-09-21 11:20:00+07:00', 'a5d34960f546fdd6d5322691efd0a9f466ae6bc78611caf7092b083af13ec680'),  -- call D, 30.jpg: correct
    ('RB-033', 1, 1005789, '2026-09-21 11:20:00+07:00', '42845df79a15e304e56fb1424d01462dd5d65d48d9781bd256630fbe21ab105c'),  -- call D, 59.jpg: correct
    ('RB-034', 1, 20630, '2026-09-21 11:20:00+07:00', 'ef6667702d70c535eedc0dc05af797b2ab571cf6cedce68d0538dd335e42d0c7'),  -- call D, 12.jpg: correct
    ('RB-057', 1, 40000, '2026-09-21 11:20:00+07:00', '6ac4862b6c0ec3777a88d627e6fc5d7699ec29be20406d8e46a1453a8549cdea'),  -- call D, 19.jpeg: correct
    ('RB-058', 1, 40000, '2026-09-21 11:20:00+07:00', '941ecff324fadaa877a1a3491448c2ded0cfb8c712b4506038a0f4090fc0e5a9'),  -- call D, 20.jpg: correct
    ('RB-010', 2, 646180, '2026-10-05 09:45:00+07:00', '5d9bc20f64f42b6a18a5e670d3551d6ac69329ed529f9e440831ecaf8bc44abc'),  -- call E, 29.jpg: amount corrected
    ('RB-035', 1, 863100, '2026-10-05 09:45:00+07:00', '85450de512b95acd64f187c85e2c3319023d6f9564e76d5c2b6e04cb76bbc1a1'),  -- call E, 58.jpg: correct
    ('RB-036', 1, 370000, '2026-10-05 09:45:00+07:00', '576e7cdef0b099c9119df508509d9515596b1d189bc4066fd3fcc460fa18e021'),  -- call E, 46.jpeg: correct
    ('RB-037', 1, 400000, '2026-10-05 09:45:00+07:00', 'd701434bfb8e2e3534237ea5f66a03c60be46e920e0f0345b1dedec03d1608b4'),  -- call E, 33.jpeg: correct
    ('RB-038', 1, 438750, '2026-10-05 09:45:00+07:00', 'f40980907233200e49fb8007d384818fd58d386036b8d43602951a1a13d01224'),  -- call E, 35.jpg: WRONG: date 17-07-2025, the photo says 17/07/2026
    ('RB-039', 1, 650000, '2026-10-05 09:45:00+07:00', '8a023f9137c13ad97ba7a1c57c89775e4fd68e7d9b6c1f976aa82aac309c5e18'),  -- call E, 47.jpg: correct
    ('RB-040', 1, 400000, '2026-10-05 09:45:00+07:00', 'b251962e51a5802c24638367b6021b15d6df400b9320ec3973a3bf1c44e401b9'),  -- call E, 38.jpg: correct
    ('RB-041', 1, 399380, '2026-10-05 09:45:00+07:00', '7751fc2429e0725e20fda4b73a9fce14673d65292bd878fb312ded9f42ca1683'),  -- call E, 49.jpg: correct
    ('RB-059', 1, 231120, '2026-10-05 09:45:00+07:00', 'dcaf4921861bfa35870d4d69fa81ac1b505d4a1a7177804a72a35d7f7759e9f3'),  -- call E, 50.jpg: correct
    ('RB-042', 1, 349546, '2026-10-05 09:45:00+07:00', '12492fcd05ec8982e5fb19af79b059b85eed70ec10c18f52fb81213984041627'),  -- call E, 55.jpeg: correct
    ('RB-018', 3, 489157, '2026-10-12 13:30:00+07:00', '6790acb3bd2c29095734a957fc104e759437b0719edc3b5d371303d252cbe2b2'),  -- call F, 18.jpeg: date corrected
    ('RB-024', 2, 750000, '2026-10-12 13:30:00+07:00', 'a82cb54e0e6fdfeb7ac8b586175d5e6978bd8ac0cc88233b5c172cb29f552ac7'),  -- call F, 62.jpg: amount corrected
    ('RB-043', 1, 200000, '2026-10-12 13:30:00+07:00', '92e304e3b1ecca6017209deb6d280123e1c6db5c6cc4d86be1172077926f8757'),  -- call F, 41.jpeg: correct
    ('RB-060', 1, 400000, '2026-10-12 13:30:00+07:00', '6563a97537fa5d08eb6178ef30cb8674f06474f9b55b6910e20faf5855aa55d1'),  -- call F, 42.jpeg: correct
    ('RB-044', 1, 400000, '2026-10-12 13:30:00+07:00', '81a27c0ec5e5d9291d3c69fa6c21418db8ac8bd980b00a4042a12e563daa23bf'),  -- call F, 43.jpg: correct
    ('RB-061', 1, 382500, '2026-10-12 13:30:00+07:00', '81a1454969c5c0785ee2488733cab5d7ecba00d743a7ef200075ad4cd6ee8199'),  -- call F, 44.jpg: correct
    ('RB-045', 1, 858652, '2026-10-12 13:30:00+07:00', 'e5f0f53638a6a0bfebcc855302e3ed30a9dc0850fb08742ce0046049bd9c3901'),  -- call F, 53.jpeg: correct
    ('RB-046', 1, 404166, '2026-10-12 13:30:00+07:00', '14e88746e7598b797ae9a7d351950fe5b6806a3fcb943a1a716fbf0631705304'),  -- call F, 54.jpeg: WRONG: amount 440,166, the photo says 404,166 (the grand total is right)
    ('RB-047', 1, 722020, '2026-10-12 13:30:00+07:00', 'cbc72d417d33948a2ce260f763e944899c88fe279cfdcbeebfe3c55053aec5ac'),  -- call F, 48.png: correct
    ('RB-048', 1, 537774, '2026-10-12 13:30:00+07:00', '09584a59133b7397ff5a114a4626d58eaf1617145aae1fada30ef8a2ea2f2fb5'),  -- call F, 61.png: correct
    ('RB-049', 1, 50000, '2026-10-12 13:30:00+07:00', '698373c4e4e30793ea2fe00f8d4dd00c579d62cd47fa3233d489ee7bfeb88bf3'),  -- call F, 25.jpeg: correct
    ('RB-062', 1, 20000, '2026-10-12 13:30:00+07:00', '8dbabd0e702e540c843920c38ec41c71ad23ffbea3a1649e155b1f1e06b93914'),  -- call F, 37.jpg: correct
    ('RB-032', 2, 411066, '2026-10-18 10:10:00+07:00', 'ffa339d89d1109667abc46b9e8c6ba5512fc3d0c79fa514c48061e830292f17e'),  -- call G, 27.jpeg: extra item removed
    ('RB-050', 1, 646180, '2026-10-18 10:10:00+07:00', '9c11db10be8414c9a7a1e5e60049e0c36a0c69a65be4dcde5933a6f25a6e3209'),  -- call G, 63.jpg: correct
    ('RB-051', 1, 522773, '2026-10-18 10:10:00+07:00', '4343684ff6a41e4679fc79acfd3b75edac60c21c1bf68392b9817f8d4858ebd7'),  -- call G, 56.jpeg: correct
    ('RB-052', 1, 700000, '2026-10-18 10:10:00+07:00', '6ef545226faad92a7e7fe8abf928e58a4d5c51d8868058038b45ba397d1ecd5a'),  -- call G, 7.jpg: correct
    ('RB-063', 1, 500000, '2026-10-18 10:10:00+07:00', '891833c3274a34370df43a9dc54716c4673453057bb5532d31c7c7d26cd2eedf'),  -- call G, 9.jpeg: correct
    ('RB-064', 1, 265000, '2026-10-19 14:15:00+07:00', '75135f91501d6e32a496a2631a46f43fe2884225eac4fe9319a1b8ed949e0dd4'),  -- call H, receipts_2_4_8.pdf (3 pages: 2.jpg, 4.jpg, 8.jpeg): correct
    ('RB-065', 1, 1128023, '2026-10-19 14:15:00+07:00', '8e498456603673d02049afdda968f693c1e5804bffde1b5f888b30a5dfe20797'),  -- call H, receipts_51_52.pdf (2 pages: 51.jpg, 52.jpg): correct
    ('RB-066', 1, 630500, '2026-10-19 14:15:00+07:00', '14ccb1d5a5aacf496f5162a0f372ca0ec3a171dffbd9de1f9d1a29325aa5cbd1'),  -- call H, receipts_49_50.pdf (2 pages: 49.jpg, 50.jpg): correct
    ('RB-067', 1, 782500, '2026-10-19 14:15:00+07:00', 'd94db8e3cf3393d076d4224f192e125dd8b9a7e843b59314baa09951e99bf35b'),  -- call H, receipts_43_44.pdf (2 pages: 43.jpg, 44.jpg): correct
    ('RB-068', 1, 1000000, '2026-10-19 14:15:00+07:00', '261b6d63f616751be26d8aac41382824435785a8818d0143e04d67b06f6bc808'),  -- call H, receipts_64.pdf (1 page: 64.jpeg, three receipts on it): correct
    ('RB-004', 2, 540000, '2026-10-20 08:30:00+07:00', '040da7796743ab082d552d0db1b3013aa3a3907db002b06a77031c862ce21b62'),  -- call I, 14.jpeg: WRONG: after the approval of revision 1, the amount sent again as 540,000; the photo says 450,000
    ('RB-006', 2, 549549, '2026-10-20 08:30:00+07:00', '8ab1e1afcdaf7746f3c8e10ae0d70701ae8d756e2d7d16ec71188771995f9a95');  -- call I, 16.jpg: after the approval of revision 1 (by the OCR), the kilometer corrected (48,942 -> 48,492)

-- Items and photos point to their revision's id, looked up by (reimbursement_code, revision_no).
INSERT INTO bbm_receipt (revision_id, item_id, product_name, date_of_expense, price_per_liter, volume_liter, kilometer, total_price)
SELECT r.id, v.item_id, v.product_name, v.date_of_expense::date, v.price_per_liter::numeric, v.volume_liter::numeric,
       v.kilometer, v.total_price::numeric
FROM (VALUES
    ('RB-001', 1, 'RB-001-1', 'pertamina dex', '2026-05-26', 27900, 48.68, 49532, 1358170),
    ('RB-002', 1, 'RB-002-1', 'bp92', '2026-01-20', 12500, 31.578, 22026, 394725),
    ('RB-003', 1, 'RB-003-1', 'pertalite', '2026-04-06', 16088, 25.32, 19202, 407348),
    ('RB-004', 1, 'RB-004-1', 'pertamax', '2025-12-18', 12750, 35.29, 15250, 450000),
    ('RB-004', 2, 'RB-004-1', 'pertamax', '2025-12-18', 12750, 35.29, 15250, 540000),
    ('RB-005', 1, 'RB-005-1', 'revvo 92', '2025-12-02', 13000, 29.46, 33942, 382980),
    ('RB-006', 1, 'RB-006-1', 'v-power diesel', '2026-01-08', 13860, 39.65, 48942, 549549),
    ('RB-006', 2, 'RB-006-1', 'v-power diesel', '2026-01-08', 13860, 39.65, 48492, 549549),
    ('RB-007', 1, 'RB-007-1', 'pertamax', '2026-05-29', 12300, 28.5, 20111, 35000),
    ('RB-007', 2, 'RB-007-1', 'pertamax', '2026-05-29', 12300, 2.85, 20111, 35000),
    ('RB-008', 1, 'RB-008-1', 'shell super', '2026-10-01', 12700, 29.98, 37903, 380746),
    ('RB-009', 1, 'RB-009-1', 'pertamax', '2026-05-02', 12300, 1.22, 10994, 15000),
    ('RB-010', 1, 'RB-010-1', 'pertamax turbo', '2026-02-04', 12700, 50.88, 16088, 664180),
    ('RB-010', 2, 'RB-010-1', 'pertamax turbo', '2026-02-04', 12700, 50.88, 16088, 646180),
    ('RB-011', 1, 'RB-011-1', 'super', '2026-01-23', 17200, 40.89, 15631, 519303),
    ('RB-012', 1, 'RB-012-1', 'pertamax turbo', '2026-02-26', 11800, 34.76, 17182, 410168),
    ('RB-012', 2, 'RB-012-1', 'pertamax', '2026-02-26', 11800, 34.76, 17182, 410168),
    ('RB-013', 1, 'RB-013-1', 'pertamax', '2025-12-07', 12750, 50.98, 34307, 650000),
    ('RB-013', 1, 'RB-013-2', 'shell super', '2025-12-12', 13000, 30.58, 35893, 397540),
    ('RB-013', 1, 'RB-013-3', 'shell super', '2025-12-29', 13000, 55.54, 36652, 722020),
    ('RB-014', 1, 'RB-014-1', 'bp92', '2026-04-07', 12390, 32.285, 23095, 400000),
    ('RB-014', 1, 'RB-014-2', 'bp92', '2026-04-10', 12390, 36.32, 23495, 450000),
    ('RB-014', 1, 'RB-014-3', 'bp92', '2026-04-15', 12390, 36.32, 24367, 450000),
    ('RB-014', 1, 'RB-014-4', 'bp92', '2026-04-20', 12390, 36.32, 24850, 450000),
    ('RB-014', 1, 'RB-014-5', 'bp92', '2026-04-24', 12390, 28.25, 25328, 350000),
    ('RB-014', 1, 'RB-014-6', 'bp92', '2026-04-28', 12390, 36.32, 26301, 450000),
    ('RB-015', 1, 'RB-015-1', 'pertamax', '2026-06-09', 12300, 32.53, 62047, 400119),
    ('RB-016', 1, 'RB-016-1', 'pertamax', '2026-03-27', 12300, 36.59, 61228, 450060),
    ('RB-017', 1, 'RB-017-1', 'pertamax', '2026-04-19', 12300, 20.32, 10739, 250000),
    ('RB-018', 1, 'RB-018-1', 'bp92', '2026-05-23', 12390, 394.8, 27138, 489157),
    ('RB-018', 2, 'RB-018-1', 'bp92', '2026-06-23', 12390, 39.48, 27138, 489157),
    ('RB-018', 3, 'RB-018-1', 'bp92', '2026-05-23', 12390, 39.48, 27138, 489157),
    ('RB-019', 1, 'RB-019-1', 'pertamina dex', '2026-01-07', 13600, 55.147, 48157, 750000),
    ('RB-020', 1, 'RB-020-1', 'pertamax 92', '2026-01-06', 12350, 32.38, 58258, 400000),
    ('RB-020', 1, 'RB-020-3', 'pertamax', '2026-01-27', 12350, 32.389, 59526, 400000),
    ('RB-020', 2, 'RB-020-1', 'pertamax 92', '2026-01-06', 12350, 32.38, 58258, 400000),
    ('RB-020', 2, 'RB-020-2', 'pertamax', '2026-01-20', 12350, 16.19, 59086, 200000),
    ('RB-020', 2, 'RB-020-3', 'pertamax', '2026-01-27', 12350, 32.389, 59526, 400000),
    ('RB-021', 1, 'RB-021-1', 'pertamax green', '2026-06-27', 17000, 11.765, 20181, 200000),
    ('RB-022', 1, 'RB-022-1', 'revvo 92', '2025-12-08', 13000, 38.46, 35480, 500000),
    ('RB-023', 1, 'RB-023-1', 'bp92', '2026-04-27', 12390, 55.405, 25685, 686468),
    ('RB-024', 1, 'RB-024-1', 'pertamax', '2026-02-02', 12500, 12, 9797, 150000),
    ('RB-024', 1, 'RB-024-2', 'pertamax', '2026-02-09', 12500, 12, 9964, 150000),
    ('RB-024', 1, 'RB-024-3', 'pertamax', '2026-02-16', 12500, 12, 10174, 150000),
    ('RB-024', 1, 'RB-024-4', 'pertamax', '2026-02-23', 12500, 8, 10370, 10000),
    ('RB-024', 1, 'RB-024-5', 'pertamax', '2026-02-25', 12500, 16, 10513, 200000),
    ('RB-024', 2, 'RB-024-1', 'pertamax', '2026-02-02', 12500, 12, 9797, 150000),
    ('RB-024', 2, 'RB-024-2', 'pertamax', '2026-02-09', 12500, 12, 9964, 150000),
    ('RB-024', 2, 'RB-024-3', 'pertamax', '2026-02-16', 12500, 12, 10174, 150000),
    ('RB-024', 2, 'RB-024-4', 'pertamax', '2026-02-23', 12500, 8, 10370, 100000),
    ('RB-024', 2, 'RB-024-5', 'pertamax', '2026-02-25', 12500, 16, 10513, 200000),
    ('RB-025', 1, 'RB-025-1', 'pertamax', '2026-07-30', NULL, 18.46, 63082, 300000),
    ('RB-026', 1, 'RB-026-1', 'pertamax', '2026-01-27', 12350, 34.824, 59940, 430080),
    ('RB-027', 1, 'RB-027-1', 'pertamax', '2025-12-01', 12750, 39.21, 57366, 500000),
    ('RB-028', 1, 'RB-028-1', 'pertalite', '2026-02-26', 10000, 20, 17585, 200000),
    ('RB-029', 1, 'RB-029-1', 'bp92', '2026-05-08', 12390, 36.32, 26731, 450000),
    ('RB-030', 1, 'RB-030-1', 'shell super', '2025-12-17', 13000, 33.07, 36284, 430000),
    ('RB-031', 1, 'RB-031-1', 'pertamax turbo', '2026-08-07', 18300, 21.98, 20327, 402230),
    ('RB-032', 1, 'RB-032-1', 'pertamax', '2026-03-29', 12300, 33.42, 61661, 411066),
    ('RB-032', 1, 'RB-032-2', 'pertamax', '2026-03-30', 12350, 20.243, 61873, 250000),
    ('RB-032', 2, 'RB-032-1', 'pertamax', '2026-03-29', 12300, 33.42, 61661, 411066),
    ('RB-033', 1, 'RB-033-1', 'bp92', '2026-02-02', 12050, 23.698, 38292, 285561),
    ('RB-033', 1, 'RB-033-2', 'revvo 92', '2026-02-13', 12050, 19.77, 38567, 238228),
    ('RB-033', 1, 'RB-033-3', 'revvo 92', '2026-02-25', 12050, 40, 38823, 482000),
    ('RB-034', 1, 'RB-034-1', 'pertamax', '2026-05-29', 12600, 1.64, 11300, 20630),
    ('RB-035', 1, 'RB-035-1', 'pertalite', '2026-03-01', 10000, 35.02, 17801, 350200),
    ('RB-035', 1, 'RB-035-2', 'pertalite', '2026-03-10', 10449, 32.79, 18186, 342623),
    ('RB-035', 1, 'RB-035-3', 'Pertalite', '2026-03-18', 10000, 18.5, 18968, 185000),
    ('RB-036', 1, 'RB-036-1', 'bp92', '2026-03-12', 12390, 29.865, 22771, 370000),
    ('RB-037', 1, 'RB-037-1', 'pertamax 92', '2026-01-06', 12350, 32.38, 58687, 400000),
    ('RB-038', 1, 'RB-038-1', 'pertamax', '2025-07-17', 16250, 27, 62749, 438750),
    ('RB-039', 1, 'RB-039-1', 'pertamax', '2025-12-07', 12750, 50.98, 34879, 650000),
    ('RB-040', 1, 'RB-040-1', 'pertamax', '2026-02-18', 11800, 33.89, 60856, 400000),
    ('RB-041', 1, 'RB-041-1', 'pertamax', '2026-03-10', 12300, 32.47, 18590, 399380),
    ('RB-042', 1, 'RB-042-1', 'bp92', '2026-02-23', 12050, 30.008, 22438, 361596),
    ('RB-043', 1, 'RB-043-1', 'pertamax', '2026-01-20', 12350, 16.19, 59298, 200000),
    ('RB-044', 1, 'RB-044-1', 'pertamax', '2026-07-09', 16250, 24.61, 62451, 400000),
    ('RB-045', 1, 'RB-045-1', 'pertamax', '2026-08-14', 15950, 53.834, 20589, 858652),
    ('RB-046', 1, 'RB-046-1', 'pertamax', '2026-05-03', 12300, 32.859, 19724, 440166),
    ('RB-047', 1, 'RB-047-1', 'shell super', '2025-12-29', 13000, 55.54, 37264, 722020),
    ('RB-048', 1, 'RB-048-1', 'bp92', '2026-10-04', 16130, 33.34, 28068, 537774),
    ('RB-049', 1, 'RB-049-1', 'pertamax', '2026-07-22', 16650, 3, 11517, 50000),
    ('RB-050', 1, 'RB-050-1', 'pertamax turbo', '2026-02-04', 12700, 50.88, 16646, 646180),
    ('RB-051', 1, 'RB-051-1', 'revvo 92', '2026-08-21', 16130, 32.41, 39267, 522773),
    ('RB-052', 1, 'RB-052-1', 'bp92', '2026-07-08', 16670, 41.992, 27571, 700000),
    ('RB-053', 1, 'RB-053-1', 'pertamax', '2026-06-28', 16250, 6.15, 11416, 100000),
    ('RB-054', 1, 'RB-054-1', 'pertamax', '2026-05-13', 12300, 12.195, 11139, 150000),
    ('RB-055', 1, 'RB-055-1', 'bp92', '2026-04-12', 12390, 35.638, 23943, 441555),
    ('RB-056', 1, 'RB-056-1', 'pertamax', '2026-08-02', 15950, 51.13, 63311, 815590),
    ('RB-057', 1, 'RB-057-1', 'pertamax', '2026-06-03', 12600, 3.18, 11345, 40000),
    ('RB-058', 1, 'RB-058-1', 'pertamax', '2026-05-08', 12600, 3.18, 11079, 40000),
    ('RB-059', 1, 'RB-059-1', 'pertamax', '2026-04-20', 12300, 18.79, 19500, 231120),
    ('RB-060', 1, 'RB-060-1', 'pertamax', '2026-01-27', 12350, 32.389, 60418, 400000),
    ('RB-061', 1, 'RB-061-1', 'pertamax', '2025-12-05', 12750, 30, 57863, 382500),
    ('RB-062', 1, 'RB-062-1', 'pertalite', '2026-05-05', 10000, 2, 11042, 20000),
    ('RB-063', 1, 'RB-063-1', 'bp92', '2025-12-02', 13000, 38.462, 21520, 500000),
    ('RB-064', 1, 'RB-064-1', 'pertamax', '2026-05-02', 12300, 1.22, 10994, 15000),
    ('RB-064', 1, 'RB-064-2', 'pertamax', '2026-06-28', 16250, 6.15, 11416, 100000),
    ('RB-064', 1, 'RB-064-3', 'pertamax', '2026-05-13', 12300, 12.195, 11139, 150000),
    ('RB-065', 1, 'RB-065-1', 'bp92', '2026-04-27', 12390, 55.405, 25685, 686468),
    ('RB-065', 1, 'RB-065-2', 'bp92', '2026-04-12', 12390, 35.638, 23943, 441555),
    ('RB-066', 1, 'RB-066-1', 'pertamax', '2026-03-10', 12300, 32.47, 18590, 399380),
    ('RB-066', 1, 'RB-066-2', 'pertamax', '2026-04-20', 12300, 18.79, 19500, 231120),
    ('RB-067', 1, 'RB-067-1', 'pertamax', '2026-07-09', 16250, 24.61, 62451, 400000),
    ('RB-067', 1, 'RB-067-2', 'pertamax', '2025-12-05', 12750, 30, 57863, 382500),
    ('RB-068', 1, 'RB-068-1', 'pertamax 92', '2026-01-06', 12350, 32.38, 58258, 400000),
    ('RB-068', 1, 'RB-068-2', 'pertamax', '2026-01-20', 12350, 16.19, 59086, 200000),
    ('RB-068', 1, 'RB-068-3', 'pertamax', '2026-01-27', 12350, 32.389, 59526, 400000)
) AS v (reimbursement_code, revision_no, item_id, product_name, date_of_expense, price_per_liter, volume_liter, kilometer, total_price)
JOIN reimbursement_revision r USING (reimbursement_code, revision_no)
ORDER BY r.id, length(v.item_id), v.item_id;  -- RB-001-2 before RB-001-10

-- One photo per revision: a BBM report has one attachment.
INSERT INTO attachment (revision_id, name, url, sha256, storage_path, content_type)
SELECT r.id, v.name, v.url, v.sha256, v.storage_path, v.content_type
FROM (VALUES
    ('RB-001', 1, '1.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/1.jpeg', 'c1a06e2d577ca4cd8bfefd4fa25e701b335d158987f60a8af76be8b3fe01754d',
     'local:backend/database/dummy_bbm_receipt/1.jpeg', 'image/jpeg'),
    ('RB-002', 1, '3.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/3.jpg', '0d74621b8c2870bc2f07d8222ef392ffbf40d2e8aae897e6346309f1e0196c2f',
     'local:backend/database/dummy_bbm_receipt/3.jpg', 'image/jpeg'),
    ('RB-003', 1, '11.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/11.jpeg', 'd6bbdcbf215291ac6e8098339cd80ddb15fcdb954dda6cda4dbaa29b8de43034',
     'local:backend/database/dummy_bbm_receipt/11.jpeg', 'image/jpeg'),
    ('RB-004', 1, '14.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/14.jpeg', '5eb3717fd55829a6bacf476b33950801293d64615d80ec44560ba8ea7889959c',
     'local:backend/database/dummy_bbm_receipt/14.jpeg', 'image/jpeg'),
    ('RB-004', 2, '14.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/14.jpeg', '5eb3717fd55829a6bacf476b33950801293d64615d80ec44560ba8ea7889959c',
     'local:backend/database/dummy_bbm_receipt/14.jpeg', 'image/jpeg'),
    ('RB-005', 1, '15.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/15.jpeg', 'a7892e22122c614d69f7502c37d5af36f6ad947cbcfd5ece27e152ec7dc78a23',
     'local:backend/database/dummy_bbm_receipt/15.jpeg', 'image/jpeg'),
    ('RB-006', 1, '16.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/16.jpg', '1300c6baaedb408ed50bfbc4aa158d913977a0f2c575ed3d4bd99264205a4878',
     'local:backend/database/dummy_bbm_receipt/16.jpg', 'image/jpeg'),
    ('RB-006', 2, '16.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/16.jpg', '1300c6baaedb408ed50bfbc4aa158d913977a0f2c575ed3d4bd99264205a4878',
     'local:backend/database/dummy_bbm_receipt/16.jpg', 'image/jpeg'),
    ('RB-007', 1, '17.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/17.jpg', '4025b44a80ef3b95bb0c324041e7047bd05d8c12425d9ddfb6196d0b8c996db5',
     'local:backend/database/dummy_bbm_receipt/17.jpg', 'image/jpeg'),
    ('RB-007', 2, '17.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/17.jpg', '4025b44a80ef3b95bb0c324041e7047bd05d8c12425d9ddfb6196d0b8c996db5',
     'local:backend/database/dummy_bbm_receipt/17.jpg', 'image/jpeg'),
    ('RB-008', 1, '21.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/21.jpeg', '986c60800685939b4d0cc8b464e269e5265786eb9e63a9256b2257b0136eccef',
     'local:backend/database/dummy_bbm_receipt/21.jpeg', 'image/jpeg'),
    ('RB-009', 1, '2.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/2.jpg', '04186bd04455ff102e0f4f2a94597a485172597b5c523cceb7e8df2f70696de7',
     'local:backend/database/dummy_bbm_receipt/2.jpg', 'image/jpeg'),
    ('RB-010', 1, '29.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/29.jpg', 'f8a03d4b70ab5d1c044b9ffb97aab23746540fb10e612d335bd0a5fbceafb034',
     'local:backend/database/dummy_bbm_receipt/29.jpg', 'image/jpeg'),
    ('RB-010', 2, '29.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/29.jpg', 'f8a03d4b70ab5d1c044b9ffb97aab23746540fb10e612d335bd0a5fbceafb034',
     'local:backend/database/dummy_bbm_receipt/29.jpg', 'image/jpeg'),
    ('RB-011', 1, '32.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/32.jpeg', 'bea00b88c16386d322ebc626d2784e8fd21b4b96d29c9e64181520a6fa59f596',
     'local:backend/database/dummy_bbm_receipt/32.jpeg', 'image/jpeg'),
    ('RB-012', 1, '39.png', 'http://127.0.0.1:5000/api/dummy-receipts/39.png', '35550986f78b72b9af65abea5aba13c84544290105d01ce010fd2a23e009a5f5',
     'local:backend/database/dummy_bbm_receipt/39.png', 'image/png'),
    ('RB-012', 2, '39.png', 'http://127.0.0.1:5000/api/dummy-receipts/39.png', '35550986f78b72b9af65abea5aba13c84544290105d01ce010fd2a23e009a5f5',
     'local:backend/database/dummy_bbm_receipt/39.png', 'image/png'),
    ('RB-013', 1, '60.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/60.jpg', 'f505342335cd064f77995506444d92a7499d806ab0d70e30cfe5b5536e246305',
     'local:backend/database/dummy_bbm_receipt/60.jpg', 'image/jpeg'),
    ('RB-014', 1, '57.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/57.jpeg', '89668ab5f76c0157d85d82418ee9e27aeea6c0ada78edbc7a33fdf43d5e16c45',
     'local:backend/database/dummy_bbm_receipt/57.jpeg', 'image/jpeg'),
    ('RB-015', 1, '5.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/5.jpeg', '27e983fd0556a4a341dfdd0e81b5d179f13b1a1aeaf5ce9350f493cd9fdf385f',
     'local:backend/database/dummy_bbm_receipt/5.jpeg', 'image/jpeg'),
    ('RB-016', 1, '6.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/6.jpg', 'eeb99e17a72e39ed64a1e80ce9e2edc3fd37a47ea6b44e7b1de322471f65bbc2',
     'local:backend/database/dummy_bbm_receipt/6.jpg', 'image/jpeg'),
    ('RB-017', 1, '10.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/10.jpg', '6311d81d75975d08e658340c4940c5889fff692e2e68c2be4fba60df14e4c122',
     'local:backend/database/dummy_bbm_receipt/10.jpg', 'image/jpeg'),
    ('RB-018', 1, '18.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/18.jpeg', 'e127c1750afd4a8349965d8e3170d61b8215a6848402024786e2c24f455bd439',
     'local:backend/database/dummy_bbm_receipt/18.jpeg', 'image/jpeg'),
    ('RB-018', 2, '18.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/18.jpeg', 'e127c1750afd4a8349965d8e3170d61b8215a6848402024786e2c24f455bd439',
     'local:backend/database/dummy_bbm_receipt/18.jpeg', 'image/jpeg'),
    ('RB-018', 3, '18.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/18.jpeg', 'e127c1750afd4a8349965d8e3170d61b8215a6848402024786e2c24f455bd439',
     'local:backend/database/dummy_bbm_receipt/18.jpeg', 'image/jpeg'),
    ('RB-019', 1, '26.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/26.jpeg', '66937f14456eb31e6ccb93edb398fafe1611cb865f12f73409a5d40cc9654894',
     'local:backend/database/dummy_bbm_receipt/26.jpeg', 'image/jpeg'),
    ('RB-020', 1, '64.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/64.jpeg', 'b01617410c0100436aaa9394d0ea067bb0cd342bbfdebd678bd76cec98641b82',
     'local:backend/database/dummy_bbm_receipt/64.jpeg', 'image/jpeg'),
    ('RB-020', 2, '64.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/64.jpeg', 'b01617410c0100436aaa9394d0ea067bb0cd342bbfdebd678bd76cec98641b82',
     'local:backend/database/dummy_bbm_receipt/64.jpeg', 'image/jpeg'),
    ('RB-021', 1, '28.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/28.jpeg', 'e03503b78314fbaf153929bf5b5060b38b20b633ed556988dc901b9d5a71ee1b',
     'local:backend/database/dummy_bbm_receipt/28.jpeg', 'image/jpeg'),
    ('RB-022', 1, '24.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/24.jpeg', '313e769bc03ea9827fb8b1530a53250e1380bc3dd3db752162057bb8ed417f4d',
     'local:backend/database/dummy_bbm_receipt/24.jpeg', 'image/jpeg'),
    ('RB-023', 1, '51.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/51.jpg', '267188c4372e4532fb1e05aaf235693142b3ad0eb0ae37a50ba62f4dfb0be7ce',
     'local:backend/database/dummy_bbm_receipt/51.jpg', 'image/jpeg'),
    ('RB-024', 1, '62.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/62.jpg', 'f8901c6bd71b2aa667310ea86147d42cf1a53ea7a35e70ef54f78b08fc1c3321',
     'local:backend/database/dummy_bbm_receipt/62.jpg', 'image/jpeg'),
    ('RB-024', 2, '62.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/62.jpg', 'f8901c6bd71b2aa667310ea86147d42cf1a53ea7a35e70ef54f78b08fc1c3321',
     'local:backend/database/dummy_bbm_receipt/62.jpg', 'image/jpeg'),
    ('RB-025', 1, '13.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/13.jpg', 'd6a128d36dc8cf339684bc4f952e4a061439b2873f852115e336850a48d2af6e',
     'local:backend/database/dummy_bbm_receipt/13.jpg', 'image/jpeg'),
    ('RB-026', 1, '22.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/22.jpg', '016324d6b7625785eae53f4d5089a046006f6b9b86b613ca6696a23f39ad6f30',
     'local:backend/database/dummy_bbm_receipt/22.jpg', 'image/jpeg'),
    ('RB-027', 1, '23.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/23.jpeg', '9838b874caf2c147e5f501be75941200956af9d9f8f78c9f03fd026499a575d5',
     'local:backend/database/dummy_bbm_receipt/23.jpeg', 'image/jpeg'),
    ('RB-028', 1, '31.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/31.jpeg', 'e1f6a09237a58fee45e2d24a5ea84c099cf252e7af4a860cf1f9b360025ccf03',
     'local:backend/database/dummy_bbm_receipt/31.jpeg', 'image/jpeg'),
    ('RB-029', 1, '40.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/40.jpg', 'b62f59be73afa72cf409509c28d5bab8a568b716014fa1b211b24e70361b1e5e',
     'local:backend/database/dummy_bbm_receipt/40.jpg', 'image/jpeg'),
    ('RB-030', 1, '34.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/34.jpg', 'b9a08f1bf01a48970f83d981ceb2af7422868d349c40c629c5acb01130197f06',
     'local:backend/database/dummy_bbm_receipt/34.jpg', 'image/jpeg'),
    ('RB-031', 1, '45.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/45.jpg', 'c174623f27160decc59373f2c4babd956fb9737406631f250302600f9377d2e9',
     'local:backend/database/dummy_bbm_receipt/45.jpg', 'image/jpeg'),
    ('RB-032', 1, '27.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/27.jpeg', 'e6caf40cebaee92bb638363be0d067c467e8abc8291a0f33971d7f7c3936d030',
     'local:backend/database/dummy_bbm_receipt/27.jpeg', 'image/jpeg'),
    ('RB-032', 2, '27.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/27.jpeg', 'e6caf40cebaee92bb638363be0d067c467e8abc8291a0f33971d7f7c3936d030',
     'local:backend/database/dummy_bbm_receipt/27.jpeg', 'image/jpeg'),
    ('RB-033', 1, '59.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/59.jpg', 'b4b34faae93d65b6ee15c841618d829ebf2d1a250c9b4a96a838d2c8e990446f',
     'local:backend/database/dummy_bbm_receipt/59.jpg', 'image/jpeg'),
    ('RB-034', 1, '12.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/12.jpg', 'd67cfdbc86ed4c91e44ba538384d961faf844e43efc7b11016f414e121075430',
     'local:backend/database/dummy_bbm_receipt/12.jpg', 'image/jpeg'),
    ('RB-035', 1, '58.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/58.jpg', 'e13a4d6d8c834e54a6f514ab19a6f31f11134f36a4d4a626a8a1e474cb2ffe28',
     'local:backend/database/dummy_bbm_receipt/58.jpg', 'image/jpeg'),
    ('RB-036', 1, '46.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/46.jpeg', '6f75290310dae4de4a36ee09a5f7c31600a73ccf42a0a9bf30c0c97c3b5bf390',
     'local:backend/database/dummy_bbm_receipt/46.jpeg', 'image/jpeg'),
    ('RB-037', 1, '33.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/33.jpeg', 'e17ffe78e53060cd8674606eb18cd422889eb9cb1e8cc9f74dc925930e77619e',
     'local:backend/database/dummy_bbm_receipt/33.jpeg', 'image/jpeg'),
    ('RB-038', 1, '35.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/35.jpg', 'fe9a6b4644d34b3bf492833c855fe1a06f9c4a599efc2b38e3a7ef2516fcfd2c',
     'local:backend/database/dummy_bbm_receipt/35.jpg', 'image/jpeg'),
    ('RB-039', 1, '47.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/47.jpg', '34223efb5bddbb7b500be46ab433bbe69d31427c37a68d9cceb13695b8559fb7',
     'local:backend/database/dummy_bbm_receipt/47.jpg', 'image/jpeg'),
    ('RB-040', 1, '38.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/38.jpg', '09d087abba7465c92a3ddfe7484e0b5ec467699749174eb6c7bc4214d12d242a',
     'local:backend/database/dummy_bbm_receipt/38.jpg', 'image/jpeg'),
    ('RB-041', 1, '49.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/49.jpg', 'eafa72ebee77114853825cdb60ac950bced3b5a206623dd4e2d5df132589067d',
     'local:backend/database/dummy_bbm_receipt/49.jpg', 'image/jpeg'),
    ('RB-042', 1, '55.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/55.jpeg', 'd89be318313d0edd6efb3809661beadd3cac17e9fc7b3c3911be787970b66588',
     'local:backend/database/dummy_bbm_receipt/55.jpeg', 'image/jpeg'),
    ('RB-043', 1, '41.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/41.jpeg', 'c8ee2bebd105ae7985eb1da7aae45b3bf4aca7383df58b057c0357c6e84a6a8e',
     'local:backend/database/dummy_bbm_receipt/41.jpeg', 'image/jpeg'),
    ('RB-044', 1, '43.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/43.jpg', '1e59cd0c52f8b55bde745a66d1b26c4067e50b0db199681df42633c9114b3eec',
     'local:backend/database/dummy_bbm_receipt/43.jpg', 'image/jpeg'),
    ('RB-045', 1, '53.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/53.jpeg', '89f93e67484648a307eae8f5ab216f6710b06be14be683f63025601675966cf7',
     'local:backend/database/dummy_bbm_receipt/53.jpeg', 'image/jpeg'),
    ('RB-046', 1, '54.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/54.jpeg', '172f51e26b3648ea7af9a17cea0da5b3a49487425fea5c9331199b679acb7da2',
     'local:backend/database/dummy_bbm_receipt/54.jpeg', 'image/jpeg'),
    ('RB-047', 1, '48.png', 'http://127.0.0.1:5000/api/dummy-receipts/48.png', 'f1c0f77c7cbb7a62eeefa0c536fbcdf5990f5808ec3d87f1c0eee41b06cc7a26',
     'local:backend/database/dummy_bbm_receipt/48.png', 'image/png'),
    ('RB-048', 1, '61.png', 'http://127.0.0.1:5000/api/dummy-receipts/61.png', '0c609a6e2b7ae4d7152b111c25b64e9bbb38b75d8001778be7c6de8d7c3f2ed4',
     'local:backend/database/dummy_bbm_receipt/61.png', 'image/png'),
    ('RB-049', 1, '25.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/25.jpeg', '7bfd314bad09a96f1ac4c56f41a5b585130a755c6f6af5041b050c5857a66cc2',
     'local:backend/database/dummy_bbm_receipt/25.jpeg', 'image/jpeg'),
    ('RB-050', 1, '63.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/63.jpg', '3d9555a2e8f0a4116df168375d7ba19201e6916da6e371ec815eeed3f6238cc2',
     'local:backend/database/dummy_bbm_receipt/63.jpg', 'image/jpeg'),
    ('RB-051', 1, '56.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/56.jpeg', '61e5c09c4ab8138bc3230caa0e3efefcac063cea6aff7935ed01c3d870b8f730',
     'local:backend/database/dummy_bbm_receipt/56.jpeg', 'image/jpeg'),
    ('RB-052', 1, '7.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/7.jpg', '4b45fc4542ad2478a53365c747744a01c00aefb2c66927e1942673feae464ac3',
     'local:backend/database/dummy_bbm_receipt/7.jpg', 'image/jpeg'),
    ('RB-053', 1, '4.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/4.jpg', '3a9cfa1cfd7c0403ea33a860b4327f29b70d4302f904ae838fa0371e41905ebd',
     'local:backend/database/dummy_bbm_receipt/4.jpg', 'image/jpeg'),
    ('RB-054', 1, '8.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/8.jpeg', '6c098629353bb8cf3a81d12ef41b9bfbf84ce2ffc57e9a28d904badaf3ab3c79',
     'local:backend/database/dummy_bbm_receipt/8.jpeg', 'image/jpeg'),
    ('RB-055', 1, '52.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/52.jpg', 'e2ea4ad845a0b6cdf6a8433e5cd11d2746e7a9ba7bf73a404ee696eed74e0c62',
     'local:backend/database/dummy_bbm_receipt/52.jpg', 'image/jpeg'),
    ('RB-056', 1, '30.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/30.jpg', '5e9f37f92cb1414e4b3de2fc2e0d1b7da4a54024f4a603d65d3fa2a47c91d007',
     'local:backend/database/dummy_bbm_receipt/30.jpg', 'image/jpeg'),
    ('RB-057', 1, '19.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/19.jpeg', 'e5c8c2a2aae5d89625a7e2dc868857a5c0b2ed0290f470275c949fd871e0999d',
     'local:backend/database/dummy_bbm_receipt/19.jpeg', 'image/jpeg'),
    ('RB-058', 1, '20.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/20.jpg', 'd2c30227ea5a644d75f533244197080897c1b7292a551338f08a2640c1799d9c',
     'local:backend/database/dummy_bbm_receipt/20.jpg', 'image/jpeg'),
    ('RB-059', 1, '50.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/50.jpg', 'dade8bff75e58419209b103b2e5752e601ed6bdf7a942453b9cd3f2cca5f335b',
     'local:backend/database/dummy_bbm_receipt/50.jpg', 'image/jpeg'),
    ('RB-060', 1, '42.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/42.jpeg', '8f19914938f0bab8516caeb52d910249cb9814ce51f626237cf760a26aec4aa5',
     'local:backend/database/dummy_bbm_receipt/42.jpeg', 'image/jpeg'),
    ('RB-061', 1, '44.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/44.jpg', '0ca73b05a085e3abfe511f426080a3448811abca54f64e079136dc4adad0a5ea',
     'local:backend/database/dummy_bbm_receipt/44.jpg', 'image/jpeg'),
    ('RB-062', 1, '37.jpg', 'http://127.0.0.1:5000/api/dummy-receipts/37.jpg', '18ed0b5590ee13b72119b22e55bd24766843f5bc5d44e9727221e03cc36f8892',
     'local:backend/database/dummy_bbm_receipt/37.jpg', 'image/jpeg'),
    ('RB-063', 1, '9.jpeg', 'http://127.0.0.1:5000/api/dummy-receipts/9.jpeg', '50e70009c3fbdc2616978b243e16ba6e25a4d250646b0fd468393383413531e5',
     'local:backend/database/dummy_bbm_receipt/9.jpeg', 'image/jpeg'),
    ('RB-064', 1, 'receipts_2_4_8.pdf', 'http://127.0.0.1:5000/api/dummy-receipts/receipts_2_4_8.pdf', '5f58b67c88fe977d6c6fb307ebb402d190d544309d5d8492afd7beddad2a1e24',
     'local:backend/database/dummy_bbm_receipt/receipts_2_4_8.pdf', 'application/pdf'),
    ('RB-065', 1, 'receipts_51_52.pdf', 'http://127.0.0.1:5000/api/dummy-receipts/receipts_51_52.pdf', '77807b8dadc284ac310e0f52e39957cf4b20d210f1d021393e570295f214038a',
     'local:backend/database/dummy_bbm_receipt/receipts_51_52.pdf', 'application/pdf'),
    ('RB-066', 1, 'receipts_49_50.pdf', 'http://127.0.0.1:5000/api/dummy-receipts/receipts_49_50.pdf', 'd7205ebf78d2d38d9cd7decf8dd04003808d3a75075024430a4c1b7231c46d74',
     'local:backend/database/dummy_bbm_receipt/receipts_49_50.pdf', 'application/pdf'),
    ('RB-067', 1, 'receipts_43_44.pdf', 'http://127.0.0.1:5000/api/dummy-receipts/receipts_43_44.pdf', 'a7c6f95eac390c26fdc246def07667d9017ab058f8d6cbbdccfe01c4b49b2470',
     'local:backend/database/dummy_bbm_receipt/receipts_43_44.pdf', 'application/pdf'),
    ('RB-068', 1, 'receipts_64.pdf', 'http://127.0.0.1:5000/api/dummy-receipts/receipts_64.pdf', 'e0a1bd5556b70c49ca3c6d3d45686838b5f23c83de2d7d772805050e815ad7e3',
     'local:backend/database/dummy_bbm_receipt/receipts_64.pdf', 'application/pdf')
) AS v (reimbursement_code, revision_no, name, url, sha256, storage_path, content_type)
JOIN reimbursement_revision r USING (reimbursement_code, revision_no)
ORDER BY r.id;

COMMIT;

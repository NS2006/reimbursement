-- Dummy reimbursement data for testing: 6 employees, 78 BBM reports, their items and receipt files.
-- Uses all 63 photos of backend/jobs/bbm_ocr/images (copied to backend/database/dummy_bbm_receipt/). Each item has
-- its receipt file attached; a photo that shows several receipts (a month of fills) is attached to each of their
-- items. The values come from backend/jobs/bbm_ocr/ground_truth/gt.json, so they are what each photo shows.
-- EREP_10064 .. EREP_10066 and EREP_10068 have a PDF file instead, made from some of these photos (a page per photo),
-- to test PDF files; EREP_10067 has a photo per item (43.jpg, 44.jpg). They claim the same receipts as the photo
-- reports again.
-- product_name is the fuel type as Darwinbox sends it (its dropdown: Pertamax 92, Shell Super 92, BP 92, Vivo Ron 92,
-- Performa > 92, Pertalite 90, BP 90, Diesel/Dex). price_per_liter is not sent: the database computes it.
-- The other system sent the reports in 9 calls to POST /api/reimbursements; every report of one call has the same
-- received_at (the request's time):
--   A  10-08-2026 09:12  EREP_10001 .. EREP_10012, EREP_10053, EREP_10054
--   B  24-08-2026 14:40  EREP_10013 .. EREP_10020
--   C  07-09-2026 10:05  EREP_10021 .. EREP_10025, EREP_10055, EREP_10073, EREP_10074
--   D  21-09-2026 11:20  EREP_10026 .. EREP_10034, EREP_10056 .. EREP_10058, EREP_10075, EREP_10076
--   E  05-10-2026 09:45  EREP_10035 .. EREP_10042, EREP_10059, EREP_10077
--   F  12-10-2026 13:30  EREP_10043 .. EREP_10049, EREP_10060 .. EREP_10062, EREP_10078, EREP_10079
--   G  18-10-2026 10:10  EREP_10050 .. EREP_10052, EREP_10063, EREP_10080
--   H  19-10-2026 14:15  EREP_10064 .. EREP_10068 (PDF files; EREP_10067 a photo per item)
--   I  20-10-2026 08:30  EREP_10081, EREP_10082
-- Most reports match their photos. Some have a deliberate mistake (marked WRONG) to test the validation. A report is
-- never sent again: a rejected one was submitted again, corrected, under a new code (same photo, new item ids):
--   EREP_10007 -> EREP_10073      EREP_10012 -> EREP_10075      EREP_10018 -> EREP_10076 -> EREP_10078
--   EREP_10010 -> EREP_10077      EREP_10020 -> EREP_10074      EREP_10024 -> EREP_10079      EREP_10032 -> EREP_10080
-- Photos of the same receipt: possible double claims, which need a reviewer (a report submitted again after a
-- rejection is not one; schema.sql receipt_matches, stored by same_receipt.sql). The PDF reports (call H) claim theirs again too:
--   14.jpeg: EREP_10004 / EREP_10081, claimed again after a reviewer approved it, with a higher amount
--   16.jpg: EREP_10006 / EREP_10082, claimed again after the OCR approved it
--   29.jpg / 63.jpg: the same Pertamax Turbo receipt (04-02-2026, Rp 646,180)
--   47.jpg / 60.jpg: 60.jpg shows 47.jpg's receipt (07-12-2025, Rp 650,000)
--   48.png / 60.jpg: 60.jpg shows 48.png's receipt (29-12-2025, Rp 722,020)
--   33.jpeg, 41.jpeg, 42.jpeg / 64.jpeg: 64.jpeg shows the three receipts of January 2026
-- total_price is the item amount before discount (as printed); grand_total is what was paid (after discount).
-- kilometer is made up: each employee's odometer grows with the litres of the fill before.
-- url: the link the file was sent with; the local backend serves the dummy files at /api/dummy-receipts/<file>
-- (py -m backend.app), so a report can be sent to POST /api/reimbursements locally.
-- storage_path: where the file is kept; the dummy reports use the dummy folder itself (see file_storage.py).
-- payload_hash: the hash POST /api/reimbursements stores (reimbursement_service.payload_hash): SHA-256 of the
-- grand total and the items, each with its files by name and SHA-256.
-- Run after schema.sql. Running it again resets the dummy employees' reports
-- (their items, files, comments, decisions and OCR results are deleted with them, then inserted fresh).
BEGIN;

INSERT INTO employee (employee_no, name) VALUES
    ('06300001', 'Employee One'),
    ('06300002', 'Employee Two'),
    ('06300003', 'Employee Three'),
    ('06300004', 'Employee Four'),
    ('06300005', 'Employee Five'),
    ('06300006', 'Employee Six')
ON CONFLICT (employee_no) DO UPDATE
    SET name = EXCLUDED.name;

DELETE FROM reimbursement_report WHERE employee_no IN ('06300001', '06300002', '06300003', '06300004', '06300005', '06300006');

-- In the order they were received.
INSERT INTO reimbursement_report (reimbursement_code, employee_no, grand_total, received_at, payload_hash) VALUES
    ('EREP_10001', '06300001', 1358170, '2026-08-10 09:12:00+07:00', '3a7a0cc478fb910c00c797f2f0d875661b34e15d0d59dbf3a1ee70f5fda04614'),  -- call A, 1.jpeg: correct
    ('EREP_10002', '06300002', 382225, '2026-08-10 09:12:00+07:00', '0a4993a51fb11ea268e7b1b1c2926c3996ce873c9bc93b7910cc9dd60ac9033c'),  -- call A, 3.jpg: correct
    ('EREP_10003', '06300006', 253200, '2026-08-10 09:12:00+07:00', 'f0644bc5709c9ba5b8ce331b100e1604324439573d9ca451d118ad21e733d3b1'),  -- call A, 11.jpeg: correct
    ('EREP_10004', '06300006', 450000, '2026-08-10 09:12:00+07:00', 'df934a1ed63b0013dcb1649d68fae3d10ff5bf5e756eb962b2e6cf8df77c8be3'),  -- call A, 14.jpeg: correct
    ('EREP_10005', '06300003', 382980, '2026-08-10 09:12:00+07:00', '9831b6490a639313d63a30e30e59df6d80ad51b6403c78a4259efdca9f0e59a5'),  -- call A, 15.jpeg: correct
    ('EREP_10006', '06300001', 549549, '2026-08-10 09:12:00+07:00', '5c054aadd77ae2878a1b3edac4efc63971e433ad4078bf1814308a327d0c1097'),  -- call A, 16.jpg: correct
    ('EREP_10007', '06300006', 35000, '2026-08-10 09:12:00+07:00', '76b04ec43a803a655cfebfa170f89e987c6107fd98e2c890b09bab9d630ebd20'),  -- call A, 17.jpg: WRONG: volume 28.5 L, the photo says 2.85 L
    ('EREP_10008', '06300003', 380746, '2026-08-10 09:12:00+07:00', '0c3dd483f9651356544b22901e0f2d2420e12b9c85878b423dd4e18085327bfd'),  -- call A, 21.jpeg: WRONG: date 01-10-2026, the photo says 10/01/2026 (day and month swapped)
    ('EREP_10009', '06300004', 15000, '2026-08-10 09:12:00+07:00', '8abd2a9d019f31a2a5d97a63080e40caa1e6b2b97260c1e0889633c06fae65a7'),  -- call A, 2.jpg: correct
    ('EREP_10053', '06300004', 100000, '2026-08-10 09:12:00+07:00', '8224ab5c10377e59457c81ab973ffb7e0bb665e0009f04b905d0ff99d04fb1d7'),  -- call A, 4.jpg: correct
    ('EREP_10054', '06300004', 150000, '2026-08-10 09:12:00+07:00', '448fd455c01031e6913c1817acf527b9c55bbf9a0ad581806bfd891bfdf6dd6a'),  -- call A, 8.jpeg: correct
    ('EREP_10010', '06300006', 664180, '2026-08-10 09:12:00+07:00', 'b301f53f7205fbed4b2de211dd8d058329b61c6e66620e2ea83f2afa08aae3fc'),  -- call A, 29.jpg: WRONG: amount 664,180, the photo says 646,180 (also in grand_total)
    ('EREP_10011', '06300006', 519303, '2026-08-10 09:12:00+07:00', '86100e598e43c83c9af589ae799d33a7fc3267887089c5c4bbfb62c44a1df416'),  -- call A, 32.jpeg: correct
    ('EREP_10012', '06300006', 410168, '2026-08-10 09:12:00+07:00', '01961d9a890cda68cf9e7433d2b4106bfd5208c6792d5fa25c8a7654305cc309'),  -- call A, 39.png: WRONG: product Performa > 92, the photo says Pertamax (RON 92)
    ('EREP_10013', '06300003', 1769560, '2026-08-24 14:40:00+07:00', '027030c3af5c8aee8a1aaa06d434354af9e8f6a77f36d69870243ce469d9cef4'),  -- call B, 60.jpg: correct
    ('EREP_10014', '06300002', 2550000, '2026-08-24 14:40:00+07:00', '902b2c2aa178ab2a01b9af31876789c193370a76056b49b2a45e2ff7afb77ba2'),  -- call B, 57.jpeg: correct
    ('EREP_10015', '06300005', 400119, '2026-08-24 14:40:00+07:00', '78e79514bff9a789eec1be8952f7752e02f3522ac87e0eee1479ae308c7b1fe0'),  -- call B, 5.jpeg: correct
    ('EREP_10016', '06300005', 450060, '2026-08-24 14:40:00+07:00', 'fa77c2d155ee6193545a8aaeed2726277bcac79fd95d7659bf6e8d415aa299f7'),  -- call B, 6.jpg: correct
    ('EREP_10017', '06300004', 250000, '2026-08-24 14:40:00+07:00', 'dd197a92cb2b9fa09d040b7d476d945c2064214e121c74e15c2c938b6b83f9a8'),  -- call B, 10.jpg: correct
    ('EREP_10018', '06300002', 489157, '2026-08-24 14:40:00+07:00', '156a8e953eb46f2f2fc1a05dd1ca6b1a47a05343039c88d102792ce3c92ac9f9'),  -- call B, 18.jpeg: WRONG: volume typed 10 times too large
    ('EREP_10019', '06300001', 750000, '2026-08-24 14:40:00+07:00', '18d4acf1b88a493a63ab4c6023cc477e71152a6889987ee24d01fb1283f792ce'),  -- call B, 26.jpeg: correct
    ('EREP_10020', '06300005', 800000, '2026-08-24 14:40:00+07:00', '70b04a81e71668fff14a0efb8fb95b7298f295f243fb890c517b4ee32292f41c'),  -- call B, 64.jpeg: WRONG: the 2nd receipt on the photo (20-01-2026, Rp 200,000) is missing
    ('EREP_10073', '06300006', 35000, '2026-09-07 10:05:00+07:00', 'eac2eb21812a594d84c533f08338eeb932d815b58a5b04ea12a2499de7bf11a2'),  -- call C, 17.jpg: EREP_10007 submitted again, volume corrected
    ('EREP_10074', '06300005', 1000000, '2026-09-07 10:05:00+07:00', '7d5a1c8488382d7c333b9b5af35c7aa5a5d9899a8948347fde8f7bc8782f93d2'),  -- call C, 64.jpeg: EREP_10020 submitted again, the missing receipt added (the OCR of EREP_10020 found it)
    ('EREP_10021', '06300006', 200000, '2026-09-07 10:05:00+07:00', 'a99dab8453e4db0993414250b4a0bc9e9f5b5de34eb6de4803f723bffbc4299c'),  -- call C, 28.jpeg: correct
    ('EREP_10022', '06300003', 500000, '2026-09-07 10:05:00+07:00', '964670c3e828de7416990920402a6b5256115ed6ef59425935bf569e11fbc824'),  -- call C, 24.jpeg: correct
    ('EREP_10023', '06300002', 686468, '2026-09-07 10:05:00+07:00', '36e6287e50d66396c2abf79eab1b1b8eb10faed5c9dda55c9cc37eadefd0b08e'),  -- call C, 51.jpg: correct
    ('EREP_10055', '06300002', 441555, '2026-09-07 10:05:00+07:00', '30bff0315818ef9caf584561f92b06ef887c0c31dd36b16e18ffa81402c45c68'),  -- call C, 52.jpg: correct
    ('EREP_10024', '06300004', 660000, '2026-09-07 10:05:00+07:00', '5b625beb2582a1a4f6eddfa42cfeca9c9d55eec0680a1e696f9141f848cf879c'),  -- call C, 62.jpg: WRONG: amount of the 4th receipt 10,000, the photo says 100,000
    ('EREP_10025', '06300005', 300000, '2026-09-07 10:05:00+07:00', 'c4f18a9d2fd7184ea57fb87a768ca58f0380df8957b71f7a60dbbb6d7e13ea1e'),  -- call C, 13.jpg: correct
    ('EREP_10075', '06300006', 410168, '2026-09-21 11:20:00+07:00', 'bae18a064b323a5fcdc53ebd08733932dec06fa5e849947557436f77cf7343a1'),  -- call D, 39.png: EREP_10012 submitted again, product corrected
    ('EREP_10076', '06300002', 489157, '2026-09-21 11:20:00+07:00', 'e0f3d90a48c970d23e900eeb42d18c27db608a432e0bf4e572bb5fe3e0d2ffd0'),  -- call D, 18.jpeg: WRONG: EREP_10018 submitted again, volume corrected, but the date is now 23-06-2026; the photo says 2026-05-23
    ('EREP_10026', '06300005', 430080, '2026-09-21 11:20:00+07:00', '90a834a02a01d9e76aa02f26c3b9c2025b9fdf7a53ca9fe0a5d2ce029b124aa6'),  -- call D, 22.jpg: correct
    ('EREP_10027', '06300005', 500000, '2026-09-21 11:20:00+07:00', 'e2022970fb8fce0c9a2dae849ee7a3a91fc3e1e91bdb92ba8e1460c8f6d5fe95'),  -- call D, 23.jpeg: correct
    ('EREP_10028', '06300006', 200000, '2026-09-21 11:20:00+07:00', 'ce71dbf68a5a2eff7f4c061c1e16c788668513ec0953235133a50e3094b42624'),  -- call D, 31.jpeg: correct
    ('EREP_10029', '06300002', 450000, '2026-09-21 11:20:00+07:00', 'ac59b014d265bccf2f0cff10496c5c720c7a7abcde886c4320576bfa0cbaff87'),  -- call D, 40.jpg: correct
    ('EREP_10030', '06300003', 430000, '2026-09-21 11:20:00+07:00', '2a90ec08c30d832c0a713fcb46f0ed55d0d57e643c79f0da151c85398627dda6'),  -- call D, 34.jpg: correct
    ('EREP_10031', '06300006', 402230, '2026-09-21 11:20:00+07:00', 'b57d637ef762d632f2fee78a07b658006b19f20c3a435054a1ebb34db57d6da6'),  -- call D, 45.jpg: correct
    ('EREP_10032', '06300005', 661066, '2026-09-21 11:20:00+07:00', '0e94380ab670572937cf8b69cee63e4dd4fb26cde7e01fdac1f21030b1c1ef20'),  -- call D, 27.jpeg: WRONG: an extra item (30-03-2026, Rp 250,000) that is not on the photo
    ('EREP_10056', '06300005', 815590, '2026-09-21 11:20:00+07:00', '090f78ebbea099712204362b99b632e735f0a8935a4cd6e00493cc3909a5a5aa'),  -- call D, 30.jpg: correct
    ('EREP_10033', '06300003', 1005789, '2026-09-21 11:20:00+07:00', 'e2954742b46ce70b5d8fc92e40a2a2a858a5d039b9a6b0c9ff865b87839345d7'),  -- call D, 59.jpg: correct
    ('EREP_10034', '06300004', 20630, '2026-09-21 11:20:00+07:00', '3babc8946f7c81cfe0604d9e71990bbbdce8a191e8cecb0e53c1bf6641e3f92c'),  -- call D, 12.jpg: correct
    ('EREP_10057', '06300004', 40000, '2026-09-21 11:20:00+07:00', '58e46263c7598d70b74039cad327a3b72b42c0fad741393ab03b98a819711d2d'),  -- call D, 19.jpeg: correct
    ('EREP_10058', '06300004', 40000, '2026-09-21 11:20:00+07:00', '5b16fd777a6d6871bb094b964ada95878eb651ceff605084276f80e88abb64cf'),  -- call D, 20.jpg: correct
    ('EREP_10077', '06300006', 646180, '2026-10-05 09:45:00+07:00', 'ed6da7333214898d91dd8122ef7e3ef782549d25ac9da5ff28543442b4c4a788'),  -- call E, 29.jpg: EREP_10010 submitted again, amount corrected
    ('EREP_10035', '06300006', 863100, '2026-10-05 09:45:00+07:00', '592ff9096b06f6fddae6d971d5e52c05120d1e6644413455a74ca01ae91e9ab0'),  -- call E, 58.jpg: correct
    ('EREP_10036', '06300002', 370000, '2026-10-05 09:45:00+07:00', 'a570a5121557319852312683e81e410acb836cde7429824098057552e14f5f57'),  -- call E, 46.jpeg: correct
    ('EREP_10037', '06300005', 400000, '2026-10-05 09:45:00+07:00', 'f4bf7be42fb455eadba2309a4fde63b354ca7fdb4de09aef953b3edfe91ca68e'),  -- call E, 33.jpeg: correct
    ('EREP_10038', '06300005', 438750, '2026-10-05 09:45:00+07:00', 'fbdeda79bfecc6d6f2629118fdd1c02ff181b4509f9c670908d38f8cb3c2aafc'),  -- call E, 35.jpg: WRONG: date 17-07-2025, the photo says 17/07/2026
    ('EREP_10039', '06300003', 650000, '2026-10-05 09:45:00+07:00', '085652fd5e14e20cb2f99a6208b541c428582853d51084fb524347b3520bb2ef'),  -- call E, 47.jpg: correct
    ('EREP_10040', '06300005', 400000, '2026-10-05 09:45:00+07:00', '846b984024abee1fb4eeb291f4b84b90662c0b11384c27c4e166dac95da627f7'),  -- call E, 38.jpg: correct
    ('EREP_10041', '06300006', 399380, '2026-10-05 09:45:00+07:00', '5b8820c5a8baa42b6885ed9b0cd8601aa3efd489813c767b7886a5c522402022'),  -- call E, 49.jpg: correct
    ('EREP_10059', '06300006', 231120, '2026-10-05 09:45:00+07:00', '0cbce958cbd13ea3620ba8308b6f017bcd3d589c96ec1f4d2bbe330e3c3bd7e8'),  -- call E, 50.jpg: correct
    ('EREP_10042', '06300002', 349546, '2026-10-05 09:45:00+07:00', '989ec7ca4b733c86cc2624949ac9728548b67dbcf724d549acd93607bb11631a'),  -- call E, 55.jpeg: correct
    ('EREP_10078', '06300002', 489157, '2026-10-12 13:30:00+07:00', '814f639b95d0292ed4748984f2124054958140b2f9e9b3290b15b0b8fea6d27f'),  -- call F, 18.jpeg: EREP_10076 submitted again, date corrected
    ('EREP_10079', '06300004', 750000, '2026-10-12 13:30:00+07:00', '161f4076a6c1cc2a8778a1309a9d1869dc190ceb073a8793fc272fc15a2d9300'),  -- call F, 62.jpg: EREP_10024 submitted again, amount corrected
    ('EREP_10043', '06300005', 200000, '2026-10-12 13:30:00+07:00', 'a84c045b5e6237698f4626e3adf6e24105c3074482b9aa3e2dbeb8c5920aadb0'),  -- call F, 41.jpeg: correct
    ('EREP_10060', '06300005', 400000, '2026-10-12 13:30:00+07:00', '3a4ced20ccceb9b40655e35c6a0f11d4bd44b6c768a124fbb1c69e22e166e2fc'),  -- call F, 42.jpeg: correct
    ('EREP_10044', '06300005', 400000, '2026-10-12 13:30:00+07:00', '7ec0eb16dbef05ecb43d5488e0e49ee4fef7f6ac674a9586ff0dca07eea8695d'),  -- call F, 43.jpg: correct
    ('EREP_10061', '06300005', 382500, '2026-10-12 13:30:00+07:00', '75600188e25dc09aad310fa346216ea3247b33f7fd2d50a2b2739a4d0fb7762f'),  -- call F, 44.jpg: correct
    ('EREP_10045', '06300006', 858652, '2026-10-12 13:30:00+07:00', 'cb00575498b1444f946e2f66eec58b30ddf67ca341011ac8e7524740ab99dc0f'),  -- call F, 53.jpeg: correct
    ('EREP_10046', '06300006', 404166, '2026-10-12 13:30:00+07:00', '564d17bbc0e17cbd6d598b1fff0ec478efa9583c5530a748a1e096df748a8437'),  -- call F, 54.jpeg: WRONG: amount 440,166, the photo says 404,166 (the grand total is right)
    ('EREP_10047', '06300003', 722020, '2026-10-12 13:30:00+07:00', '6f88122ac325c51753d800e342467f78efc9e56efaf9babde253cabc9cdb4141'),  -- call F, 48.png: correct
    ('EREP_10048', '06300002', 537774, '2026-10-12 13:30:00+07:00', '70f4048b58101e2876801184796d4b74ea7f5b2981bddb99787da85b2ad97965'),  -- call F, 61.png: correct
    ('EREP_10049', '06300004', 50000, '2026-10-12 13:30:00+07:00', '1b3b8e4da9a9295af7c9b25177ae0e4a6862bb302870fbed7fc438539bf210b5'),  -- call F, 25.jpeg: correct
    ('EREP_10062', '06300004', 20000, '2026-10-12 13:30:00+07:00', '98a24d2ceab9307744d294e82909bdf57a661ec86dde2ced6623001df629dec8'),  -- call F, 37.jpg: correct
    ('EREP_10080', '06300005', 411066, '2026-10-18 10:10:00+07:00', 'b3fc00d903c5f17959a9022e9df4e409eb7eb5e4f5555ec8fa038dbf4edee33e'),  -- call G, 27.jpeg: EREP_10032 submitted again, extra item removed
    ('EREP_10050', '06300006', 646180, '2026-10-18 10:10:00+07:00', '47f0d8307735312d3361187875554312037e0f38e57def1efd600792b261a12f'),  -- call G, 63.jpg: correct
    ('EREP_10051', '06300003', 522773, '2026-10-18 10:10:00+07:00', 'f5bb7f4273cdf8084838f12e83f3a266250cb3f3b10a71be4aaaafc073f402aa'),  -- call G, 56.jpeg: correct
    ('EREP_10052', '06300002', 700000, '2026-10-18 10:10:00+07:00', '2e7ca3c7e2ef1cf1cff779efa32304d74e74f8180a0ce9ea93f4e3e5321a076e'),  -- call G, 7.jpg: correct
    ('EREP_10063', '06300002', 500000, '2026-10-18 10:10:00+07:00', '49cec82fa385421f9af0cb1ad19a20f177f42ddb0c7c1eb1dc1e5045538d07ec'),  -- call G, 9.jpeg: correct
    ('EREP_10064', '06300004', 265000, '2026-10-19 14:15:00+07:00', 'd339a4434a65daa8c370aaf83cbf356c898a98b11b31c96f87f2f3bcc9152d65'),  -- call H, receipts_2_4_8.pdf (3 pages: 2.jpg, 4.jpg, 8.jpeg): correct
    ('EREP_10065', '06300002', 1128023, '2026-10-19 14:15:00+07:00', '71cbe641d1aa9d6e08634d7b22bef605063ac32f82e23bd237b0d634eee9ff29'),  -- call H, receipts_51_52.pdf (2 pages: 51.jpg, 52.jpg): correct
    ('EREP_10066', '06300006', 630500, '2026-10-19 14:15:00+07:00', 'b9350015ca66cdfd06ea60fcf3f4aeac35d8a1a11e5896fbafe5d5c127b3c574'),  -- call H, receipts_49_50.pdf (2 pages: 49.jpg, 50.jpg): correct
    ('EREP_10067', '06300005', 782500, '2026-10-19 14:15:00+07:00', '294f54308f01410a97c7a3eaba7638227629760ee1f8c78cd1f501ad7497e0f5'),  -- call H, 43.jpg and 44.jpg (a photo per item): correct
    ('EREP_10068', '06300005', 1000000, '2026-10-19 14:15:00+07:00', '70c5eaf2b03384c8087f0facf4993c2f400471168c149f0c02c16e448fff5671'),  -- call H, receipts_64.pdf (1 page: 64.jpeg, three receipts on it): correct
    ('EREP_10081', '06300006', 540000, '2026-10-20 08:30:00+07:00', '3be3968353d4304d3814f41cf13363e88c159c64350025d54a02b0970615f3f1'),  -- call I, 14.jpeg: WRONG: the receipt of EREP_10004 (approved) claimed again, with the amount 540,000; the photo says 450,000
    ('EREP_10082', '06300001', 549549, '2026-10-20 08:30:00+07:00', 'e540740324055e69789540faa6fe0c00ddbc0978fa31ecf3568181bbe1bae8d2');  -- call I, 16.jpg: the receipt of EREP_10006 (approved by the OCR) claimed again, with the kilometer corrected (48,942 -> 48,492)

-- The receipt files: the dummy folder's files, served at /api/dummy-receipts/<name> by the local backend and kept in
-- the folder itself.
CREATE TEMP TABLE seed_file (
    name          varchar(255) PRIMARY KEY,
    sha256        varchar(64)  NOT NULL,
    content_type  varchar(100) NOT NULL
) ON COMMIT DROP;

INSERT INTO seed_file (name, sha256, content_type) VALUES
    ('1.jpeg', 'c1a06e2d577ca4cd8bfefd4fa25e701b335d158987f60a8af76be8b3fe01754d', 'image/jpeg'),
    ('3.jpg', '0d74621b8c2870bc2f07d8222ef392ffbf40d2e8aae897e6346309f1e0196c2f', 'image/jpeg'),
    ('11.jpeg', 'd6bbdcbf215291ac6e8098339cd80ddb15fcdb954dda6cda4dbaa29b8de43034', 'image/jpeg'),
    ('14.jpeg', '5eb3717fd55829a6bacf476b33950801293d64615d80ec44560ba8ea7889959c', 'image/jpeg'),
    ('15.jpeg', 'a7892e22122c614d69f7502c37d5af36f6ad947cbcfd5ece27e152ec7dc78a23', 'image/jpeg'),
    ('16.jpg', '1300c6baaedb408ed50bfbc4aa158d913977a0f2c575ed3d4bd99264205a4878', 'image/jpeg'),
    ('17.jpg', '4025b44a80ef3b95bb0c324041e7047bd05d8c12425d9ddfb6196d0b8c996db5', 'image/jpeg'),
    ('21.jpeg', '986c60800685939b4d0cc8b464e269e5265786eb9e63a9256b2257b0136eccef', 'image/jpeg'),
    ('2.jpg', '04186bd04455ff102e0f4f2a94597a485172597b5c523cceb7e8df2f70696de7', 'image/jpeg'),
    ('4.jpg', '3a9cfa1cfd7c0403ea33a860b4327f29b70d4302f904ae838fa0371e41905ebd', 'image/jpeg'),
    ('8.jpeg', '6c098629353bb8cf3a81d12ef41b9bfbf84ce2ffc57e9a28d904badaf3ab3c79', 'image/jpeg'),
    ('29.jpg', 'f8a03d4b70ab5d1c044b9ffb97aab23746540fb10e612d335bd0a5fbceafb034', 'image/jpeg'),
    ('32.jpeg', 'bea00b88c16386d322ebc626d2784e8fd21b4b96d29c9e64181520a6fa59f596', 'image/jpeg'),
    ('39.png', '35550986f78b72b9af65abea5aba13c84544290105d01ce010fd2a23e009a5f5', 'image/png'),
    ('60.jpg', 'f505342335cd064f77995506444d92a7499d806ab0d70e30cfe5b5536e246305', 'image/jpeg'),
    ('57.jpeg', '89668ab5f76c0157d85d82418ee9e27aeea6c0ada78edbc7a33fdf43d5e16c45', 'image/jpeg'),
    ('5.jpeg', '27e983fd0556a4a341dfdd0e81b5d179f13b1a1aeaf5ce9350f493cd9fdf385f', 'image/jpeg'),
    ('6.jpg', 'eeb99e17a72e39ed64a1e80ce9e2edc3fd37a47ea6b44e7b1de322471f65bbc2', 'image/jpeg'),
    ('10.jpg', '6311d81d75975d08e658340c4940c5889fff692e2e68c2be4fba60df14e4c122', 'image/jpeg'),
    ('18.jpeg', 'e127c1750afd4a8349965d8e3170d61b8215a6848402024786e2c24f455bd439', 'image/jpeg'),
    ('26.jpeg', '66937f14456eb31e6ccb93edb398fafe1611cb865f12f73409a5d40cc9654894', 'image/jpeg'),
    ('64.jpeg', 'b01617410c0100436aaa9394d0ea067bb0cd342bbfdebd678bd76cec98641b82', 'image/jpeg'),
    ('28.jpeg', 'e03503b78314fbaf153929bf5b5060b38b20b633ed556988dc901b9d5a71ee1b', 'image/jpeg'),
    ('24.jpeg', '313e769bc03ea9827fb8b1530a53250e1380bc3dd3db752162057bb8ed417f4d', 'image/jpeg'),
    ('51.jpg', '267188c4372e4532fb1e05aaf235693142b3ad0eb0ae37a50ba62f4dfb0be7ce', 'image/jpeg'),
    ('52.jpg', 'e2ea4ad845a0b6cdf6a8433e5cd11d2746e7a9ba7bf73a404ee696eed74e0c62', 'image/jpeg'),
    ('62.jpg', 'f8901c6bd71b2aa667310ea86147d42cf1a53ea7a35e70ef54f78b08fc1c3321', 'image/jpeg'),
    ('13.jpg', 'd6a128d36dc8cf339684bc4f952e4a061439b2873f852115e336850a48d2af6e', 'image/jpeg'),
    ('22.jpg', '016324d6b7625785eae53f4d5089a046006f6b9b86b613ca6696a23f39ad6f30', 'image/jpeg'),
    ('23.jpeg', '9838b874caf2c147e5f501be75941200956af9d9f8f78c9f03fd026499a575d5', 'image/jpeg'),
    ('31.jpeg', 'e1f6a09237a58fee45e2d24a5ea84c099cf252e7af4a860cf1f9b360025ccf03', 'image/jpeg'),
    ('40.jpg', 'b62f59be73afa72cf409509c28d5bab8a568b716014fa1b211b24e70361b1e5e', 'image/jpeg'),
    ('34.jpg', 'b9a08f1bf01a48970f83d981ceb2af7422868d349c40c629c5acb01130197f06', 'image/jpeg'),
    ('45.jpg', 'c174623f27160decc59373f2c4babd956fb9737406631f250302600f9377d2e9', 'image/jpeg'),
    ('27.jpeg', 'e6caf40cebaee92bb638363be0d067c467e8abc8291a0f33971d7f7c3936d030', 'image/jpeg'),
    ('30.jpg', '5e9f37f92cb1414e4b3de2fc2e0d1b7da4a54024f4a603d65d3fa2a47c91d007', 'image/jpeg'),
    ('59.jpg', 'b4b34faae93d65b6ee15c841618d829ebf2d1a250c9b4a96a838d2c8e990446f', 'image/jpeg'),
    ('12.jpg', 'd67cfdbc86ed4c91e44ba538384d961faf844e43efc7b11016f414e121075430', 'image/jpeg'),
    ('19.jpeg', 'e5c8c2a2aae5d89625a7e2dc868857a5c0b2ed0290f470275c949fd871e0999d', 'image/jpeg'),
    ('20.jpg', 'd2c30227ea5a644d75f533244197080897c1b7292a551338f08a2640c1799d9c', 'image/jpeg'),
    ('58.jpg', 'e13a4d6d8c834e54a6f514ab19a6f31f11134f36a4d4a626a8a1e474cb2ffe28', 'image/jpeg'),
    ('46.jpeg', '6f75290310dae4de4a36ee09a5f7c31600a73ccf42a0a9bf30c0c97c3b5bf390', 'image/jpeg'),
    ('33.jpeg', 'e17ffe78e53060cd8674606eb18cd422889eb9cb1e8cc9f74dc925930e77619e', 'image/jpeg'),
    ('35.jpg', 'fe9a6b4644d34b3bf492833c855fe1a06f9c4a599efc2b38e3a7ef2516fcfd2c', 'image/jpeg'),
    ('47.jpg', '34223efb5bddbb7b500be46ab433bbe69d31427c37a68d9cceb13695b8559fb7', 'image/jpeg'),
    ('38.jpg', '09d087abba7465c92a3ddfe7484e0b5ec467699749174eb6c7bc4214d12d242a', 'image/jpeg'),
    ('49.jpg', 'eafa72ebee77114853825cdb60ac950bced3b5a206623dd4e2d5df132589067d', 'image/jpeg'),
    ('50.jpg', 'dade8bff75e58419209b103b2e5752e601ed6bdf7a942453b9cd3f2cca5f335b', 'image/jpeg'),
    ('55.jpeg', 'd89be318313d0edd6efb3809661beadd3cac17e9fc7b3c3911be787970b66588', 'image/jpeg'),
    ('41.jpeg', 'c8ee2bebd105ae7985eb1da7aae45b3bf4aca7383df58b057c0357c6e84a6a8e', 'image/jpeg'),
    ('42.jpeg', '8f19914938f0bab8516caeb52d910249cb9814ce51f626237cf760a26aec4aa5', 'image/jpeg'),
    ('43.jpg', '1e59cd0c52f8b55bde745a66d1b26c4067e50b0db199681df42633c9114b3eec', 'image/jpeg'),
    ('44.jpg', '0ca73b05a085e3abfe511f426080a3448811abca54f64e079136dc4adad0a5ea', 'image/jpeg'),
    ('53.jpeg', '89f93e67484648a307eae8f5ab216f6710b06be14be683f63025601675966cf7', 'image/jpeg'),
    ('54.jpeg', '172f51e26b3648ea7af9a17cea0da5b3a49487425fea5c9331199b679acb7da2', 'image/jpeg'),
    ('48.png', 'f1c0f77c7cbb7a62eeefa0c536fbcdf5990f5808ec3d87f1c0eee41b06cc7a26', 'image/png'),
    ('61.png', '0c609a6e2b7ae4d7152b111c25b64e9bbb38b75d8001778be7c6de8d7c3f2ed4', 'image/png'),
    ('25.jpeg', '7bfd314bad09a96f1ac4c56f41a5b585130a755c6f6af5041b050c5857a66cc2', 'image/jpeg'),
    ('37.jpg', '18ed0b5590ee13b72119b22e55bd24766843f5bc5d44e9727221e03cc36f8892', 'image/jpeg'),
    ('63.jpg', '3d9555a2e8f0a4116df168375d7ba19201e6916da6e371ec815eeed3f6238cc2', 'image/jpeg'),
    ('56.jpeg', '61e5c09c4ab8138bc3230caa0e3efefcac063cea6aff7935ed01c3d870b8f730', 'image/jpeg'),
    ('7.jpg', '4b45fc4542ad2478a53365c747744a01c00aefb2c66927e1942673feae464ac3', 'image/jpeg'),
    ('9.jpeg', '50e70009c3fbdc2616978b243e16ba6e25a4d250646b0fd468393383413531e5', 'image/jpeg'),
    ('receipts_2_4_8.pdf', '5f58b67c88fe977d6c6fb307ebb402d190d544309d5d8492afd7beddad2a1e24', 'application/pdf'),
    ('receipts_51_52.pdf', '77807b8dadc284ac310e0f52e39957cf4b20d210f1d021393e570295f214038a', 'application/pdf'),
    ('receipts_49_50.pdf', 'd7205ebf78d2d38d9cd7decf8dd04003808d3a75075024430a4c1b7231c46d74', 'application/pdf'),
    ('receipts_64.pdf', 'e0a1bd5556b70c49ca3c6d3d45686838b5f23c83de2d7d772805050e815ad7e3', 'application/pdf');

-- The items, each with the name of the file attached to it.
CREATE TEMP TABLE seed_item (
    reimbursement_code  varchar(50)   NOT NULL,
    item_id             varchar(50)   NOT NULL,
    product_name        varchar(255)  NOT NULL,
    date_of_expense     date          NOT NULL,
    volume_liter        numeric(10,3) NOT NULL,
    kilometer           integer,
    total_price         numeric(14,2) NOT NULL,
    file_name           varchar(255)  NOT NULL
) ON COMMIT DROP;

INSERT INTO seed_item (reimbursement_code, item_id, product_name, date_of_expense, volume_liter, kilometer, total_price,
                       file_name) VALUES
    ('EREP_10001', 'EXP_10001', 'Diesel/Dex', '2026-05-26', 48.68, 49532, 1358170, '1.jpeg'),
    ('EREP_10002', 'EXP_10002', 'BP 92', '2026-01-20', 31.578, 22026, 394725, '3.jpg'),
    ('EREP_10003', 'EXP_10003', 'Pertalite 90', '2026-04-06', 25.32, 19202, 407348, '11.jpeg'),
    ('EREP_10004', 'EXP_10004', 'Pertamax 92', '2025-12-18', 35.29, 15250, 450000, '14.jpeg'),
    ('EREP_10005', 'EXP_10005', 'Vivo Ron 92', '2025-12-02', 29.46, 33942, 382980, '15.jpeg'),
    ('EREP_10006', 'EXP_10006', 'Diesel/Dex', '2026-01-08', 39.65, 48942, 549549, '16.jpg'),
    ('EREP_10007', 'EXP_10007', 'Pertamax 92', '2026-05-29', 28.5, 20111, 35000, '17.jpg'),
    ('EREP_10008', 'EXP_10008', 'Shell Super 92', '2026-10-01', 29.98, 37903, 380746, '21.jpeg'),
    ('EREP_10009', 'EXP_10009', 'Pertamax 92', '2026-05-02', 1.22, 10994, 15000, '2.jpg'),
    ('EREP_10010', 'EXP_10010', 'Performa > 92', '2026-02-04', 50.88, 16088, 664180, '29.jpg'),
    ('EREP_10011', 'EXP_10011', 'Shell Super 92', '2026-01-23', 40.89, 15631, 519303, '32.jpeg'),
    ('EREP_10012', 'EXP_10012', 'Performa > 92', '2026-02-26', 34.76, 17182, 410168, '39.png'),
    ('EREP_10013', 'EXP_10013', 'Pertamax 92', '2025-12-07', 50.98, 34307, 650000, '60.jpg'),
    ('EREP_10013', 'EXP_10014', 'Shell Super 92', '2025-12-12', 30.58, 35893, 397540, '60.jpg'),
    ('EREP_10013', 'EXP_10015', 'Shell Super 92', '2025-12-29', 55.54, 36652, 722020, '60.jpg'),
    ('EREP_10014', 'EXP_10016', 'BP 92', '2026-04-07', 32.285, 23095, 400000, '57.jpeg'),
    ('EREP_10014', 'EXP_10017', 'BP 92', '2026-04-10', 36.32, 23495, 450000, '57.jpeg'),
    ('EREP_10014', 'EXP_10018', 'BP 92', '2026-04-15', 36.32, 24367, 450000, '57.jpeg'),
    ('EREP_10014', 'EXP_10019', 'BP 92', '2026-04-20', 36.32, 24850, 450000, '57.jpeg'),
    ('EREP_10014', 'EXP_10020', 'BP 92', '2026-04-24', 28.25, 25328, 350000, '57.jpeg'),
    ('EREP_10014', 'EXP_10021', 'BP 92', '2026-04-28', 36.32, 26301, 450000, '57.jpeg'),
    ('EREP_10015', 'EXP_10022', 'Pertamax 92', '2026-06-09', 32.53, 62047, 400119, '5.jpeg'),
    ('EREP_10016', 'EXP_10023', 'Pertamax 92', '2026-03-27', 36.59, 61228, 450060, '6.jpg'),
    ('EREP_10017', 'EXP_10024', 'Pertamax 92', '2026-04-19', 20.32, 10739, 250000, '10.jpg'),
    ('EREP_10018', 'EXP_10025', 'BP 92', '2026-05-23', 394.8, 27138, 489157, '18.jpeg'),
    ('EREP_10019', 'EXP_10026', 'Diesel/Dex', '2026-01-07', 55.147, 48157, 750000, '26.jpeg'),
    ('EREP_10020', 'EXP_10027', 'Pertamax 92', '2026-01-06', 32.38, 58258, 400000, '64.jpeg'),
    ('EREP_10020', 'EXP_10029', 'Pertamax 92', '2026-01-27', 32.389, 59526, 400000, '64.jpeg'),
    ('EREP_10021', 'EXP_10030', 'Performa > 92', '2026-06-27', 11.765, 20181, 200000, '28.jpeg'),
    ('EREP_10022', 'EXP_10031', 'Vivo Ron 92', '2025-12-08', 38.46, 35480, 500000, '24.jpeg'),
    ('EREP_10023', 'EXP_10032', 'BP 92', '2026-04-27', 55.405, 25685, 686468, '51.jpg'),
    ('EREP_10024', 'EXP_10033', 'Pertamax 92', '2026-02-02', 12, 9797, 150000, '62.jpg'),
    ('EREP_10024', 'EXP_10034', 'Pertamax 92', '2026-02-09', 12, 9964, 150000, '62.jpg'),
    ('EREP_10024', 'EXP_10035', 'Pertamax 92', '2026-02-16', 12, 10174, 150000, '62.jpg'),
    ('EREP_10024', 'EXP_10036', 'Pertamax 92', '2026-02-23', 8, 10370, 10000, '62.jpg'),
    ('EREP_10024', 'EXP_10037', 'Pertamax 92', '2026-02-25', 16, 10513, 200000, '62.jpg'),
    ('EREP_10025', 'EXP_10038', 'Pertamax 92', '2026-07-30', 18.46, 63082, 300000, '13.jpg'),
    ('EREP_10026', 'EXP_10039', 'Pertamax 92', '2026-01-27', 34.824, 59940, 430080, '22.jpg'),
    ('EREP_10027', 'EXP_10040', 'Pertamax 92', '2025-12-01', 39.21, 57366, 500000, '23.jpeg'),
    ('EREP_10028', 'EXP_10041', 'Pertalite 90', '2026-02-26', 20, 17585, 200000, '31.jpeg'),
    ('EREP_10029', 'EXP_10042', 'BP 92', '2026-05-08', 36.32, 26731, 450000, '40.jpg'),
    ('EREP_10030', 'EXP_10043', 'Shell Super 92', '2025-12-17', 33.07, 36284, 430000, '34.jpg'),
    ('EREP_10031', 'EXP_10044', 'Performa > 92', '2026-08-07', 21.98, 20327, 402230, '45.jpg'),
    ('EREP_10032', 'EXP_10045', 'Pertamax 92', '2026-03-29', 33.42, 61661, 411066, '27.jpeg'),
    ('EREP_10032', 'EXP_10046', 'Pertamax 92', '2026-03-30', 20.243, 61873, 250000, '27.jpeg'),
    ('EREP_10033', 'EXP_10047', 'BP 92', '2026-02-02', 23.698, 38292, 285561, '59.jpg'),
    ('EREP_10033', 'EXP_10048', 'Vivo Ron 92', '2026-02-13', 19.77, 38567, 238228, '59.jpg'),
    ('EREP_10033', 'EXP_10049', 'Vivo Ron 92', '2026-02-25', 40, 38823, 482000, '59.jpg'),
    ('EREP_10034', 'EXP_10050', 'Pertamax 92', '2026-05-29', 1.64, 11300, 20630, '12.jpg'),
    ('EREP_10035', 'EXP_10051', 'Pertalite 90', '2026-03-01', 35.02, 17801, 350200, '58.jpg'),
    ('EREP_10035', 'EXP_10052', 'Pertalite 90', '2026-03-10', 32.79, 18186, 342623, '58.jpg'),
    ('EREP_10035', 'EXP_10053', 'Pertalite 90', '2026-03-18', 18.5, 18968, 185000, '58.jpg'),
    ('EREP_10036', 'EXP_10054', 'BP 92', '2026-03-12', 29.865, 22771, 370000, '46.jpeg'),
    ('EREP_10037', 'EXP_10055', 'Pertamax 92', '2026-01-06', 32.38, 58687, 400000, '33.jpeg'),
    ('EREP_10038', 'EXP_10056', 'Pertamax 92', '2025-07-17', 27, 62749, 438750, '35.jpg'),
    ('EREP_10039', 'EXP_10057', 'Pertamax 92', '2025-12-07', 50.98, 34879, 650000, '47.jpg'),
    ('EREP_10040', 'EXP_10058', 'Pertamax 92', '2026-02-18', 33.89, 60856, 400000, '38.jpg'),
    ('EREP_10041', 'EXP_10059', 'Pertamax 92', '2026-03-10', 32.47, 18590, 399380, '49.jpg'),
    ('EREP_10042', 'EXP_10060', 'BP 92', '2026-02-23', 30.008, 22438, 361596, '55.jpeg'),
    ('EREP_10043', 'EXP_10061', 'Pertamax 92', '2026-01-20', 16.19, 59298, 200000, '41.jpeg'),
    ('EREP_10044', 'EXP_10062', 'Pertamax 92', '2026-07-09', 24.61, 62451, 400000, '43.jpg'),
    ('EREP_10045', 'EXP_10063', 'Pertamax 92', '2026-08-14', 53.834, 20589, 858652, '53.jpeg'),
    ('EREP_10046', 'EXP_10064', 'Pertamax 92', '2026-05-03', 32.859, 19724, 440166, '54.jpeg'),
    ('EREP_10047', 'EXP_10065', 'Shell Super 92', '2025-12-29', 55.54, 37264, 722020, '48.png'),
    ('EREP_10048', 'EXP_10066', 'BP 92', '2026-10-04', 33.34, 28068, 537774, '61.png'),
    ('EREP_10049', 'EXP_10067', 'Pertamax 92', '2026-07-22', 3, 11517, 50000, '25.jpeg'),
    ('EREP_10050', 'EXP_10068', 'Performa > 92', '2026-02-04', 50.88, 16646, 646180, '63.jpg'),
    ('EREP_10051', 'EXP_10069', 'Vivo Ron 92', '2026-08-21', 32.41, 39267, 522773, '56.jpeg'),
    ('EREP_10052', 'EXP_10070', 'BP 92', '2026-07-08', 41.992, 27571, 700000, '7.jpg'),
    ('EREP_10053', 'EXP_10071', 'Pertamax 92', '2026-06-28', 6.15, 11416, 100000, '4.jpg'),
    ('EREP_10054', 'EXP_10072', 'Pertamax 92', '2026-05-13', 12.195, 11139, 150000, '8.jpeg'),
    ('EREP_10055', 'EXP_10073', 'BP 92', '2026-04-12', 35.638, 23943, 441555, '52.jpg'),
    ('EREP_10056', 'EXP_10074', 'Pertamax 92', '2026-08-02', 51.13, 63311, 815590, '30.jpg'),
    ('EREP_10057', 'EXP_10075', 'Pertamax 92', '2026-06-03', 3.18, 11345, 40000, '19.jpeg'),
    ('EREP_10058', 'EXP_10076', 'Pertamax 92', '2026-05-08', 3.18, 11079, 40000, '20.jpg'),
    ('EREP_10059', 'EXP_10077', 'Pertamax 92', '2026-04-20', 18.79, 19500, 231120, '50.jpg'),
    ('EREP_10060', 'EXP_10078', 'Pertamax 92', '2026-01-27', 32.389, 60418, 400000, '42.jpeg'),
    ('EREP_10061', 'EXP_10079', 'Pertamax 92', '2025-12-05', 30, 57863, 382500, '44.jpg'),
    ('EREP_10062', 'EXP_10080', 'Pertalite 90', '2026-05-05', 2, 11042, 20000, '37.jpg'),
    ('EREP_10063', 'EXP_10081', 'BP 92', '2025-12-02', 38.462, 21520, 500000, '9.jpeg'),
    ('EREP_10064', 'EXP_10082', 'Pertamax 92', '2026-05-02', 1.22, 10994, 15000, 'receipts_2_4_8.pdf'),
    ('EREP_10064', 'EXP_10083', 'Pertamax 92', '2026-06-28', 6.15, 11416, 100000, 'receipts_2_4_8.pdf'),
    ('EREP_10064', 'EXP_10084', 'Pertamax 92', '2026-05-13', 12.195, 11139, 150000, 'receipts_2_4_8.pdf'),
    ('EREP_10065', 'EXP_10085', 'BP 92', '2026-04-27', 55.405, 25685, 686468, 'receipts_51_52.pdf'),
    ('EREP_10065', 'EXP_10086', 'BP 92', '2026-04-12', 35.638, 23943, 441555, 'receipts_51_52.pdf'),
    ('EREP_10066', 'EXP_10087', 'Pertamax 92', '2026-03-10', 32.47, 18590, 399380, 'receipts_49_50.pdf'),
    ('EREP_10066', 'EXP_10088', 'Pertamax 92', '2026-04-20', 18.79, 19500, 231120, 'receipts_49_50.pdf'),
    ('EREP_10067', 'EXP_10089', 'Pertamax 92', '2026-07-09', 24.61, 62451, 400000, '43.jpg'),
    ('EREP_10067', 'EXP_10090', 'Pertamax 92', '2025-12-05', 30, 57863, 382500, '44.jpg'),
    ('EREP_10068', 'EXP_10091', 'Pertamax 92', '2026-01-06', 32.38, 58258, 400000, 'receipts_64.pdf'),
    ('EREP_10068', 'EXP_10092', 'Pertamax 92', '2026-01-20', 16.19, 59086, 200000, 'receipts_64.pdf'),
    ('EREP_10068', 'EXP_10093', 'Pertamax 92', '2026-01-27', 32.389, 59526, 400000, 'receipts_64.pdf'),
    ('EREP_10073', 'EXP_10098', 'Pertamax 92', '2026-05-29', 2.85, 20111, 35000, '17.jpg'),
    ('EREP_10074', 'EXP_10099', 'Pertamax 92', '2026-01-06', 32.38, 58258, 400000, '64.jpeg'),
    ('EREP_10074', 'EXP_10100', 'Pertamax 92', '2026-01-20', 16.19, 59086, 200000, '64.jpeg'),
    ('EREP_10074', 'EXP_10101', 'Pertamax 92', '2026-01-27', 32.389, 59526, 400000, '64.jpeg'),
    ('EREP_10075', 'EXP_10102', 'Pertamax 92', '2026-02-26', 34.76, 17182, 410168, '39.png'),
    ('EREP_10076', 'EXP_10103', 'BP 92', '2026-06-23', 39.48, 27138, 489157, '18.jpeg'),
    ('EREP_10077', 'EXP_10104', 'Performa > 92', '2026-02-04', 50.88, 16088, 646180, '29.jpg'),
    ('EREP_10078', 'EXP_10105', 'BP 92', '2026-05-23', 39.48, 27138, 489157, '18.jpeg'),
    ('EREP_10079', 'EXP_10106', 'Pertamax 92', '2026-02-02', 12, 9797, 150000, '62.jpg'),
    ('EREP_10079', 'EXP_10107', 'Pertamax 92', '2026-02-09', 12, 9964, 150000, '62.jpg'),
    ('EREP_10079', 'EXP_10108', 'Pertamax 92', '2026-02-16', 12, 10174, 150000, '62.jpg'),
    ('EREP_10079', 'EXP_10109', 'Pertamax 92', '2026-02-23', 8, 10370, 100000, '62.jpg'),
    ('EREP_10079', 'EXP_10110', 'Pertamax 92', '2026-02-25', 16, 10513, 200000, '62.jpg'),
    ('EREP_10080', 'EXP_10111', 'Pertamax 92', '2026-03-29', 33.42, 61661, 411066, '27.jpeg'),
    ('EREP_10081', 'EXP_10112', 'Pertamax 92', '2025-12-18', 35.29, 15250, 540000, '14.jpeg'),
    ('EREP_10082', 'EXP_10113', 'Diesel/Dex', '2026-01-08', 39.65, 48492, 549549, '16.jpg');

INSERT INTO bbm_receipt (reimbursement_code, item_id, product_name, date_of_expense, volume_liter, kilometer, total_price)
SELECT s.reimbursement_code, s.item_id, s.product_name, s.date_of_expense, s.volume_liter, s.kilometer, s.total_price
FROM seed_item s
JOIN reimbursement_report r USING (reimbursement_code)
ORDER BY r.received_at, s.reimbursement_code, length(s.item_id), s.item_id;  -- EXP_9999 before EXP_10000

INSERT INTO attachment (bbm_receipt_id, name, url, sha256, storage_path, content_type)
SELECT i.id, f.name, 'http://127.0.0.1:5000/api/dummy-receipts/' || f.name, f.sha256,
       'local:backend/database/dummy_bbm_receipt/' || f.name, f.content_type
FROM seed_item s
JOIN bbm_receipt i USING (reimbursement_code, item_id)
JOIN seed_file f ON f.name = s.file_name
ORDER BY i.id;

COMMIT;

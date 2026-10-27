-- Dummy decisions: the reviewers approving and rejecting some of the dummy reports (run after dummy_comment.sql).
-- Each was made after the OCR read the report, as a reviewer would.
-- Matched and proceed reports need no decision: every report is compared on its own.
-- The story: EREP_10010 and EREP_10024 were rejected, and the OCR approved the report submitted again (EREP_10077,
-- EREP_10079); EREP_10018 was rejected, and so was its report submitted again (EREP_10076) before the third one
-- (EREP_10078) matched; EREP_10012 was rejected and its report submitted again (EREP_10075) waits for a reviewer (the
-- OCR misread its volume, so the receipt's numbers don't back the amount); EREP_10007 was rejected and its report
-- submitted again (EREP_10073) approved by a reviewer, as the OCR couldn't read its date; EREP_10020 (a receipt
-- missing) and EREP_10032 (an item not on the photo) were rejected, and their reports submitted again matched
-- (EREP_10074) or wait for the OCR (EREP_10080); EREP_10050 claims the receipt of EREP_10010 again; EREP_10029 was
-- reopened once.
-- EREP_10004 (approved by a reviewer) and EREP_10006 (approved by the OCR) had their receipts claimed again (call I):
-- EREP_10081 raises the amount and waits for a reviewer, EREP_10082 only corrects the kilometer and matches.
-- Running it again replaces the decisions on the dummy employees' reports.
BEGIN;

DELETE FROM review_decision d
USING reimbursement_report p
WHERE p.reimbursement_code = d.reimbursement_code
  AND p.employee_no IN ('06300001', '06300002', '06300003', '06300004', '06300005', '06300006');

INSERT INTO review_decision (reimbursement_code, decision, reason, user_email, decided_at) VALUES
    ('EREP_10004', 'approved', NULL, 'reviewer1@example.com', '2026-08-11 09:06:00+07:00'),
    ('EREP_10007', 'rejected', 'Volume sent as 28,5 L; the receipt says 2,85 L (Rp 35.000 at Rp 12.300 per liter). Submit it again with the right volume.', 'reviewer2@example.com', '2026-08-11 09:21:00+07:00'),
    ('EREP_10010', 'rejected', 'Total sent as Rp 664.180; the receipt says Rp 646.180.', 'reviewer1@example.com', '2026-08-11 09:40:00+07:00'),
    ('EREP_10008', 'rejected', 'Date sent as 01-10-2026; the receipt says 10/01/2026 (day and month swapped).', 'reviewer2@example.com', '2026-08-11 10:06:00+07:00'),
    ('EREP_10012', 'rejected', 'Fuel type sent as Performa > 92; the receipt says Pertamax (RON 92).', 'reviewer2@example.com', '2026-08-11 10:15:00+07:00'),
    ('EREP_10020', 'rejected', 'The photo shows three receipts; the one of 20-01-2026 (Rp 200.000) is missing. Submit it again with all three.', 'reviewer1@example.com', '2026-08-25 09:10:00+07:00'),
    ('EREP_10024', 'rejected', 'Total sent as Rp 10.000; the receipt says Rp 100.000.', 'reviewer2@example.com', '2026-09-08 08:35:00+07:00'),
    ('EREP_10073', 'approved', NULL, 'reviewer2@example.com', '2026-09-08 08:41:00+07:00'),
    ('EREP_10018', 'rejected', 'Volume sent as 394,8 L; the receipt says 39,48 L.', 'reviewer1@example.com', '2026-09-08 09:00:00+07:00'),
    ('EREP_10029', 'approved', NULL, 'reviewer1@example.com', '2026-09-22 08:10:00+07:00'),
    ('EREP_10029', 'reopened', NULL, 'reviewer2@example.com', '2026-09-22 08:12:00+07:00'),
    ('EREP_10029', 'approved', NULL, 'reviewer2@example.com', '2026-09-22 08:16:00+07:00'),
    ('EREP_10076', 'rejected', 'Date sent as 23-06-2026; the receipt says 2026-05-23.', 'reviewer1@example.com', '2026-09-22 08:30:00+07:00'),
    ('EREP_10032', 'rejected', 'The item of 30-03-2026 (Rp 250.000) is not on the photo. Submit it again without it.', 'reviewer1@example.com', '2026-09-22 08:45:00+07:00'),
    ('EREP_10050', 'rejected', 'Double claim: the same receipt as EREP_10010 (29.jpg), Pertamax Turbo, 04-02-2026, Rp 646.180.', 'reviewer1@example.com', '2026-10-18 11:01:00+07:00');

COMMIT;

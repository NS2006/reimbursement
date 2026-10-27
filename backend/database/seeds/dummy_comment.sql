-- Dummy comments: the reviewers discussing some of the dummy reports (run after dummy_bbm_ocr.sql).
-- Written after the OCR read each report, as a reviewer would; one was edited later.
-- Running it again replaces the comments on the dummy employees' reports.
BEGIN;

DELETE FROM comment c
USING reimbursement_report p
WHERE p.reimbursement_code = c.reimbursement_code
  AND p.employee_no IN ('06300001', '06300002', '06300003', '06300004', '06300005', '06300006');

INSERT INTO comment (reimbursement_code, user_email, description, created_at, edited_at) VALUES
    ('EREP_10004', 'reviewer1@example.com', 'The OCR read the pump number into the product name ("PERTAMAX Hose 10.3"). The photo says Pertamax, as submitted. OK to approve.', '2026-08-11 09:05:00+07:00', NULL),
    ('EREP_10007', 'reviewer2@example.com', 'Volume is 28.5 L but the receipt says 2.85 L (Rp 35.000 at Rp 12.300 per liter). Asked the employee to submit it again.', '2026-08-11 09:20:00+07:00', NULL),
    ('EREP_10008', 'reviewer1@example.com', 'Date sent as 01-10-2026, the receipt says 10/01/2026: day and month swapped.', '2026-08-11 09:31:00+07:00', NULL),
    ('EREP_10008', 'reviewer2@example.com', 'Agreed. Rejecting it, so the employee submits it again with the right date.', '2026-08-11 10:02:00+07:00', '2026-08-11 10:05:00+07:00'),
    ('EREP_10073', 'reviewer2@example.com', 'EREP_10007 submitted again with the right volume. The OCR could not read the date this time; the photo shows 29/05/2026, as submitted.', '2026-09-08 08:40:00+07:00', NULL),
    ('EREP_10029', 'reviewer2@example.com', 'The OCR read the date as 2026-06-08; the photo says 2026-05-08, as submitted. OK.', '2026-09-22 08:15:00+07:00', NULL),
    ('EREP_10038', 'reviewer1@example.com', 'The year should be 2026: the receipt is dated 17/07/2026.', '2026-10-06 08:30:00+07:00', NULL),
    ('EREP_10046', 'reviewer2@example.com', 'Amount typed as Rp 440.166, the receipt says Rp 404.166. The grand total is right.', '2026-10-13 09:10:00+07:00', NULL),
    ('EREP_10050', 'reviewer1@example.com', 'This is the same receipt as EREP_10010 (29.jpg): Pertamax Turbo, 04-02-2026, Rp 646.180. Possible double claim.', '2026-10-18 11:00:00+07:00', NULL);

COMMIT;

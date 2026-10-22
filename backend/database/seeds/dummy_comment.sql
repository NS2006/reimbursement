-- Dummy comments: the reviewers discussing some of the dummy reports (run after dummy_bbm_ocr.sql).
-- Written after the OCR read each report, as a reviewer would; one was edited later.
-- Running it again replaces the comments on the dummy employees' reports.
BEGIN;

DELETE FROM comment c
USING reimbursement_report p
WHERE p.reimbursement_code = c.reimbursement_code
  AND p.employee_no IN ('EMP-001', 'EMP-002', 'EMP-003', 'EMP-004', 'EMP-005', 'EMP-006');

INSERT INTO comment (reimbursement_code, user_email, description, created_at, edited_at) VALUES
    ('RB-004', 'reviewer1@example.com', 'The OCR read the pump number into the product name ("PERTAMAX Hose 10.3"). The photo says Pertamax, as submitted. OK to approve.', '2026-08-11 09:05:00+07:00', NULL),
    ('RB-007', 'reviewer2@example.com', 'Volume is 28.5 L but the receipt says 2.85 L (Rp 35.000 at Rp 12.300 per liter). Asked the employee to send it again.', '2026-08-11 09:20:00+07:00', NULL),
    ('RB-007', 'reviewer2@example.com', 'Revision 2 has the right volume. The OCR could not read the date this time; the photo shows 29/05/2026, as submitted.', '2026-09-08 08:40:00+07:00', NULL),
    ('RB-008', 'reviewer1@example.com', 'Date sent as 01-10-2026, the receipt says 10/01/2026: day and month swapped.', '2026-08-11 09:31:00+07:00', NULL),
    ('RB-008', 'reviewer2@example.com', 'Agreed. Waiting for a corrected revision before approving.', '2026-08-11 10:02:00+07:00', '2026-08-11 10:05:00+07:00'),
    ('RB-011', 'reviewer1@example.com', 'The receipt shows Rp 12.700 per liter, which fits the total (40,89 L). Rp 17.200 is a typo.', '2026-08-11 09:47:00+07:00', NULL),
    ('RB-029', 'reviewer2@example.com', 'The OCR read the date as 2026-06-08; the photo says 2026-05-08, as submitted. OK.', '2026-09-22 08:15:00+07:00', NULL),
    ('RB-038', 'reviewer1@example.com', 'The year should be 2026: the receipt is dated 17/07/2026.', '2026-10-06 08:30:00+07:00', NULL),
    ('RB-046', 'reviewer2@example.com', 'Amount typed as Rp 440.166, the receipt says Rp 404.166. The grand total is right.', '2026-10-13 09:10:00+07:00', NULL),
    ('RB-050', 'reviewer1@example.com', 'This is the same receipt as RB-010 (29.jpg): Pertamax Turbo, 04-02-2026, Rp 646.180. Possible double claim.', '2026-10-18 11:00:00+07:00', NULL);

COMMIT;

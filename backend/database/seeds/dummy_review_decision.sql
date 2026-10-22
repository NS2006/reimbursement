-- Dummy decisions: the reviewers approving and rejecting some of the dummy reports (run after dummy_comment.sql).
-- Each is on one revision (code, revision_no) and was made after the OCR read it, as a reviewer would.
-- Matched and proceed revisions need no decision, also after a rejection: every revision is compared on its own.
-- The story: RB-010, RB-018 and RB-024 were rejected, and the OCR approved the revision sent again (RB-018's after a
-- second rejection); RB-012 was rejected and its revision sent again waits for a reviewer (the OCR misread its volume,
-- so the receipt's numbers don't back the amount); RB-007 was rejected and its new revision approved by a reviewer, as
-- the OCR couldn't read its date; RB-050 claims the receipt of RB-010 again; RB-029 was reopened once.
-- RB-004 (approved by a reviewer) and RB-006 (approved by the OCR) were sent again after the approval (call I): RB-004
-- revision 2 raises the amount and waits for a reviewer, RB-006 revision 2 only corrects the kilometer and matches.
-- Running it again replaces the decisions on the dummy employees' reports.
BEGIN;

DELETE FROM review_decision d
USING reimbursement_revision r, reimbursement_report p
WHERE r.id = d.revision_id
  AND p.reimbursement_code = r.reimbursement_code
  AND p.employee_no IN ('EMP-001', 'EMP-002', 'EMP-003', 'EMP-004', 'EMP-005', 'EMP-006');

INSERT INTO review_decision (revision_id, decision, reason, user_email, decided_at)
SELECT r.id, v.decision, v.reason, v.user_email, CAST(v.decided_at AS timestamptz)
FROM (VALUES
    ('RB-004', 1, 'approved', NULL, 'reviewer1@example.com', '2026-08-11 09:06:00+07:00'),
    ('RB-007', 1, 'rejected', 'Volume sent as 28,5 L; the receipt says 2,85 L (Rp 35.000 at Rp 12.300 per liter). Send it again with the right volume.', 'reviewer2@example.com', '2026-08-11 09:21:00+07:00'),
    ('RB-010', 1, 'rejected', 'Total sent as Rp 664.180; the receipt says Rp 646.180.', 'reviewer1@example.com', '2026-08-11 09:40:00+07:00'),
    ('RB-008', 1, 'rejected', 'Date sent as 01-10-2026; the receipt says 10/01/2026 (day and month swapped).', 'reviewer2@example.com', '2026-08-11 10:06:00+07:00'),
    ('RB-012', 1, 'rejected', 'Product sent as Pertamax Turbo; the receipt says Pertamax.', 'reviewer2@example.com', '2026-08-11 10:15:00+07:00'),
    ('RB-024', 1, 'rejected', 'Total sent as Rp 10.000; the receipt says Rp 100.000.', 'reviewer2@example.com', '2026-09-08 08:35:00+07:00'),
    ('RB-007', 2, 'approved', NULL, 'reviewer2@example.com', '2026-09-08 08:41:00+07:00'),
    ('RB-018', 1, 'rejected', 'Volume sent as 394,8 L; the receipt says 39,48 L.', 'reviewer1@example.com', '2026-09-08 09:00:00+07:00'),
    ('RB-029', 1, 'approved', NULL, 'reviewer1@example.com', '2026-09-22 08:10:00+07:00'),
    ('RB-029', 1, 'reopened', NULL, 'reviewer2@example.com', '2026-09-22 08:12:00+07:00'),
    ('RB-029', 1, 'approved', NULL, 'reviewer2@example.com', '2026-09-22 08:16:00+07:00'),
    ('RB-018', 2, 'rejected', 'Date sent as 23-06-2026; the receipt says 2026-05-23.', 'reviewer1@example.com', '2026-09-22 08:30:00+07:00'),
    ('RB-050', 1, 'rejected', 'Double claim: the same receipt as RB-010 (29.jpg), Pertamax Turbo, 04-02-2026, Rp 646.180.', 'reviewer1@example.com', '2026-10-18 11:01:00+07:00')
) AS v (code, revision_no, decision, reason, user_email, decided_at)
JOIN reimbursement_revision r ON r.reimbursement_code = v.code AND r.revision_no = v.revision_no
ORDER BY CAST(v.decided_at AS timestamptz);

COMMIT;

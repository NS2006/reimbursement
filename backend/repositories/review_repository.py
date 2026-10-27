from backend.database.connection import fetch_all, get_connection

COLUMNS = "d.id, d.decision, d.reason, d.user_email, u.name AS user_name, d.decided_at"


def add(code, decision, reason, user_email, based_on):
    """Add a reviewer's decision to a report. Returns (outcome, detail):

        ("added", the new decision)
        ("not_found", None)              no report with that code
        ("changed", newest or None)      the newest decision is not the one the reviewer saw (based_on)
        ("nothing_to_reopen", None)      reopened, but no decision is in force
        ("unchanged", the decision)      that decision is already in force

    The report row is locked while deciding, so two reviewers deciding at once are handled one after the other."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        try:
            outcome = _add(conn, code, decision, reason, user_email, based_on)
        except Exception:
            conn.run("ROLLBACK")
            raise
        conn.run("COMMIT" if outcome[0] == "added" else "ROLLBACK")
    return outcome


def _add(conn, code, decision, reason, user_email, based_on):
    if not conn.run("SELECT 1 FROM reimbursement_report WHERE reimbursement_code = :code FOR UPDATE", code=code):
        return "not_found", None

    found = fetch_all(
        conn,
        f"SELECT {COLUMNS} FROM review_decision d JOIN app_user u ON u.email = d.user_email "
        "WHERE d.reimbursement_code = :code ORDER BY d.decided_at DESC, d.id DESC LIMIT 1",
        code=code,
    )
    newest = found[0] if found else None
    if (newest["id"] if newest else None) != based_on:
        return "changed", newest
    in_force = newest if newest and newest["decision"] != "reopened" else None
    if decision == "reopened" and in_force is None:
        return "nothing_to_reopen", None
    if in_force and in_force["decision"] == decision:
        return "unchanged", in_force

    [added] = fetch_all(
        conn,
        "WITH d AS ("
        "    INSERT INTO review_decision (reimbursement_code, decision, reason, user_email)"
        "    VALUES (:code, :decision, :reason, :user_email)"
        "    RETURNING *"
        f") SELECT {COLUMNS} FROM d JOIN app_user u ON u.email = d.user_email",
        code=code,
        decision=decision,
        reason=reason,
        user_email=user_email,
    )
    return "added", added

from backend.database.connection import fetch_all, get_connection

COLUMNS = "c.id, c.user_email, u.name AS user_name, c.description, c.created_at, c.edited_at"


def find_by_report(code):
    """The reviewers' comments on a report, oldest first."""
    with get_connection() as conn:
        return fetch_all(
            conn,
            f"SELECT {COLUMNS} FROM comment c JOIN app_user u ON u.email = c.user_email "
            "WHERE c.reimbursement_code = :code ORDER BY c.created_at, c.id",
            code=code,
        )


def find_on_report(code, comment_id):
    """One comment of a report ({id, user_email}), or None when the report has no such comment."""
    with get_connection() as conn:
        rows = fetch_all(
            conn,
            "SELECT id, user_email FROM comment WHERE id = :id AND reimbursement_code = :code",
            id=comment_id,
            code=code,
        )
    return rows[0] if rows else None


def add(code, user_email, description):
    """Add a comment to a report and return it, or None when the report does not exist."""
    with get_connection() as conn:
        rows = fetch_all(
            conn,
            "WITH c AS ("
            "    INSERT INTO comment (reimbursement_code, user_email, description)"
            "    SELECT CAST(:code AS varchar), :user_email, :description"  # cast: :code is used twice
            "    WHERE EXISTS (SELECT 1 FROM reimbursement_report WHERE reimbursement_code = :code)"
            "    RETURNING id, user_email, description, created_at, edited_at"
            f") SELECT {COLUMNS} FROM c JOIN app_user u ON u.email = c.user_email",
            code=code,
            user_email=user_email,
            description=description,
        )
    return rows[0] if rows else None


def update(comment_id, description):
    """Change the text of a comment and return it, or None when it no longer exists.

    edited_at is only set when the text really changes, so saving the same text does not mark it as edited.
    """
    with get_connection() as conn:
        rows = fetch_all(
            conn,
            "WITH c AS ("
            "    UPDATE comment"
            "    SET edited_at = CASE WHEN description = CAST(:description AS text) THEN edited_at ELSE now() END,"
            "        description = CAST(:description AS text)"  # cast: :description is used twice
            "    WHERE id = :id"
            "    RETURNING id, user_email, description, created_at, edited_at"
            f") SELECT {COLUMNS} FROM c JOIN app_user u ON u.email = c.user_email",
            id=comment_id,
            description=description,
        )
    return rows[0] if rows else None


def delete(comment_id):
    """Delete a comment. Returns False when it was already gone."""
    with get_connection() as conn:
        rows = conn.run("DELETE FROM comment WHERE id = :id RETURNING id", id=comment_id)
    return bool(rows)

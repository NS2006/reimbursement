from backend.database.connection import fetch_all, get_connection


def find(attachment_id):
    """One attachment ({id, name, storage_path, content_type}), or None when there is no such attachment."""
    with get_connection() as conn:
        rows = fetch_all(
            conn,
            "SELECT id, name, storage_path, content_type FROM attachment WHERE id = :id",
            id=attachment_id,
        )
    return rows[0] if rows else None

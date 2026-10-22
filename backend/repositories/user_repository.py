from backend.database.connection import get_connection


def find_all() -> list[dict]:
    with get_connection() as conn:
        rows = conn.run("SELECT email, name FROM app_user ORDER BY name, email")
    return [{"email": email, "name": name} for email, name in rows]


def find_by_email(email: str) -> dict | None:
    with get_connection() as conn:
        rows = conn.run("SELECT email, name FROM app_user WHERE email = :email", email=email)
    if not rows:
        return None
    email, name = rows[0]
    return {"email": email, "name": name}

import os
from contextlib import contextmanager

import pg8000.native

# The longest a query may run, in milliseconds. PostgreSQL cancels it after that, so a query nobody waits for any more
# stops using the database. Below the 10 s the connection waits for an answer, so the server stops it first.
STATEMENT_TIMEOUT_MS = 9000


def _setting(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to the .env file in the repo root.")
    return value


@contextmanager
def get_connection():
    """Open a PostgreSQL connection for one unit of work and always close it afterwards."""
    conn = pg8000.native.Connection(
        user=_setting("DB_USER"),
        password=_setting("DB_PASSWORD"),
        host=_setting("DB_HOST", "localhost"),
        port=int(_setting("DB_PORT", "5432")),
        database=_setting("DB_NAME"),
        timeout=10,
        startup_params={"options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"},
    )
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(conn, sql: str, **params) -> list[dict]:
    """Run a query and return its rows as dicts keyed by column name."""
    rows = conn.run(sql, **params)
    names = [column["name"] for column in conn.columns or []]
    return [dict(zip(names, row)) for row in rows]

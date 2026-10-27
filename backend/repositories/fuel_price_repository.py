import json
from pathlib import Path

from backend.database.connection import fetch_all, get_connection

# The fuels a database without any starts with (add_products_if_none): the same file backend.database.reset seeds.
PRODUCTS_SEED = Path(__file__).resolve().parents[1] / "database" / "seeds" / "fuel_product.sql"

# The active products, in the merchants' order: gasoline by RON, then diesel.
PRODUCTS_SQL = """
    SELECT p.id, p.merchant, p.name, p.fuel_kind, p.ron
    FROM fuel_product p
    WHERE p.active
    ORDER BY array_position(ARRAY['pertamina', 'shell', 'bp', 'vivo']::varchar[], p.merchant),
             p.fuel_kind = 'diesel', p.ron NULLS LAST, p.id
"""

# Every price of the active products, the newest valid_from first (also the ones announced for a later day).
PRICES_SQL = """
    SELECT f.id, f.fuel_product_id, f.price_per_liter, f.valid_from, f.source, f.source_url, f.source_text,
           f.fetched_at, f.fuel_price_run_id
    FROM fuel_price f
    JOIN fuel_product p ON p.id = f.fuel_product_id AND p.active
    ORDER BY f.fuel_product_id, f.valid_from DESC
"""

RUN_COLUMNS = """
    r.id, r.trigger, r.requested_by, u.name AS requested_by_name, r.status, r.requested_at, r.started_at,
    r.finished_at, r.error, r.prices_found, r.prices_stored, r.rejected_prices
"""

LAST_RUN_SQL = f"""
    SELECT {RUN_COLUMNS}
    FROM fuel_price_run r
    LEFT JOIN app_user u ON u.email = r.requested_by
    ORDER BY r.id DESC
    LIMIT 1
"""

# Queueing a refresh is one at a time (a transaction-level advisory lock), so two clicks at once can't both pass the
# cooldown check; the unique index on the queued or running run is the last guard.
QUEUE_LOCK = 72_014

# A queued run no worker took in this long, or a run still running after this long (its worker stopped without
# saying so), fails: otherwise it would block every new refresh.
NOT_STARTED_MINUTES = 120
STALE_MINUTES = 40


def find_overview() -> dict:
    """What the fuel price page shows, read in one connection: products, prices (every price of them, newest
    valid_from first per product) and last_run (the newest refresh from the web, or None)."""
    with get_connection() as conn:
        products = fetch_all(conn, PRODUCTS_SQL)
        prices = fetch_all(conn, PRICES_SQL)
        runs = fetch_all(conn, LAST_RUN_SQL)
    return {"products": products, "prices": prices, "last_run": runs[0] if runs else None}


# ---------------------------------------------------------------------------
# Queueing a refresh (the button, a new batch of reports)
# ---------------------------------------------------------------------------

def queue_button_run(email, cooldown_minutes):
    """Queue a refresh someone asked for on the website. Returns (outcome, run):

        ("queued", the new run)
        ("active", that run)       one is queued or running
        ("too_soon", the newest)   the newest was asked for less than cooldown_minutes ago (however it started)"""
    return _queue("button", email, cooldown_minutes)


def queue_batch_run(cooldown_minutes):
    """Queue the refresh of a new batch of reports, with the button's cooldown: one refresh per cooldown, whichever
    asked for it. Returns (outcome, run) as queue_button_run."""
    return _queue("batch", None, cooldown_minutes)


def _queue(trigger, email, cooldown_minutes):
    """Queue a run unless one is active or the newest was asked for less than cooldown_minutes ago; see
    queue_button_run."""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        try:
            conn.run("SELECT pg_advisory_xact_lock(:key)", key=QUEUE_LOCK)
            _fail_stale(conn)
            active = _newest_run(conn, "WHERE r.status IN ('queued', 'running')")
            newest = active or _newest_run(conn)
            too_soon = newest is not None and newest["requested_minutes_ago"] < cooldown_minutes
            reason = "active" if active else "too_soon" if too_soon else None
            if reason:
                conn.run("ROLLBACK")
                return reason, newest
            [[run_id]] = conn.run(
                "INSERT INTO fuel_price_run (trigger, requested_by) VALUES (:trigger, :email) RETURNING id",
                trigger=trigger, email=email,
            )
            run = _newest_run(conn, "WHERE r.id = :id", id=run_id)
            conn.run("COMMIT")
        except Exception:
            conn.run("ROLLBACK")
            raise
    return "queued", run


def _newest_run(conn, where="", **params):
    """The newest run matching where (with how many minutes ago it was asked for), or None."""
    rows = fetch_all(
        conn,
        f"""
        SELECT {RUN_COLUMNS}, EXTRACT(EPOCH FROM now() - r.requested_at) / 60 AS requested_minutes_ago
        FROM fuel_price_run r
        LEFT JOIN app_user u ON u.email = r.requested_by
        {where}
        ORDER BY r.id DESC
        LIMIT 1
        """,
        **params,
    )
    return rows[0] if rows else None


def _fail_stale(conn):
    """Fail the run no worker took in NOT_STARTED_MINUTES (not_started), or that is running for over STALE_MINUTES
    (stale)."""
    conn.run(
        "UPDATE fuel_price_run SET status = 'failed', finished_at = now(), started_at = COALESCE(started_at, now()), "
        "    error = CASE status WHEN 'queued' THEN 'not_started' ELSE 'stale' END "
        "WHERE (status = 'queued' AND requested_at < now() - make_interval(mins => CAST(:queued AS integer))) "
        "   OR (status = 'running' AND started_at < now() - make_interval(mins => CAST(:running AS integer)))",
        queued=NOT_STARTED_MINUTES, running=STALE_MINUTES,
    )


# ---------------------------------------------------------------------------
# The refresh itself (backend/jobs/fuel_price/worker.py)
# ---------------------------------------------------------------------------

def claim_run():
    """Fail stale runs, then take the queued run, if any: it becomes running. Returns {id, trigger, requested_at} or
    None. Two workers never take the same run (SKIP LOCKED)."""
    with get_connection() as conn:
        _fail_stale(conn)
        rows = fetch_all(
            conn,
            """
            UPDATE fuel_price_run SET status = 'running', started_at = now()
            WHERE id = (SELECT id FROM fuel_price_run WHERE status = 'queued' ORDER BY id LIMIT 1
                        FOR UPDATE SKIP LOCKED)
            RETURNING id, trigger, requested_at
            """,
        )
    return rows[0] if rows else None


def release_run(run_id):
    """Put a running run back in the queue (its worker was stopped)."""
    with get_connection() as conn:
        conn.run("UPDATE fuel_price_run SET status = 'queued', started_at = NULL WHERE id = :id AND status = 'running'",
                 id=run_id)


def add_products_if_none():
    """Insert the fuels (PRODUCTS_SEED) when fuel_product has no row at all, as on a first deploy. Returns how many
    were inserted: 0 when there are products, active or not (one the merchants stopped selling isn't brought back).
    Two workers at once insert them once (the file's ON CONFLICT)."""
    with get_connection() as conn:
        if conn.run("SELECT 1 FROM fuel_product LIMIT 1"):
            return 0
        conn.run("START TRANSACTION")
        try:
            conn.run(PRODUCTS_SEED.read_text(encoding="utf-8"))
            [[count]] = conn.run("SELECT count(*) FROM fuel_product")
            conn.run("COMMIT")
        except Exception:
            conn.run("ROLLBACK")
            raise
    return count


def find_for_refresh():
    """What a found price is checked against (and a report's items are priced with: fuel_price_service.add_item_prices):
    the active products, and every price of them (newest valid_from first per product)."""
    with get_connection() as conn:
        products = fetch_all(conn, PRODUCTS_SQL)
        prices = fetch_all(
            conn,
            """
            SELECT f.fuel_product_id, f.valid_from, f.price_per_liter, f.source
            FROM fuel_price f JOIN fuel_product p ON p.id = f.fuel_product_id AND p.active
            ORDER BY f.fuel_product_id, f.valid_from DESC
            """,
        )
    return products, prices


def finish_run(run_id, prices, found, rejected, usage):
    """Store the prices that passed the checks and close the run (done), in one transaction. A price never replaces
    one entered by hand, and a news price never replaces an official one, also when it was added during the run.
    Returns how many prices were stored, or None when the run is not running any more (failed as stale meanwhile).

    prices: [{fuel_product_id, valid_from, price_per_liter, source, source_url, source_text}]
    rejected: [{merchant, product, price_per_liter, source_url, reason}]
    usage: {cached_input_tokens, uncached_input_tokens, output_tokens, reasoning_tokens, web_searches}"""
    with get_connection() as conn:
        conn.run("START TRANSACTION")
        try:
            if not conn.run("SELECT 1 FROM fuel_price_run WHERE id = :id AND status = 'running' FOR UPDATE",
                            id=run_id):
                conn.run("ROLLBACK")
                return None
            stored = 0
            for price in prices:
                stored += len(conn.run(
                    """
                    INSERT INTO fuel_price (fuel_product_id, valid_from, price_per_liter, source, source_url,
                                            source_text, fuel_price_run_id)
                    VALUES (:product_id, :valid_from, CAST(:price AS numeric), :source, :url, :text, :run_id)
                    ON CONFLICT (fuel_product_id, valid_from) DO UPDATE
                        SET price_per_liter = EXCLUDED.price_per_liter, source = EXCLUDED.source,
                            source_url = EXCLUDED.source_url, source_text = EXCLUDED.source_text,
                            fetched_at = now(), fuel_price_run_id = EXCLUDED.fuel_price_run_id
                        WHERE fuel_price.source <> 'manual'
                          AND NOT (fuel_price.source = 'official' AND EXCLUDED.source = 'news')
                          AND fuel_price.price_per_liter IS DISTINCT FROM EXCLUDED.price_per_liter
                    RETURNING id
                    """,
                    product_id=price["fuel_product_id"], valid_from=price["valid_from"],
                    price=None if price["price_per_liter"] is None else str(price["price_per_liter"]),
                    source=price["source"], url=price["source_url"], text=price["source_text"], run_id=run_id,
                ))
            _close(conn, run_id, "done", None, usage,
                   found=found, stored=stored, rejected=json.dumps(rejected, ensure_ascii=False))
            conn.run("COMMIT")
        except Exception:
            conn.run("ROLLBACK")
            raise
    return stored


def fail_run(run_id, error, usage=None):
    """Close the run as failed, with why: a code the website explains (claude_unavailable, timeout, no_answer, ...)."""
    with get_connection() as conn:
        _close(conn, run_id, "failed", error, usage or {})


def _close(conn, run_id, status, error, usage, found=None, stored=None, rejected=None):
    conn.run(
        """
        UPDATE fuel_price_run
        SET status = :status, finished_at = now(), error = :error, prices_found = :found, prices_stored = :stored,
            rejected_prices = CAST(:rejected AS jsonb),
            cached_input_tokens = :cached, uncached_input_tokens = :uncached, output_tokens = :output,
            reasoning_tokens = :reasoning, web_searches = :searches
        WHERE id = :id AND status = 'running'
        """,
        id=run_id, status=status, error=error, found=found, stored=stored, rejected=rejected,
        cached=int(usage.get("cached_input_tokens", 0)), uncached=int(usage.get("uncached_input_tokens", 0)),
        output=int(usage.get("output_tokens", 0)), reasoning=int(usage.get("reasoning_tokens", 0)),
        searches=int(usage.get("web_searches", 0)),
    )

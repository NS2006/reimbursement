"""
Reset your LOCAL database. Run from the repository root:

    py -m backend.database.reset            (asks which option)
    py -m backend.database.reset reseed     (or: rebuild, empty; add --yes to skip the confirmation)

Options:
    reseed   Empty every table, then run every seeder again. The tables stay as they are.
    rebuild  Drop everything, create the tables from schema.sql, then run every seeder.
             Use this after changing schema.sql.
    empty    Empty every table but app_user, without seeding, like a first deploy: the users can still sign in, the
             reports come only from POST /api/reimbursements, and the fuel price worker adds the fuels again (when it
             starts, or before its next refresh) and their prices from "Update from the web".

Needs psql on PATH and the DB_* settings in .env (repository root). Everything in the database is deleted,
so it refuses to run against anything other than localhost.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

DATABASE_DIR = Path(__file__).resolve().parent
SCHEMA = DATABASE_DIR / "schema.sql"

# Seeders run in this order; a seeder can only use rows inserted by the ones before it. Add new seeders here.
SEEDS = [
    DATABASE_DIR / "seeds" / "app_user.sql",
    DATABASE_DIR / "seeds" / "fuel_product.sql",
    DATABASE_DIR / "seeds" / "fuel_price.sql",
    DATABASE_DIR / "seeds" / "dummy_reimbursement.sql",
    DATABASE_DIR / "seeds" / "dummy_bbm_ocr.sql",
    DATABASE_DIR / "seeds" / "dummy_ocr_failure.sql",
    DATABASE_DIR / "seeds" / "dummy_comment.sql",
    DATABASE_DIR / "seeds" / "dummy_review_decision.sql",
    DATABASE_DIR / "seeds" / "dummy_month.sql",
    DATABASE_DIR / "seeds" / "same_receipt.sql",   # last: the reports claiming the same receipt, of every seed
]

MODES = {
    "reseed": "Empty every table, then run every seeder again (the tables stay)",
    "rebuild": "Drop everything, create the tables from schema.sql, then run every seeder",
    "empty": "Empty every table but app_user (the users), without seeding",
}

# Empties every table of schema public but the ones named in {keep} (quoted names, or '' for none).
EMPTY_TABLES = """
DO $$
DECLARE tables text;
BEGIN
    SELECT string_agg(format('%I', tablename), ', ') INTO tables FROM pg_tables
    WHERE schemaname = 'public' AND tablename NOT IN ({keep});
    IF tables IS NOT NULL THEN
        EXECUTE 'TRUNCATE ' || tables || ' RESTART IDENTITY CASCADE';
    END IF;
END $$;
"""
EMPTY_ALL_TABLES = EMPTY_TABLES.format(keep="''")
# comment and review_decision reference app_user's rows and are emptied too. fuel_product is emptied as on a first
# deploy: the fuel price worker inserts the fuels again (fuel_price_repository.add_products_if_none).
EMPTY_ALL_BUT_USERS = EMPTY_TABLES.format(keep="'app_user'")

DROP_EVERYTHING = "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

ROW_COUNTS = """
SELECT table_name AS "table",
       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I', table_name), false, true, '')))[1]::text AS rows
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
"""

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def load_settings():
    load_dotenv(DATABASE_DIR.parent.parent / ".env")
    settings = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "name": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }
    missing = [key for key, value in settings.items() if not value]
    if missing:
        sys.exit(f"Missing in .env: {', '.join('DB_' + key.upper() for key in missing)}")
    if settings["host"] not in LOCAL_HOSTS:
        sys.exit(f"Refusing to reset {settings['host']}: this script only resets a local database.")
    return settings


def psql(settings, *args):
    """Run psql with the .env settings; stop the whole reset on the first error."""
    env = {
        **os.environ,
        "PGPASSWORD": settings["password"],
        "PGOPTIONS": os.environ.get("PGOPTIONS", "") + " -c client_min_messages=warning",  # hide NOTICE lines
    }
    command = [
        "psql", "-h", settings["host"], "-p", settings["port"], "-U", settings["user"], "-d", settings["name"],
        "-q", "-v", "ON_ERROR_STOP=1", *args,
    ]
    try:
        result = subprocess.run(command, env=env)
    except FileNotFoundError:
        sys.exit("psql was not found. Add PostgreSQL's bin folder to PATH.")
    if result.returncode != 0:
        sys.exit(f"Stopped: psql failed (exit code {result.returncode}). Nothing after this step ran.")


def choose_mode(settings):
    print(f'Database "{settings["name"]}" on {settings["host"]}:{settings["port"]}')
    for number, (mode, text) in enumerate(MODES.items(), start=1):
        print(f"  {number}) {mode:<8} {text}")
    answer = input(f"Choose 1 to {len(MODES)} (anything else cancels): ").strip()
    return dict(enumerate(MODES, start=1)).get(int(answer)) if answer.isdigit() else None


def main():
    parser = argparse.ArgumentParser(description="Reset the local database.")
    parser.add_argument("mode", nargs="?", choices=MODES, help="skip the menu")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation")
    args = parser.parse_args()

    settings = load_settings()
    mode = args.mode or choose_mode(settings)
    if mode is None:
        sys.exit("Cancelled.")

    if not args.yes:
        rows = "every row but the users (app_user)" if mode == "empty" else "every row"
        answer = input(f'{mode}: {rows} in "{settings["name"]}" will be deleted. Continue? [y/N] ')
        if answer.strip().lower() != "y":
            sys.exit("Cancelled.")

    if mode == "rebuild":
        print("Dropping everything...")
        psql(settings, "-c", DROP_EVERYTHING)
        print(f"Creating the tables ({SCHEMA.name})...")
        psql(settings, "-f", str(SCHEMA))
    elif mode == "empty":
        print("Emptying every table but app_user...")
        psql(settings, "-c", EMPTY_ALL_BUT_USERS)
    else:
        print("Emptying every table...")
        psql(settings, "-c", EMPTY_ALL_TABLES)

    if mode != "empty":
        for seed in SEEDS:
            print(f"Seeding {seed.name}...")
            psql(settings, "-f", str(seed))

    print("\nDone. Rows per table:")
    psql(settings, "-c", ROW_COUNTS)


if __name__ == "__main__":
    main()
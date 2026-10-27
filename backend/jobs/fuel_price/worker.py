"""
The fuel price job: refreshes the Jakarta fuel prices from the web, one queued refresh (fuel_price_run) at a time. The
website's button and a new batch of reports queue one (services/fuel_price_service.py); the OCR worker runs it before
its next file (backend/jobs/bbm_ocr/worker.py), or run it alone from the repository root:

    py -m backend.jobs.fuel_price.worker            run the queued refreshes, then wait for new ones
    py -m backend.jobs.fuel_price.worker --once     run the queued refresh, if any, then stop

A refresh:

1. The merchants' own price lists (Pertamina's and Shell's, sources.OFFICIAL_LISTS): the job downloads each
   (page_fetch.py) and Claude Haiku reads it like an article (price_search.read_article). No search is needed.
2. The news, for the products the lists didn't settle (price_checks.settled_products: BP's and Vivo's, and a
   merchant's whose list can't be downloaded or read): Claude searches the web for recent articles about their prices
   on the listed sites, the job downloads them, and Claude reads up to MAX_ARTICLES of them. An article the page says
   was published more than DAYS_BACK days ago is skipped before Claude reads it (its prices would be refused anyway).

Claude gives each price with a sentence (or a line of the list) quoted from the page, price_checks.py checks every
price, and the ones that pass are stored with the run (fuel_price_repository.finish_run). The run fails with a code
the website explains: claude_unavailable, timeout, no_answer, over_budget (the search, when no price list was read
either), no_articles (no price list or article could be read) or worker_error; the repository fails a run no worker
took (not_started) or one that stopped (stale).
"""

import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from backend.jobs.bbm_ocr.receipt_ocr_haiku import ClaudeInterrupted, ClaudeUnavailable
from backend.jobs.fuel_price.page_fetch import PageError, fetch_page
from backend.jobs.fuel_price.price_checks import DAYS_BACK, check_prices, settled_products
from backend.jobs.fuel_price.price_search import MAX_ARTICLES, NoAnswer, add_usage, find_articles, read_article
from backend.jobs.fuel_price.sources import OFFICIAL_LISTS
from backend.repositories import fuel_price_repository
from backend.services.report_filter import MONTH_ZONE

log = logging.getLogger(__name__)

RUN_SECONDS = 30 * 60   # no new article is read after this long (fuel_price_repository fails a run after 40 minutes)
IDLE_SECONDS = 30       # alone: how often to look for a queued refresh


def run_next(search=find_articles, read=read_article, fetch=fetch_page):
    """Take the queued refresh, if any, and run it. Returns "nothing" (none queued), "done", "failed" or
    "unavailable" (Claude can't run: the OCR worker waits before going on). A database error is raised. search, read
    and fetch are how the articles are found, read and downloaded (fake ones in tests)."""
    run = fuel_price_repository.claim_run()
    if run is None:
        return "nothing"
    log.info("Fuel price refresh %d (%s) started.", run["id"], run["trigger"])
    usage = {}
    try:
        return _refresh(run["id"], usage, search, read, fetch)
    except (ClaudeInterrupted, KeyboardInterrupt):
        try:
            fuel_price_repository.release_run(run["id"])
            log.info("Fuel price refresh %d is back in the queue.", run["id"])
        except Exception:  # the database is down too: it fails as stale later
            log.warning("Fuel price refresh %d could not be put back.", run["id"])
        raise KeyboardInterrupt from None
    except ClaudeUnavailable as error:
        log.warning("Fuel price refresh %d failed: Claude can't run: %s", run["id"], error)
        fuel_price_repository.fail_run(run["id"], "claude_unavailable", usage)
        return "unavailable"
    except NoAnswer as error:
        log.warning("Fuel price refresh %d failed (%s): %s", run["id"], error.code, error)
        fuel_price_repository.fail_run(run["id"], error.code, add_usage(usage, error.usage))
        return "failed"
    except Exception:
        log.exception("Fuel price refresh %d went wrong", run["id"])
        fuel_price_repository.fail_run(run["id"], "worker_error", usage)
        return "failed"


def _refresh(run_id, usage, search, read, fetch):
    """Read the merchants' price lists, search and read the news for the rest, check and store the prices (usage
    collects what Claude used, also when it fails)."""
    started = time.monotonic()
    today = datetime.now(MONTH_ZONE).date()
    add_products_if_none()
    products, stored = fuel_price_repository.find_for_refresh()

    # 1. The merchants' own price lists
    lists = []
    for merchant, official in OFFICIAL_LISTS.items():
        own = [product for product in products if product["merchant"] == merchant]
        reading = _read_page(run_id, usage, read, fetch, today, own, official["page"], official["data"]) if own else None
        if reading is not None:
            lists.append({**reading, "merchant": merchant})
    settled = settled_products(today, products, lists)

    # 2. The news, for the products the lists didn't settle
    rest = [product for product in products if product["id"] not in settled]
    urls = []
    if rest:
        try:
            urls, search_usage = search(today, rest)
            add_usage(usage, search_usage)
        except NoAnswer as error:
            if not lists:
                raise
            add_usage(usage, error.usage)  # the price lists' prices are still stored
            log.warning("Fuel price refresh %d: the news search failed (%s): %s", run_id, error.code, error)
    articles = []
    oldest = today - timedelta(days=DAYS_BACK)
    for url in urls:
        if len(articles) >= MAX_ARTICLES:
            break
        if time.monotonic() - started > RUN_SECONDS:
            log.warning("Fuel price refresh %d: out of time, the other articles are not read.", run_id)
            break
        reading = _read_page(run_id, usage, read, fetch, today, rest, url, oldest=oldest)
        if reading is not None:
            articles.append(reading)
    readings = lists + articles
    if not readings:
        raise NoAnswer("no_articles", f"No price list, and none of the {len(urls)} article(s) found, could be read.")

    prices, found, rejected = check_prices(today, products, stored, readings)
    count = fuel_price_repository.finish_run(run_id, prices, found, rejected, usage)
    if count is None:
        log.warning("Fuel price refresh %d stopped running meanwhile (failed as stale); nothing stored.", run_id)
        return "failed"
    log.info("Fuel price refresh %d done: %d price list(s), %d article(s), prices of %d product(s) found, %d stored, "
             "%d rejected, $%.3f (%.0f s).", run_id, len(lists), len(articles), found, count, len(rejected),
             usage.get("cost_usd", 0), time.monotonic() - started)
    return "done"


def add_products_if_none():
    """A first deploy: insert the fuels when the database has none, so the page lists them and a refresh looks for
    their prices (when the worker starts, and before each refresh). A database error is logged: the next try goes
    on."""
    try:
        count = fuel_price_repository.add_products_if_none()
    except Exception as error:
        log.warning("The fuel products could not be checked (%s); trying again at the next refresh.", error)
        return
    if count:
        log.info("There were no fuel products: added %d (backend/database/seeds/fuel_product.sql).", count)


def _read_page(run_id, usage, read, fetch, today, products, url, download=None, oldest=None):
    """Download a page (or the data it is drawn from: download) and have Claude read these products' prices on it.
    Returns {url, text, answers, published} for price_checks, or None when it can't be downloaded, says it was
    published before oldest (not read), or Claude gave no answer (the other pages may do)."""
    try:
        page = fetch(download or url)
    except PageError as error:
        log.info("Fuel price refresh %d: %s can't be read (%s): %s", run_id, download or url, error.code, error)
        return None
    if oldest and page.published and page.published < oldest:
        log.info("Fuel price refresh %d: %s was published %s, over %d days ago: not read.", run_id, url,
                 page.published.strftime("%d-%m-%Y"), DAYS_BACK)
        return None
    text = page.text
    try:
        answers, read_usage = read(today, products, url, text)
    except NoAnswer as error:
        add_usage(usage, error.usage)
        log.warning("Fuel price refresh %d: %s gave no answer (%s): %s", run_id, url, error.code, error)
        return None
    add_usage(usage, read_usage)
    log.info("Fuel price refresh %d: %d price(s) on %s", run_id, len(answers), url)
    return {"url": url, "text": text, "answers": answers, "published": page.published}


def main():
    parser = argparse.ArgumentParser(description="Refresh the fuel prices from the web when a refresh is queued.")
    parser.add_argument("--once", action="store_true", help="run the queued refresh, if any, then stop")
    args = parser.parse_args()

    # The DB_* settings live in the .env file in the repo root.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    add_products_if_none()
    if not args.once:
        log.info("Waiting for queued fuel price refreshes (checking every %d seconds).", IDLE_SECONDS)
    try:
        while True:
            try:
                outcome = run_next()
            except Exception as error:  # the database can't be used: try again later
                if args.once:
                    raise
                log.warning("The database can't be used (%s); trying again in %d seconds.", error, IDLE_SECONDS)
                outcome = "nothing"
            if args.once:
                if outcome == "nothing":
                    log.info("Nothing queued.")
                return
            if outcome in ("nothing", "unavailable"):
                time.sleep(IDLE_SECONDS)
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()

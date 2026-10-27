"""
The fuel price page (GET /api/fuel-prices): the price per liter in DKI Jakarta of every fuel the merchants sell, with
its history (every price change, and a price announced for a later day), and the last refresh from the web.

A refresh (POST /api/fuel-prices/refresh, or a new batch of reports: queue_daily_refresh) is only queued here; the
fuel price job (backend/jobs/fuel_price/worker.py, run by the OCR worker) does it.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import jsonify, request

from backend.jobs.bbm_ocr.product_labels import fuel_product_of
from backend.repositories import fuel_price_repository, user_repository
from backend.services.json_values import to_json
from backend.services.report_filter import MONTH_ZONE

log = logging.getLogger(__name__)

# One refresh per REFRESH_COOLDOWN, from the newest however it was started: the button and a new batch of reports
# both wait for it. Each refresh costs Claude tokens and web searches, and the prices rarely change more than once a
# month.
REFRESH_COOLDOWN = timedelta(days=1)

# fuel_price_run_id: the refresh from the web that stored the price (None for manual and seeded ones), so the page can
# show what the last refresh changed.
PRICE_KEYS = ("id", "price_per_liter", "valid_from", "source", "source_url", "source_text", "fetched_at",
              "fuel_price_run_id")

# What a rejected price may hold, as the worker writes it (fuel_price_run.rejected_prices; valid_from YYYY-MM-DD)
REJECTED_PRICE_KEYS = {"merchant": str, "product": str, "price_per_liter": (int, float), "valid_from": str,
                       "source_url": str, "reason": str}


def list_fuel_prices():
    """GET /api/fuel-prices. Days are WIB: a price valid from 01-11 applies from midnight in Jakarta."""
    now = datetime.now(MONTH_ZONE)
    today = now.date()
    overview = fuel_price_repository.find_overview()

    history = defaultdict(list)
    for price in overview["prices"]:
        history[price["fuel_product_id"]].append({key: price[key] for key in PRICE_KEYS})

    run = overview["last_run"]
    return jsonify(to_json({
        "today": today,
        "products": [_product(product, _changes(history[product["id"]]), today) for product in overview["products"]],
        "last_run": _run(run) if run else None,
        "next_refresh_at": _next_refresh_at(run, now),
    }))


def add_item_prices(report):
    """Give each BBM item of a report (reimbursement_service.report_detail) its fuel_price, for the reviewer: the fuel
    it is (product_labels.fuel_product_of: its fuel type, or the name on its receipts for Performa > 92 and Diesel/Dex)
    with its DKI Jakarta price per liter today and on the item's date, or None when the fuel can't be told:

        {merchant, product, from_receipt, today: {price_per_liter, valid_from, source}, on_date: {...}}

    from_receipt: the fuel type names several fuels, the receipt told which. today or on_date is None when no price of
    it was known that day; price_per_liter is None when the source listed none from valid_from on (not listed).
    valid_from is the day the price started (a price reported again keeps it)."""
    products, prices = fuel_price_repository.find_for_refresh()
    product_ids = {(product["merchant"], product["name"]): product["id"] for product in products}
    history = defaultdict(list)
    for price in prices:
        history[price["fuel_product_id"]].append(price)
    today = datetime.now(MONTH_ZONE).date()

    for item in report["items"]:
        read_names = [line["product_name"] for photo in report["photos"]
                      if item["id"] in photo["item_ids"] and photo["ocr"] for line in photo["ocr"]["lines"]]
        fuel = fuel_product_of(item["product_name"], read_names)
        product_id = product_ids.get(fuel)
        if product_id is None:  # not a fuel of the page (or no longer sold)
            item["fuel_price"] = None
            continue
        changes = _changes(history[product_id])
        item["fuel_price"] = {
            "merchant": fuel[0], "product": fuel[1],
            "from_receipt": fuel_product_of(item["product_name"], []) is None,
            "today": _price_on(changes, today), "on_date": _price_on(changes, item["date_of_expense"]),
        }


def _price_on(changes, day):
    """The price in force on day, from a product's price changes (newest first), or None when none had started."""
    price = next((change for change in changes if change["valid_from"] <= day), None)
    return {key: price[key] for key in ("price_per_liter", "valid_from", "source")} if price else None


def _changes(history):
    """The prices that changed it, newest first. A price equal to the one before it (reported again, or entered again)
    only goes on with it: it is left out, so a price keeps the day it started and the one before it is a different one.
    """
    changes = []
    for price in reversed(history):
        if not changes or price["price_per_liter"] != changes[-1]["price_per_liter"]:
            changes.append(price)
    return changes[::-1]


def queue_refresh():
    """POST /api/fuel-prices/refresh with {"user_email": ...}: queue a refresh from the web. 201 with the run; 409
    while one is queued or running (refresh_active); 429 within REFRESH_COOLDOWN of the newest (refresh_too_soon).
    Who is signed in is checked by the Blibli gateway; the body names the user, who only has to be a known user."""
    body = request.get_json(silent=True)
    email = body.get("user_email") if isinstance(body, dict) else None
    user = user_repository.find_by_email(email.strip().lower()) if isinstance(email, str) and email.strip() else None
    if user is None:
        return _error(400, "invalid_user", 'Send a known user as "user_email".')

    minutes = REFRESH_COOLDOWN.total_seconds() / 60
    outcome, run = fuel_price_repository.queue_button_run(user["email"], minutes)
    if outcome == "active":
        return _error(409, "refresh_active", "A refresh is already queued or running.")
    if outcome == "too_soon":
        next_at = run["requested_at"] + REFRESH_COOLDOWN
        return jsonify(error="refresh_too_soon", message=f"The prices can be refreshed again at {next_at.isoformat()}.",
                       next_refresh_at=to_json(next_at)), 429
    return jsonify(run=to_json(_run(run))), 201


def queue_daily_refresh():
    """Queue the refresh of a new batch of reports (POST /api/reimbursements stored a new one), unless one is queued or
    running, or the newest (the button's too) was asked for less than REFRESH_COOLDOWN ago. A failure is only logged:
    the reports are stored anyway."""
    try:
        outcome, run = fuel_price_repository.queue_batch_run(REFRESH_COOLDOWN.total_seconds() / 60)
    except Exception:
        log.exception("Could not queue the daily fuel price refresh")
        return
    if outcome == "queued":
        log.info("Queued the daily fuel price refresh (run %s)", run["id"])


def _error(status, error, message):
    return jsonify(error=error, message=message), status


def _product(product, history, today):
    """The product with its price today (price), the one before it (previous), the next one announced (upcoming) and
    every price (history, newest first). A price with price_per_liter None: not sold or not listed from that day."""
    past = [price for price in history if price["valid_from"] <= today]
    later = [price for price in history if price["valid_from"] > today]
    return {
        "id": product["id"],
        "merchant": product["merchant"],
        "name": product["name"],
        "fuel_kind": product["fuel_kind"],
        "ron": product["ron"],
        "price": past[0] if past else None,
        "previous": past[1] if len(past) > 1 else None,
        "upcoming": later[-1] if later else None,
        "history": history,
    }


def _run(run):
    return {
        "id": run["id"],
        "trigger": run["trigger"],
        "requested_by": {"email": run["requested_by"], "name": run["requested_by_name"]} if run["requested_by"] else None,
        "status": run["status"],
        "requested_at": run["requested_at"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "error": run["error"],
        "prices_found": run["prices_found"],
        "prices_stored": run["prices_stored"],
        "rejected_prices": _rejected_prices(run["rejected_prices"]),
    }


def _rejected_prices(value):
    """The rejected prices as the website reads them: only the known keys, each of its type (None otherwise), the
    day DD-MM-YYYY."""
    if not isinstance(value, list):
        return None
    rejected = [{key: _typed(item.get(key), kind) for key, kind in REJECTED_PRICE_KEYS.items()}
                for item in value if isinstance(item, dict)]
    for item in rejected:
        try:
            item["valid_from"] = to_json(date.fromisoformat(item["valid_from"])) if item["valid_from"] else None
        except ValueError:
            item["valid_from"] = None
    return rejected


def _typed(value, kind):
    return value if isinstance(value, kind) and not isinstance(value, bool) else None


def _next_refresh_at(run, now):
    """When the button can be pressed again; None when it can now (or would, but for a refresh queued or running)."""
    if run is None:
        return None
    ready_at = run["requested_at"] + REFRESH_COOLDOWN
    return ready_at if ready_at > now else None

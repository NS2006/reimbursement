"""
Checking the prices Claude read on the pages (worker.py) before any is stored. Claude's answers are not trusted: a
page can be wrong, out of date or written to mislead, and Claude can misread one. A price read on a page counts only
when:

- the page is on a listed site (sources.py): the merchant's own site, or a news site;
- the sentence Claude quoted is on the page, states the price and names the product (not another product's name);
- the price is a whole number of rupiah from MIN_PRICE to MAX_PRICE, and the day it starts, when the page gives one,
  is at most DAYS_BACK days before today and DAYS_AHEAD days after.

A price the same as the one stored for its day only confirms it. Any other is a change, stored only when the page
gives the day it starts, two different sites give the same price from the same day (or the merchant's own site gives
it), and it would not replace a price entered by hand, or an official one with one from the news. A change that is not
stored is listed as rejected, with why; a price that failed a check but is the one already stored is not (nothing
would change).

A news article that gives a price without the day it starts says the price applied on the day it was published (from
the page itself, worker.py): its day for the check above is that day (today when the page doesn't say), and the price
is stored when two different sites give it, from the day the second of them gave it (_date_by_publishing). So the day
stored can be later than the real one, never earlier than what the sites back.

A merchant's own price list (sources.OFFICIAL_LISTS) also says which products have no price (stored as a price of
None: "not listed", out of stock): the ones it lists without a price (Claude gives price None, and the line it quotes
gives no price), and the ones it leaves out (_unlisted: decided here, not by Claude). Pertamina's list gives every
province's prices: a line quoted from it must name Jakarta.
"""

import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from backend.jobs.fuel_price.sources import site_of, source_of

MIN_PRICE = 5_000
MAX_PRICE = 60_000
DAYS_BACK = 60
DAYS_AHEAD = 31
MAX_QUOTE_CHARS = 500   # fuel_price.source_text
MAX_REJECTED = 50       # listed on the run
PRICE_NEAR = 40         # a price list gives a product's price within this many characters after its name (no spaces)
# The merchants whose own price list gives a price per province: the line quoted from it must name REGION.
BY_PROVINCE = {"pertamina"}
REGION = "jakarta"


def check_prices(today, products, stored, readings):
    """The prices to store from the pages read in a refresh.

        today:     the day in WIB
        products:  the active products [{id, merchant, name, ron}]
        stored:    their prices [{fuel_product_id, valid_from, price_per_liter, source}], newest valid_from first
        readings:  [{url, text (the page's text Claude read), answers (price_search.read_article), published (the
                   day the page says it was published, or None), merchant (only on a merchant's own price list,
                   sources.OFFICIAL_LISTS)}]

    Returns (prices, found, rejected):

        prices:    [{fuel_product_id, valid_from, price_per_liter (None: not listed), source, source_url,
                   source_text}] (finish_run)
        found:     how many products a price (or "not listed") that passed the checks was found for
        rejected:  [{merchant, product, price_per_liter, valid_from (YYYY-MM-DD or None), source_url, reason}];
                   reason: implausible_price, bad_date, date_out_of_range, wrong_site, quote_not_on_page,
                   price_not_in_quote, product_not_in_quote, region_not_in_quote, priced_in_quote, no_start_date,
                   one_site_only, sites_disagree, manual_kept, official_kept
    """
    by_name = {product["name"]: product for product in products}
    names = {product["id"]: _name_words(product) for product in products}
    history = defaultdict(list)
    for row in stored:
        history[row["fuel_product_id"]].append(row)

    rejected = []
    found = set()
    evidence = defaultdict(list)  # (product id, price, valid_from) -> the pages giving that change
    undated = defaultdict(list)   # (product id, price) -> the pages giving it without a start, with the day published
    for reading in readings:
        checked = _checked_answers(today, by_name, names, reading)
        published = reading.get("published")
        if not isinstance(published, date) or not today - timedelta(days=DAYS_BACK) <= published <= today:
            published = None
        for item in checked:
            product, price, valid_from, problem = item["product"], item["price"], item["valid_from"], item["problem"]
            reject = _rejecter(rejected, product, item["answer"], reading["url"])
            if problem in ("implausible_price", "bad_date", "date_out_of_range"):
                reject(problem, price, valid_from)
                continue
            if problem is None:
                found.add(product["id"])
            in_force = _in_force(history[product["id"]], valid_from or published or today)
            if in_force is not None and in_force["price_per_liter"] == price:
                continue  # it confirms the stored price
            page = {"site": site_of(reading["url"]), "source": item["source"], "url": reading["url"],
                    "quote": item["quote"].strip()}
            if problem:
                reject(problem, price, valid_from)
            elif valid_from is not None:
                evidence[(product["id"], price, valid_from)].append(page)
            elif published is not None:
                undated[(product["id"], price)].append({**page, "day": published})
            else:
                reject("no_start_date", price)
        unlisted, day = _unlisted(today, products, reading, checked)
        for product in unlisted:  # left out of the merchant's own list: not listed from the list's day
            found.add(product["id"])
            in_force = _in_force(history[product["id"]], day)
            if in_force is None or in_force["price_per_liter"] is not None:
                evidence[(product["id"], None, day)].append(
                    {"site": reading["merchant"], "source": "official", "url": reading["url"], "quote": ""})

    by_id = {product["id"]: product for product in products}
    _date_by_publishing(evidence, undated, history, rejected, by_id)
    changes = defaultdict(list)  # (product id, valid_from) -> the changes that passed
    for (product_id, price, valid_from), pages in evidence.items():
        product = by_id[product_id]
        reject = _rejecter(rejected, product, None, pages[0]["url"])
        official = [page for page in pages if page["source"] == "official"]
        if not official and len({page["site"] for page in pages}) < 2:
            reject("one_site_only", price, valid_from)
            continue
        same_day = next((row for row in history[product_id] if row["valid_from"] == valid_from), None)
        if same_day is not None and same_day["source"] == "manual":
            reject("manual_kept", price, valid_from)
            continue
        if same_day is not None and same_day["source"] == "official" and not official:
            reject("official_kept", price, valid_from)
            continue
        best = (official or pages)[0]
        changes[(product_id, valid_from)].append({
            "fuel_product_id": product_id, "valid_from": valid_from, "price_per_liter": price,
            "source": best["source"], "source_url": best["url"],
            "source_text": best["quote"][:MAX_QUOTE_CHARS] or None,
        })

    prices = []
    for (product_id, valid_from), options in changes.items():
        if len(options) == 1:
            prices.append(options[0])
            continue
        for option in options:  # two prices from the same day, each from two sites: neither is trusted
            _rejecter(rejected, by_id[product_id], None, option["source_url"])(
                "sites_disagree", option["price_per_liter"], valid_from)
    return prices, len(found), rejected[:MAX_REJECTED]


def _date_by_publishing(evidence, undated, history, rejected, by_id):
    """Give the prices pages gave without a start a day, in evidence: when the merchant's own site gives the price, the
    day it was published; when two different sites give it (some with a start, some without), the day the second of
    them gave it (each site's earliest day: its start, or the day its page was published). The price's pages with a
    start that settle it alone (two sites the same day, or the merchant's own site) are left as they are."""
    for (product_id, price), pages in undated.items():
        dated = {key: found for key, found in evidence.items() if key[:2] == (product_id, price)}
        if any(_settles(found) for found in dated.values()):
            continue
        entries = [{**page, "day": key[2]} for key, found in dated.items() for page in found] + pages
        site_days = {}
        for entry in entries:
            site_days[entry["site"]] = min(entry["day"], site_days.get(entry["site"], entry["day"]))
        official = [entry["day"] for entry in entries if entry["source"] == "official"]
        if official:
            start = min(official)
        elif len(site_days) >= 2:
            start = sorted(site_days.values())[1]
        else:
            for page in pages:
                _rejecter(rejected, by_id[product_id], None, page["url"])("no_start_date", price)
            continue
        for key in dated:
            del evidence[key]
        in_force = _in_force(history[product_id], start)
        if in_force is not None and in_force["price_per_liter"] == price:
            continue  # in force on that day already
        # the page of the start day first: its quote is stored with the price
        evidence[(product_id, price, start)] = sorted(entries, key=lambda entry: entry["day"] != start)


def _settles(pages):
    """Whether these pages settle a price on their own: the merchant's own site gives it, or two different sites."""
    return any(page["source"] == "official" for page in pages) or len({page["site"] for page in pages}) >= 2


def settled_products(today, products, readings):
    """The ids of the products the merchants' own price lists settle: a price of them (or "not listed") from a list
    passed the checks with the day it starts, or the list leaves them out (_unlisted). The news is not searched for
    them; it is for every other product (all of a merchant's when its list can't be downloaded or read)."""
    by_name = {product["name"]: product for product in products}
    names = {product["id"]: _name_words(product) for product in products}
    settled = set()
    for reading in readings:
        checked = _checked_answers(today, by_name, names, reading)
        settled |= {item["product"]["id"] for item in checked if item["problem"] is None and item["valid_from"]}
        settled |= {product["id"] for product in _unlisted(today, products, reading, checked)[0]}
    return settled


def _checked_answers(today, by_name, names, reading):
    """Every answer about a known product on a page, checked: [{product, answer, price, valid_from, source, quote,
    problem}]; problem: why it doesn't count (a rejected reason), or None. price None: listed without a price, only
    on the merchant's own list, and only when Claude gave no price of the product from it."""
    page = _squash(reading["text"])
    answers = [answer for answer in reading["answers"] if answer.get("product") in by_name]
    priced = {answer["product"] for answer in answers if _price(answer.get("price_per_liter")) is not None}
    checked = []
    for answer in answers:
        product = by_name[answer["product"]]
        source = source_of(reading["url"], product["merchant"])
        quote = answer.get("source_text") if isinstance(answer.get("source_text"), str) else ""
        item = {"product": product, "answer": answer, "price": None, "valid_from": None, "source": source,
                "quote": quote, "problem": None}
        checked.append(item)
        if answer.get("price_per_liter") is None and reading.get("merchant") == product["merchant"]:
            if product["name"] in priced:
                checked.pop()  # the list gives a price of it too (another line of a similar name)
                continue
        else:
            item["price"] = _price(answer.get("price_per_liter"))
            if item["price"] is None:
                item["problem"] = "implausible_price"
                continue
        item["valid_from"], item["problem"] = _day(answer.get("valid_from"), today)
        if item["problem"] is None:
            item["problem"] = _quote_problem(source, quote, answer.get("name_on_page"), page, item["price"], product,
                                             names, reading.get("merchant") == product["merchant"])
    return checked


def _unlisted(today, products, reading, checked):
    """The products a merchant's own price list leaves out, and the day the list is from: (products, day). Only when
    the list was read well (a price of the merchant's passed the checks, with the day it starts, today or before), and
    only the products no price of passed and whose name the list doesn't show with a price after it: a product Claude
    missed is never taken for one left out."""
    merchant = reading.get("merchant")
    passed = [item for item in checked if item["problem"] is None and item["product"]["merchant"] == merchant]
    days = [item["valid_from"] for item in passed if item["valid_from"] and item["valid_from"] <= today]
    if not merchant or not days:
        return [], None
    page = _squash(reading["text"])
    settled = {item["product"]["id"] for item in passed}
    return [product for product in products if product["merchant"] == merchant and product["id"] not in settled
            and not _shows_price(page, product, products)], max(days)


def _shows_price(page, product, products):
    """Whether the page (squashed) gives the product's name with a price within PRICE_NEAR characters after it, not as
    the start of a longer product's name ("Shell V-Power" in "Shell V-Power Diesel Rp25,420" is V-Power Diesel)."""
    name = _squash(product["name"])
    longer = [_squash(other["name"]) for other in products
              if other["id"] != product["id"] and _squash(other["name"]).startswith(name)]
    for match in re.finditer(re.escape(name), page):
        if any(page.startswith(other, match.start()) for other in longer):
            continue
        if _prices_in(page[match.end():match.end() + PRICE_NEAR]):
            return True
    return False


def _rejecter(rejected, product, answer, url):
    """A function listing this product's price as rejected, once per price, day and reason."""
    def reject(reason, price=None, valid_from=None):
        if price is None and answer is not None:  # the price Claude gave, when it is a number at all
            given = answer.get("price_per_liter")
            if isinstance(given, (int, float)) and not isinstance(given, bool) and math.isfinite(given):
                price = given
        entry = {"merchant": product["merchant"], "product": product["name"],
                 "price_per_liter": price, "valid_from": valid_from.isoformat() if valid_from else None,
                 "source_url": url, "reason": reason}
        if not any(_same(entry, other) for other in rejected):
            rejected.append(entry)
    return reject


def _same(entry, other):
    return all(entry[key] == other[key] for key in ("product", "price_per_liter", "valid_from", "reason"))


def _price(value):
    """A whole number of rupiah from MIN_PRICE to MAX_PRICE, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if value != int(value) or not MIN_PRICE <= value <= MAX_PRICE:
        return None
    return int(value)


def _day(value, today):
    """(the day a price starts, or None when the page gives none; why it is refused, or None)."""
    if value is None or value == "":
        return None, None
    try:
        day = date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        day = None
    if day is None:
        return None, "bad_date"
    if not today - timedelta(days=DAYS_BACK) <= day <= today + timedelta(days=DAYS_AHEAD):
        return day, "date_out_of_range"
    return day, None


def _quote_problem(source, quote, name_on_page, page, price, product, names, own_list):
    """Why the page's quote doesn't back the price (None: "not listed"), or None. own_list: the page is the product's
    merchant's own price list."""
    if source is None:
        return "wrong_site"  # another merchant's own site
    if not quote.strip() or len(quote) > MAX_QUOTE_CHARS or _squash(quote) not in page:
        return "quote_not_on_page"
    if price is None and _prices_in(quote):
        return "priced_in_quote"  # "not listed", but its line gives a price
    if price is not None and not _states_price(quote, price):
        return "price_not_in_quote"
    if not isinstance(name_on_page, str) or _squash(name_on_page) not in _squash(quote) \
            or not _names_product(name_on_page, product, names):
        return "product_not_in_quote"
    if own_list and product["merchant"] in BY_PROVINCE and REGION not in _squash(quote):
        return "region_not_in_quote"
    return None


def _squash(text):
    """The text without spaces, in lower case, for finding a quote on a page."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def _states_price(quote, price):
    """Whether the quote states the price, with or without thousands separators (Rp19.150, Rp 19,150, 19150)."""
    return re.search(rf"(?<!\d){price}(?!\d)", _flat(quote)) is not None


def _prices_in(text):
    """The prices (MIN_PRICE to MAX_PRICE) the text gives."""
    return [int(number) for number in re.findall(r"(?<!\d)\d+(?!\d)", _flat(text))
            if MIN_PRICE <= int(number) <= MAX_PRICE]


def _flat(text):
    """The text without thousands separators in its numbers (Rp19.150 -> Rp19150)."""
    return re.sub(r"(?<=\d)[.,](?=\d{3}(?!\d))", "", unicodedata.normalize("NFKC", text))


# Words a page puts around a product's name that don't tell products apart: the merchants (BP stations are "BP-AKR")
BRAND_WORDS = {"pertamina", "shell", "bp", "akr", "vivo"}
# Names pages use that share no word with the product's own name
ALIASES = {"Biosolar": ["Solar", "Bio Solar"]}
# Words that make a name on a page a product the app doesn't track: Pertashop's (an outlet, not a station), for
# industry, or non-subsidised Biosolar (Biosolar is the subsidised one). Pertamina's list gives them next to ours.
OTHER_PRODUCT_WORDS = {"pertashop", "industri", "industry", "non"}


def _words(name):
    """The words of a product name, without merchants' names and what is written in brackets or as RON / CN:
    "Vivo Revvo 92" -> {"revvo", "92"}, "Pertamax (RON 92)" -> {"pertamax"}, "Shell V-Power" -> {"v", "power"}."""
    name = unicodedata.normalize("NFKC", name).casefold()
    name = re.sub(r"\([^)]*\)|(?:ron|cn)\s*\d+", " ", name)
    return frozenset(re.findall(r"[0-9a-z]+", name)) - BRAND_WORDS


def _name_words(product):
    """The ways a page names the product, as word sets: its name, and its other names (Solar for Biosolar)."""
    return [words for words in map(_words, [product["name"], *ALIASES.get(product["name"], [])]) if words]


def _names_product(name_on_page, product, names):
    """Whether the name the page gives is this product: the product whose name it holds, or is part of, best (the
    most words in common, then the fewest left over). "Diesel Primus" and "Vivo Primus Plus Diesel" are Diesel Primus
    Plus, "Pertamax Green" is Pertamax Green 95, but "Pertamax" is never Pertamax Turbo, nor "V-Power" V-Power Diesel;
    a name two products fit as well is neither, and "Pertamax Pertashop" none (OTHER_PRODUCT_WORDS)."""
    page = _words(name_on_page)
    if not page or page & OTHER_PRODUCT_WORDS:
        return False
    scores = {}
    for product_id, options in names.items():
        fits = [(len(page & words), -len(page ^ words)) for words in options if words <= page or page <= words]
        if fits:
            scores[product_id] = max(fits)
    best = max(scores.values(), default=None)
    return best is not None and scores.get(product["id"]) == best and list(scores.values()).count(best) == 1


def _in_force(history, day):
    """The stored price in force on the day (history: newest valid_from first), or None."""
    return next((row for row in history if row["valid_from"] <= day), None)

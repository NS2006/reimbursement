"""
Downloading a news or merchant page for Claude to read (worker.py); the sentences it quotes are checked against the
same text (price_checks.py). A merchant's price data (JSON) becomes text too: one line per product (json_text). A news
page also gives the day it was published, so the worker skips old articles before Claude reads them.

The address comes from Claude, which found it on the web, so it is treated as untrusted: https only, on a listed site
(sources.ALL_HOSTS), to public internet addresses only (the address is looked up once and that same address is
connected to, so a name can't point somewhere else between the check and the download), at most MAX_REDIRECTS
redirects (each checked the same way), MAX_PAGE_BYTES and DEADLINE_SECONDS in all, and text pages or JSON only.
"""

import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import zlib
from datetime import date
from typing import NamedTuple
from urllib.parse import urljoin, urlsplit

from backend.jobs.fuel_price.sources import ALL_HOSTS

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 3
DEADLINE_SECONDS = 30
USER_AGENT = "Mozilla/5.0 (compatible; reimbursement-fuel-price-check/1.0)"
MAX_CONTEXT_CHARS = 120   # a JSON value longer than this is not repeated on the lines of the objects inside its own
# The meta tags (name, property or itemprop) news sites give an article's publishing time in, after its structured
# data's datePublished (Kompas, detik, CNBC Indonesia, Liputan6 give both).
PUBLISHED_TAGS = {"article:published_time", "datepublished", "publishdate", "pubdate", "dtk:publishdate",
                  "content_publisheddate"}


class Page(NamedTuple):
    """A downloaded page: its text for Claude, and the day it was published (None when the page doesn't say)."""
    text: str
    published: date | None


class PageError(Exception):
    """The page can't be checked: not_allowed (another site, not https, not a public address), unreachable, not_text
    (also JSON that can't be read), too_large."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An https connection to an address looked up beforehand, still checking the certificate of the host name."""

    def __init__(self, host, address, timeout):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch_page(url):
    """The page: its text (tags and scripts removed, spaces collapsed; JSON as json_text) and the day it was
    published. Raises PageError."""
    deadline = time.monotonic() + DEADLINE_SECONDS
    for _ in range(MAX_REDIRECTS + 1):
        host, path, address = _checked(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PageError("unreachable", "The page took too long.")
        connection = _PinnedHTTPSConnection(host, address, timeout=min(remaining, 15))
        try:
            connection.request("GET", path, headers={"Host": host, "User-Agent": USER_AGENT,
                                                     "Accept": "text/html, application/json",
                                                     "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise PageError("unreachable", "A redirect without a location.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise PageError("unreachable", f"The site answered {response.status}.")
            content_type = (response.getheader("Content-Type") or "").lower()
            is_json = re.match(r"application/([\w.-]+\+)?json\b", content_type) is not None
            if not is_json and not content_type.startswith(("text/html", "text/plain", "application/xhtml")):
                raise PageError("not_text", f"Not a text page ({content_type or 'no type'}).")
            body = response.read(MAX_PAGE_BYTES + 1)
            if len(body) > MAX_PAGE_BYTES:
                raise PageError("too_large", "The page is too large.")
            if (response.getheader("Content-Encoding") or "").lower() == "gzip":  # sent although not asked for
                inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
                body = inflater.decompress(body, MAX_PAGE_BYTES + 1)
                if len(body) > MAX_PAGE_BYTES or inflater.unconsumed_tail:
                    raise PageError("too_large", "The page is too large.")
        except (OSError, http.client.HTTPException, zlib.error) as error:
            raise PageError("unreachable", f"The page could not be downloaded: {error}") from error
        finally:
            connection.close()
        charset = re.search(r"charset=([\w-]+)", content_type)
        try:
            text = body.decode(charset.group(1) if charset else "utf-8", "replace")
        except LookupError:
            text = body.decode("utf-8", "replace")
        if not is_json:
            return Page(to_text(text), published_day(text))
        try:
            return Page(json_text(json.loads(text)), None)
        except (ValueError, RecursionError) as error:
            raise PageError("not_text", f"The data can't be read: {error}") from error
    raise PageError("unreachable", "Too many redirects.")


def published_day(page):
    """The day an HTML page says it was published: its structured data's datePublished, or a meta tag
    (PUBLISHED_TAGS); None when it says neither."""
    found = re.search(r'"datePublished"\s*:\s*"([^"]{8,40})"', page)
    values = [found.group(1)] if found else []
    for tag in re.findall(r"<meta\b[^>]*>", page, flags=re.I):
        attributes = {key.lower(): value for key, value in re.findall(r"([\w:.-]+)\s*=\s*[\"']([^\"']*)[\"']", tag)}
        if {attributes.get(key, "").lower() for key in ("name", "property", "itemprop")} & PUBLISHED_TAGS:
            values.append(attributes.get("content", ""))
    for value in values:
        match = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
        if not match:
            continue
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
    return None


def to_text(page):
    """The visible text of an HTML page, its spaces collapsed."""
    page = re.sub(r"<(script|style|noscript|template)\b.*?</\1\s*>", " ", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def json_text(data):
    """JSON data as text Claude can read and quote, one line per object: its plain values as "key: value", after the
    short values of the list items it is in. A price list by province gives "province: Prov. DKI Jakarta | product:
    PERTAMAX | price: 15950 | updatedDate: ...", so the line of a price names its province too. HTML in a value
    becomes its text. Any shape of data is read the same way: nothing here depends on how a merchant lays out its
    data."""
    return "\n".join(_json_lines(data, (), False))


def _json_lines(value, context, item):
    """The lines of a JSON value; context: the values the lines start with; item: the value is an item of a list."""
    if isinstance(value, list):
        return [line for entry in value for line in _json_lines(entry, context, True)]
    if not isinstance(value, dict):
        plain = _plain(value)
        return [" | ".join((*context, plain))] if plain else []
    own, nested = [], []
    for key, entry in value.items():
        if isinstance(entry, (dict, list)):
            nested.append(entry)
        elif plain := _plain(entry):
            own.append(f"{key}: {plain}")
    if not nested:
        return [" | ".join((*context, *own))] if own else []
    # A list item's short values go on the lines of the objects inside it (a province on its products' lines); the
    # rest, and an object's values that aren't a list item's (a reply's status), go on a line of their own.
    passed = [pair for pair in own if len(pair) <= MAX_CONTEXT_CHARS] if item else []
    lines = [line for entry in nested for line in _json_lines(entry, (*context, *passed), False)]
    if own and (len(passed) < len(own) or not lines):
        lines.insert(0, " | ".join((*context, *own)))
    return lines


def _plain(value):
    """A JSON value as one line of text ("" for null): HTML becomes its text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    return to_text(text) if "<" in text else re.sub(r"\s+", " ", text).strip()


def _checked(url):
    """(host, path with query, a public address of the host) for an allowed https address. Raises PageError."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.username or host not in ALL_HOSTS:
        raise PageError("not_allowed", f"Not a listed https site: {host or url[:80]}")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as error:
        raise PageError("unreachable", f"{host} could not be found: {error}") from error
    if not addresses or not all(ipaddress.ip_address(address.split("%")[0]).is_global for address in addresses):
        raise PageError("not_allowed", f"{host} is not a public internet address.")
    path = parts.path or "/"
    address = sorted(addresses, key=lambda item: (":" in item, item))[0]  # IPv4 first
    return host, path + (f"?{parts.query}" if parts.query else ""), address

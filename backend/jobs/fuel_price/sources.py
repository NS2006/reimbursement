"""
The web pages a fuel price may come from: the only sites the job downloads (page_fetch.py) and gives Claude to read.
A price from a merchant's own site is "official", from a news site "news"; any other site is refused. Pertamina's and
Shell's own price lists are read on every refresh; the news is searched for the products they don't settle.
"""

from urllib.parse import urlsplit

# The merchants' own sites. BP's price page refuses a download and Vivo's site doesn't answer: their prices come from
# the news only.
OFFICIAL_HOSTS = {
    "pertamina": {"mypertamina.id", "www.mypertamina.id", "api.web.mypertamina.id", "pertaminapatraniaga.com",
                  "www.pertaminapatraniaga.com"},
    "shell": {"shell.co.id", "www.shell.co.id"},
    "bp": set(),
    "vivo": set(),
}

# The merchants' own price lists, read on every refresh (no search needed). Their pages draw the list with JavaScript,
# so a download of the page has no prices; the job downloads the data the page draws it from (data) and Claude reads it
# like an article. page is what a stored price links to. Their layout is not relied on (page_fetch.json_text): only
# these addresses.
OFFICIAL_LISTS = {
    "pertamina": {
        "page": "https://mypertamina.id/about/product-price",
        "data": "https://api.web.mypertamina.id/price",
    },
    "shell": {
        "page": "https://www.shell.co.id/in_id/pengendara-bermotor/bahan-bakar-shell/harga-bahan-bakar-shell.html",
        "data": "https://www.shell.co.id/in_id/pengendara-bermotor/bahan-bakar-shell/harga-bahan-bakar-shell.model.json",
    },
}

# Indonesian news sites that publish the prices of every merchant, and the parts of them that do: the ones whose pages
# can be downloaded and read (Bisnis.com refuses the download, Kumparan draws its articles with JavaScript). Six are
# enough for two of them to agree on a new price.
NEWS_SITES = {
    "kompas.com": ["money", "otomotif", "megapolitan"],
    "detik.com": ["finance", "oto"],
    "cnbcindonesia.com": [],
    "liputan6.com": [],
    "antaranews.com": ["megapolitan"],
    "katadata.co.id": ["databoks"],
}
NEWS_HOSTS = {host for site, parts in NEWS_SITES.items()
              for host in [site, f"www.{site}"] + [f"{part}.{site}" for part in parts]}

ALL_HOSTS = NEWS_HOSTS.union(*OFFICIAL_HOSTS.values())


def site_of(url):
    """The site a listed https address belongs to: the merchant ("pertamina", "shell") for its own pages, the news
    site ("kompas.com" for money.kompas.com too), or None (any other site, or not https). Two pages agree from two
    different sites only when their sites differ."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.username:
        return None
    for merchant, hosts in OFFICIAL_HOSTS.items():
        if host in hosts:
            return merchant
    if host in NEWS_HOSTS:
        return next(site for site in NEWS_SITES if host == site or host.endswith(f".{site}"))
    return None


def source_of(url, merchant):
    """"official" (the merchant's own site), "news" (a listed news site) or None (any other site, or not https)."""
    site = site_of(url)
    if site is None:
        return None
    if site in OFFICIAL_HOSTS:
        return "official" if site == merchant else None
    return "news"

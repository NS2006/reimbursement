import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Downloading the file of an attachment (a receipt photo or PDF) from the other system's file host: for the website
# (attachment_service.py) and for the OCR worker (backend/jobs/bbm_ocr/worker.py).

MAX_FILE_BYTES = 25 * 1024 * 1024
TIMEOUT_SECONDS = 20

# What can be shown and read, recognised by the first bytes of the file (not by the name or the host's
# Content-Type, which can be wrong). SVG is left out on purpose: it can carry scripts.
SIGNATURES = [
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
]

# The file name extension of each type, for saving a downloaded file
EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}


class DownloadError(Exception):
    """The file could not be downloaded, or is not an image or a PDF. status and error are for an API answer."""

    def __init__(self, status, error, message):
        super().__init__(message)
        self.status = status
        self.error = error


def allowed_hosts():
    """The file hosts the backend may download from: ATTACHMENT_HOSTS in .env, host or host:port separated by
    commas (e.g. "files.example.com,127.0.0.1:5000"). Empty: any host (the addresses come from the other systems,
    so set it outside local development)."""
    return {host.strip().lower() for host in os.getenv("ATTACHMENT_HOSTS", "").split(",") if host.strip()}


def _host_allowed(url):
    hosts = allowed_hosts()
    parts = urlsplit(url)
    return not hosts or (parts.netloc or "").lower() in hosts or (parts.hostname or "").lower() in hosts


class _CheckedRedirects(HTTPRedirectHandler):
    """Follow a redirect only to another http or https address on an allowed host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme not in ("http", "https") or not _host_allowed(newurl):
            raise HTTPError(newurl, code, "redirect to an address that is not allowed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = build_opener(_CheckedRedirects)


def download(url, name):
    """(data, content_type) of the file at url, at most MAX_FILE_BYTES; name is the file's name, for the messages.
    Raises DownloadError when the host is not allowed, fails or cannot be reached, the file is too large, or it is
    neither an image nor a PDF."""
    if not _host_allowed(url):
        raise DownloadError(502, "file_host_not_allowed",
                            f"The file host of {name} is not one the backend may download from (ATTACHMENT_HOSTS).")
    try:
        with _opener.open(Request(url, headers={"User-Agent": "reimbursement-backend"}),
                          timeout=TIMEOUT_SECONDS) as response:
            data = response.read(MAX_FILE_BYTES + 1)
    except HTTPError as error:
        raise DownloadError(502, "file_unreachable", f"The file host answered HTTP {error.code} for {name}.") from None
    except (URLError, TimeoutError, OSError):
        raise DownloadError(502, "file_unreachable", f"The file host of {name} can't be reached.") from None
    if len(data) > MAX_FILE_BYTES:
        raise DownloadError(502, "file_too_large", f"{name} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")

    content_type = content_type_of(data)
    if content_type is None:
        raise DownloadError(415, "unsupported_file", f"{name} is not an image or a PDF.")
    return data, content_type


def content_type_of(data):
    """image/... or application/pdf from the first bytes of a file; None for anything else."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return next((content_type for signature, content_type in SIGNATURES if data.startswith(signature)), None)

"""
Where the receipt files are kept. The links the other systems send expire (Darwinbox's after 10 minutes), so
POST /api/reimbursements downloads every file at once and stores it here; the website and the OCR worker read the file
from here, never from the link.

GCS_BUCKET set (in .env): a Google Cloud Storage bucket. Keep it private: the backend's service account only needs to
create and read objects, and the credentials come from Application Default Credentials (Workload Identity on GCP,
`gcloud auth application-default login` on a laptop), never from a key in the code.
GCS_BUCKET not set: a local folder, backend/storage/ (development and tests).

A file is stored under its SHA-256 (attachments/<sha256>.<ext>), so the same file sent again is stored once.
The storage_path saved for an attachment says where it is: gs://<bucket>/attachments/... or local:<path in the repo>.
"""

import os
import tempfile
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_FOLDER = REPO_ROOT / "backend" / "storage"
# The local folders a local: path may point into: the local storage, and the dummy receipts of the seed.
LOCAL_FOLDERS = (LOCAL_FOLDER, REPO_ROOT / "backend" / "database" / "dummy_bbm_receipt")
TIMEOUT_SECONDS = 30  # per try; and how long to keep retrying in all (the library's default is 2 minutes, too long to
                      # hold the caller's request when the storage is down)


class StorageError(Exception):
    """A file could not be stored or read. missing: there is no such file (reading again will not help)."""

    def __init__(self, message, missing=False):
        super().__init__(message)
        self.missing = missing


def save(data, sha256, extension, content_type):
    """Store a file (once: an existing copy is kept) and return its storage_path. Raises StorageError."""
    name = f"attachments/{sha256}{extension}"
    bucket = os.getenv("GCS_BUCKET", "").strip()
    if bucket:
        return _save_to_bucket(bucket, name, data, content_type)
    return _save_to_folder(name, data)


def read(storage_path):
    """The bytes of a stored file. Raises StorageError (missing=True when there is no such file)."""
    if storage_path.startswith("gs://"):
        bucket, _, name = storage_path.removeprefix("gs://").partition("/")
        return _read_from_bucket(bucket, name)
    if storage_path.startswith("local:"):
        return _read_from_folder(storage_path.removeprefix("local:"))
    raise StorageError(f"Unknown storage path {storage_path!r}.", missing=True)


# ---------------------------------------------------------------------------
# Google Cloud Storage
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _client():
    from google.cloud import storage  # only needed when GCS_BUCKET is set

    return storage.Client()


def _retry():
    from google.cloud.storage.retry import DEFAULT_RETRY

    return DEFAULT_RETRY.with_timeout(TIMEOUT_SECONDS)


def _save_to_bucket(bucket, name, data, content_type):
    from google.api_core.exceptions import PreconditionFailed

    try:
        blob = _client().bucket(bucket).blob(name)
        # if_generation_match=0: write only if the object does not exist yet (the same content is already there)
        blob.upload_from_string(data, content_type=content_type, if_generation_match=0, timeout=TIMEOUT_SECONDS,
                                retry=_retry())
    except PreconditionFailed:
        pass
    except Exception as error:  # credentials, network, permissions: the storage is not usable now
        raise StorageError(f"The file storage could not be reached ({type(error).__name__}).") from error
    return f"gs://{bucket}/{name}"


def _read_from_bucket(bucket, name):
    from google.api_core.exceptions import NotFound

    try:
        return _client().bucket(bucket).blob(name).download_as_bytes(timeout=TIMEOUT_SECONDS, retry=_retry())
    except NotFound:
        raise StorageError(f"gs://{bucket}/{name} is not in the file storage.", missing=True) from None
    except Exception as error:
        raise StorageError(f"The file storage could not be reached ({type(error).__name__}).") from error


# ---------------------------------------------------------------------------
# Local folder (development)
# ---------------------------------------------------------------------------

def _save_to_folder(name, data):
    path = LOCAL_FOLDER / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written next to it, then renamed: a reader never sees half a file, and two requests saving the same
        # file at once both end with it whole.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as part:
            part.write(data)
        os.replace(part.name, path)
    return "local:" + path.relative_to(REPO_ROOT).as_posix()


def _read_from_folder(relative):
    path = (REPO_ROOT / relative).resolve()
    if not any(path.is_relative_to(folder) for folder in LOCAL_FOLDERS):
        raise StorageError(f"local:{relative} is outside the local file storage.", missing=True)
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise StorageError(f"local:{relative} is not in the local file storage.", missing=True) from None

import json
import re
from pathlib import Path


_PDF_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")


def load_json(path):
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def is_pdf(path):
    """Whether the file is a PDF, by its first bytes (not its name)."""
    with Path(path).open("rb") as file:
        return file.read(5) == b"%PDF-"


def pdf_page_count(path):
    """
    Pages of a PDF, counted from its page objects; None when they can't be counted this way
    (stored in compressed object streams).
    """
    return len(_PDF_PAGE.findall(Path(path).read_bytes())) or None

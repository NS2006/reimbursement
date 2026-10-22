from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

IMAGE_DIR = BASE_DIR / "images"
SCHEMA_PATH = BASE_DIR / "gas_station_receipt.schema.json"

RESULT_PATH = BASE_DIR / "results"
OUTPUT_PATH = RESULT_PATH / "batch_results.json"
GT_PATH = BASE_DIR / "ground_truth" / "gt.json"
REPORT_PATH = RESULT_PATH / "accuracy_report.json"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
}

# A PDF is given to Claude whole. Claude Code reads a PDF of up to 10 pages by itself (a longer one needs
# pdftoppm from poppler, which is GPL) and of at most 20 MB.
PDF_EXTENSIONS = {".pdf"}
MAX_PDF_PAGES = 10
MAX_PDF_BYTES = 20 * 1024 * 1024

# Numeric comparison tolerance
NUMERIC_TOLERANCE = 0.01

RECEIPT_FIELDS = [
    "date",
    "discount",
    "total",
]

PRODUCT_FIELDS = [
    "name",
    "quantity",
    "unit_price",
    "total_price",
]

# Matching modes:
RECEIPT_MATCHING = "best_match"
PRODUCT_MATCHING = "name"

# Evaluation behavior
NULLS_COUNT_AS_CORRECT = True
INCLUDE_CORRECT_COMPARISONS = True

# Maximum number of error categories shown in the summary
TOP_ERROR_TYPES = 20
"""
Reusable gas-station receipt extraction using Claude Haiku 5.5 on Google Vertex AI.

Main usage:

    result, usage = extract_receipts(
        image_path="images/1.jpg",
        schema_path="gas_station_receipt.schema.json",
    )

The function returns:

    result -> Python dict containing the extracted receipts
    usage  -> dict containing token usage information

No output JSON file is created automatically.

Same public functions as receipt_ocr_luna.py, so it can replace it:
    extract_receipts, add_usage, BASE_USAGE_KEYS, receipt_problems
"""

from __future__ import annotations

import os
import time
import json
import base64
import pathlib
from typing import Any

import anthropic
from dotenv import load_dotenv


# ================================================================
# Configuration
# ================================================================

# reimbursement/.env is read here: GCP_PROJECT_ID, GCP_REGION
load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")

# <<< FILL IN:
MODEL = "MODEL"

# <<< FILL IN 
#   GCP_PROJECT_ID = the Google Cloud project that is billed and has Haiku 5.5 enabled
#   GCP_REGION     = where the model runs: "global" (recommended) or e.g. "us-east5"
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "global")

# Thinking depth: "low" | "medium" | "high" | "xhigh" | "max". Haiku 5.5 defaults to "medium".
EFFORT = "medium"

MAX_TOKENS = 16000          # thinking tokens also count here; the JSON answer itself is small
TIMEOUT_SECONDS = 180       # per request; the SDK itself retries 429 and 5xx errors twice


# ================================================================
# Prompt
# ================================================================

EXTRACTION_PROMPT = """
Extract every fuel-station receipt in the image as JSON matching the schema. Ignore other documents. Return JSON only.

RECEIPTS
- One entry per physical receipt, in reading order (top to bottom, then left to right). Never merge, skip or deduplicate receipts: receipts with identical values but different dates are separate entries. Several products on one receipt stay in that one entry.
- Use only printed evidence. Never invent, guess or back-solve a value. If a value is unreadable or unsupported use null with confidence 0 (discount uses 0).

FIELDS
- date: exactly as printed (same format, no time, never reformat). Read day, month and year digit by digit.
- name: product name as printed (do not correct or expand).
- quantity: liters. Its separator is a decimal point: 32,389 and 32.389 both mean 32.389. Never a pump number, nozzle, ID or time.
- unit_price: GROSS price per liter before any discount or subsidy. Never the reduced customer price.
- total_price: GROSS product amount before discount: printed, or quantity x unit_price when both are printed. With no discount it equals the amount paid for that product.
- discount: total discount or subsidy actually applied to this transaction, as a positive number; 0 if none or not proven. Count only amounts printed in the transaction lines, or a printed per-unit subsidy x quantity. These are NOT discounts: footer promotions, subsidy or eligibility text, loyalty messages, tax lines, or a price difference nobody labels as a discount.
- total: final amount paid for the whole receipt (Total, Total Bayar, Jumlah). Not cash tendered (Tunai), change (Kembali), points or tax lines.

NUMBERS
- JSON numbers only, rupiah without currency symbol. In money, a . or , followed by exactly 3 digits is a thousands separator: 12.700 and 12,700 both mean 12700, and 646.180 means 646180. A separator followed by 2 digits (like ,00) is a decimal; drop it.
- Fuel unit prices are normally thousands of rupiah per liter, so a unit_price under 1000 (such as 12.7 or 20.63) almost always means a misread separator: read it again. Follow the printed digits, never scale by 1000 or change digits to fit arithmetic. If still ambiguous use null.
- Separator style can differ between receipts: infer it from the other amounts on the same receipt.

CHECKS
Before answering verify: quantity x unit_price is about total_price, and total_price summed over products minus discount is about total. Use a mismatch only to read misread digits again. Never use it to overwrite clearly printed values or fill missing ones. Never copy total into total_price when a discount exists.

CONFIDENCE
Per field, 0.0 to 1.0, as defined in the schema descriptions. Null means 0.0. Never raise confidence because the arithmetic fits.
""".strip()


# ================================================================
# Create the Vertex AI client
# ================================================================

_client: anthropic.AnthropicVertex | None = None


def get_client() -> anthropic.AnthropicVertex:
    """
    Create the Vertex AI client once and reuse it for every image.

    Login: no API key. It uses your Google login (Application Default
    Credentials). On your PC run once:

        gcloud auth application-default login

    Returns:
        The shared AnthropicVertex client.

    Raises:
        RuntimeError: If GCP_PROJECT_ID is not set.
    """

    global _client

    if not GCP_PROJECT_ID:
        raise RuntimeError(
            "GCP_PROJECT_ID is not set. Put GCP_PROJECT_ID=... "
            "(and optionally GCP_REGION=...) in reimbursement/.env."
        )

    if _client is None:
        _client = anthropic.AnthropicVertex(
            project_id=GCP_PROJECT_ID,
            region=GCP_REGION,
            timeout=TIMEOUT_SECONDS,
        )

    return _client


# ================================================================
# Token usage
# ================================================================
BASE_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")


def add_usage(total: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """
    Add every numeric field of `usage` into `total` (in place) and return it.

    Works with whatever fields are reported (nested detail dictionaries,
    ...), so new fields never need code changes. It can also accumulate
    usage across many images:

        batch_usage = {}
        for ...:
            result, usage = extract_receipts(...)
            add_usage(batch_usage, usage)
    """
    for key, value in usage.items():
        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value

        elif isinstance(value, dict):
            nested = total.setdefault(key, {})

            if isinstance(nested, dict):
                add_usage(nested, value)

    return total


# ================================================================
# Image and schema helpers
# ================================================================

def detect_media_type(data: bytes) -> str:
    """
    Return the image media type from the file's first bytes.

    The file extension is not trusted. Claude accepts JPEG, PNG, WebP
    and GIF (BMP is not supported).

    Raises:
        RuntimeError: If the image format is not supported.
    """

    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"

    raise RuntimeError(
        "Unsupported image format. Use JPEG, PNG, WebP or GIF."
    )


# Schema keywords the structured-output feature may reject.
# The value ranges stay in the prompt (confidence is 0.0 to 1.0).
UNSUPPORTED_SCHEMA_KEYS = {"minimum", "maximum", "$defs"}


def clean_schema(node: Any) -> Any:
    """
    Return a copy of the JSON schema without the keywords in
    UNSUPPORTED_SCHEMA_KEYS (the schema file itself is not changed).
    """

    if isinstance(node, dict):
        return {
            key: clean_schema(value)
            for key, value in node.items()
            if key not in UNSUPPORTED_SCHEMA_KEYS
        }

    if isinstance(node, list):
        return [clean_schema(item) for item in node]

    return node


# ================================================================
# Run Haiku
# ================================================================

def run_haiku(
    image_path: pathlib.Path,
    schema_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run Claude Haiku on an image and return the extracted JSON result.

    Args:
        image_path:
            Path to the input receipt image.

        schema_path:
            Path to the JSON Schema describing the expected output.

    Returns:
        A tuple:

            (
                result,
                usage
            )

        result:
            Extracted receipt data as a Python dictionary.

        usage:
            Token usage of this request, for example:

                {
                    "input_tokens": ...,          (includes cached tokens)
                    "cached_input_tokens": ...,
                    "output_tokens": ...,
                    "total_tokens": ...,
                    "elapsed_seconds": ...
                }

    Raises:
        FileNotFoundError:
            If the image or schema does not exist.

        RuntimeError:
            If the API call fails or does not produce valid JSON.
    """

    image_path = pathlib.Path(image_path)
    schema_path = pathlib.Path(schema_path)

    # ------------------------------------------------------------
    # Validate input
    # ------------------------------------------------------------

    if not image_path.is_file():
        raise FileNotFoundError(
            f"Image file not found: {image_path}"
        )

    if not schema_path.is_file():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}"
        )

    # ------------------------------------------------------------
    # Load image and schema
    # ------------------------------------------------------------

    image_bytes = image_path.read_bytes()
    media_type = detect_media_type(image_bytes)

    schema = clean_schema(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )

    # ------------------------------------------------------------
    # Build request
    # ------------------------------------------------------------

    request = {
        # Model
        "model": MODEL,

        "max_tokens": MAX_TOKENS,

        # Reasoning effort, and the JSON the answer must follow.
        # Thinking is adaptive and on by default for Haiku 5.5.
        # Do not add temperature/top_p/top_k: Haiku 5.5 rejects them.
        "output_config": {
            "effort": EFFORT,
            "format": {
                "type": "json_schema",
                "schema": schema,
            },
        },

        # Input image, then the prompt.
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(
                                image_bytes
                            ).decode("utf-8"),
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    }

    # ------------------------------------------------------------
    # Run Haiku
    # ------------------------------------------------------------
    start_time = time.perf_counter()

    try:
        response = get_client().messages.create(**request)

    except anthropic.APIStatusError as exc:
        raise RuntimeError(
            f"Vertex AI request failed (HTTP {exc.status_code}):\n"
            f"{exc.message}"
        ) from exc

    except anthropic.APIConnectionError as exc:
        raise RuntimeError(
            "Vertex AI could not be reached. Check the network, "
            "the project/region and your Google login."
        ) from exc

    # ------------------------------------------------------------
    # Handle incomplete answers
    # ------------------------------------------------------------

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None)

        raise RuntimeError(
            f"Haiku declined this request (category: {category})."
        )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "The answer was cut off at MAX_TOKENS. "
            "Increase MAX_TOKENS or lower EFFORT."
        )

    # ------------------------------------------------------------
    # Extract result from the response
    # ------------------------------------------------------------

    text = "".join(
        block.text
        for block in response.content
        if block.type == "text"
    ).strip()

    try:
        result = json.loads(text)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "The response was not valid JSON.\n"
            f"Response text:\n{text[:500]}"
        ) from exc

    # ------------------------------------------------------------
    # Make sure we received the expected JSON
    # ------------------------------------------------------------

    if not isinstance(result, dict) or not isinstance(
        result.get("receipts"), list
    ):
        raise RuntimeError(
            "The response JSON has no 'receipts' list.\n"
            f"Response text:\n{text[:500]}"
        )

    # ------------------------------------------------------------
    # Calculate token usage and its elapsed time
    # ------------------------------------------------------------
    usage: dict[str, Any] = dict.fromkeys(BASE_USAGE_KEYS, 0)

    api_usage = response.usage

    cache_read = getattr(api_usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(api_usage, "cache_creation_input_tokens", 0) or 0

    # Anthropic's input_tokens leaves cached tokens out. Add them back so
    # input_tokens means the same as in the Luna file (cached is part of input).
    usage["input_tokens"] = api_usage.input_tokens + cache_read + cache_write
    usage["cached_input_tokens"] = cache_read
    usage["output_tokens"] = api_usage.output_tokens

    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]

    # Total elapsed time, including image encoding and JSON parsing
    usage["elapsed_seconds"] = round(
        time.perf_counter() - start_time, 3
    )

    return result, usage

# ================================================================
# Consistency check and retry
# ================================================================

RETRIES = 1                  # extra Haiku runs when the result looks inconsistent (0 = never retry)
MIN_UNIT_PRICE = 1000        # fuel costs thousands of rupiah per liter; less means a misread separator
PRODUCT_MATH_TOLERANCE = 150 # rupiah allowed between quantity x unit_price and total_price (largest seen: 107)
TOTAL_MATH_TOLERANCE = 1     # rupiah allowed between sum(total_price) - discount and total


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def receipt_problems(receipts) -> list[str]:
    """
    Arithmetic and sanity checks on extracted receipts. Returns a list of problems (empty = looks fine).
    It cannot see wrong dates or names, only numbers that do not agree with each other.
    """
    if not isinstance(receipts, list) or not receipts:
        return ["no receipts found"]

    problems = []
    for r, receipt in enumerate(receipts):
        label = f"receipt {r}"
        if receipt.get("date") is None:
            problems.append(f"{label}: date is null")
        total, discount = _num(receipt.get("total")), _num(receipt.get("discount")) or 0
        if total is None:
            problems.append(f"{label}: total is null")

        products = receipt.get("products") or []
        if not products:
            problems.append(f"{label}: no products")
        prices = []
        for p, product in enumerate(products):
            where = f"{label} product {p}"
            q, u, tp = (_num(product.get(k)) for k in ("quantity", "unit_price", "total_price"))
            for key, value in (("quantity", q), ("unit_price", u), ("total_price", tp)):
                if value is None:
                    problems.append(f"{where}: {key} is null")
            prices.append(tp)
            if u is not None and u < MIN_UNIT_PRICE:
                problems.append(f"{where}: unit_price {u} is under {MIN_UNIT_PRICE}")
            if None not in (q, u, tp) and abs(q * u - tp) > PRODUCT_MATH_TOLERANCE:
                problems.append(f"{where}: quantity x unit_price = {q * u:,.0f} but total_price = {tp:,.0f}")

        if prices and None not in prices and total is not None:
            implied = sum(prices) - discount
            if abs(implied - total) > TOTAL_MATH_TOLERANCE:
                problems.append(f"{label}: sum of total_price - discount = {implied:,.0f} but total = {total:,.0f}")
    return problems

# ================================================================
# Public API
# ================================================================

def extract_receipts(
    image_path: str | pathlib.Path,
    schema_path: str | pathlib.Path = "gas_station_receipt.schema.json",
    retries: int = RETRIES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Extract all gas station receipts from an image.

    If the numbers of the result do not add up (see receipt_problems), Haiku is run again
    (up to `retries` times) and the result with fewer problems is kept; a tie keeps the first run.
    The returned usage adds up all runs and has an extra "retries" count.
    """

    image_path = pathlib.Path(image_path)
    schema_path = pathlib.Path(schema_path)

    result, usage = run_haiku(image_path, schema_path)
    problems = receipt_problems(result.get("receipts"))
    usage["retries"] = 0

    for _ in range(retries):
        if not problems:
            break

        print(f"  Inconsistent result ({len(problems)} problem(s)): {'; '.join(problems[:3])}. Running Haiku again.")
        try:
            new_result, new_usage = run_haiku(image_path, schema_path)
        except RuntimeError as exc:  # a failed retry must not lose the first result
            print(f"  Retry failed: {exc}")
            break

        add_usage(usage, new_usage)  # tokens and time of both runs
        usage["retries"] += 1

        new_problems = receipt_problems(new_result.get("receipts"))
        if len(new_problems) < len(problems):
            result, problems = new_result, new_problems

    return result, usage

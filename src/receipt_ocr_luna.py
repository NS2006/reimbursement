"""
Reusable gas-station receipt extraction using Codex CLI and GPT-6 Luna.

Main usage:

    result, usage = extract_receipts(
        image_path="images/1.jpg",
        schema_path="gas_station_receipt.schema.json",
    )

The function returns:

    result -> Python dict containing the extracted receipts
    usage  -> dict containing token usage information

No output JSON file is created automatically.
"""

from __future__ import annotations

import time
import json
import pathlib
import shutil
import subprocess
from typing import Any


# ================================================================
# Configuration
# ================================================================

MODEL = "gpt-6-luna"
EFFORT = "xhigh"


# ================================================================
# Prompt
# ================================================================

EXTRACTION_PROMPT = """
Extract every fuel-station receipt in the image as JSON matching the schema. Ignore other documents. Return JSON only.

RECEIPTS
- One entry per physical receipt, in reading order (top to bottom, then left to right). Never merge, skip or deduplicate receipts: receipts with identical values but different dates are separate entries. Several products on one receipt stay in that one entry.
- Use only printed evidence. Never invent, guess or back-solve a value. If a value is unreadable or unsupported use null with confidence 0 (discount uses 0).

FIELDS
- date: exactly as printed (same format, no time, never reformat).
- name: product name as printed (do not correct or expand).
- quantity: liters. Its separator is a decimal point: 32,389 and 32.389 both mean 32.389. Never a pump number, nozzle, ID or time.
- unit_price: GROSS price per liter before any discount or subsidy. Never the reduced customer price.
- total_price: GROSS product amount before discount: printed, or quantity x unit_price when both are printed. With no discount it equals the amount paid for that product.
- discount: total discount or subsidy actually applied to this transaction, as a positive number; 0 if none or not proven. Count only amounts printed in the transaction lines, or a printed per-unit subsidy x quantity. These are NOT discounts: footer promotions, subsidy or eligibility text, loyalty messages, tax lines, or a price difference nobody labels as a discount.
- total: final amount paid for the whole receipt (Total, Total Bayar, Jumlah). Not cash tendered (Tunai), change (Kembali), points or tax lines.

NUMBERS
- JSON numbers only, rupiah without currency symbol. In money, a . or , followed by exactly 3 digits is a thousands separator: 12.700 and 12,700 both mean 12700, and 646.180 means 646180. A separator followed by 2 digits (like ,00) is a decimal; drop it.
- Fuel unit prices are normally thousands of rupiah per liter, so a unit_price under 1000 (such as 12.7 or 20.63) almost always means a misread separator: re-inspect. Follow the printed digits, never scale by 1000 or change digits to fit arithmetic. If still ambiguous use null.
- Separator style can differ between receipts: infer it from the other amounts on the same receipt.

CHECKS
Before answering verify: quantity x unit_price is about total_price, and total_price summed over products minus discount is about total. Use a mismatch only to re-inspect misread digits. Never use it to overwrite clearly printed values or fill missing ones. Never copy total into total_price when a discount exists.

INSPECTION
If image tools exist, crop and enlarge ambiguous areas (separators, faint digits, dates, quantities) before deciding; enhanced views are aids, not evidence. Never claim an inspection you did not do.

CONFIDENCE
Per field, 0.0 to 1.0, as defined in the schema descriptions. Null means 0.0. Never raise confidence because the arithmetic fits.
""".strip()


# ================================================================
# Find Codex
# ================================================================

def find_codex() -> str:
    """
    Find the Codex CLI executable.

    Returns:
        Path to the Codex executable.

    Raises:
        RuntimeError: If Codex cannot be found.
    """

    codex_executable = shutil.which("codex")

    if codex_executable is None:
        codex_executable = shutil.which("codex.cmd")

    if codex_executable is None:
        raise RuntimeError(
            "Codex CLI was not found in PATH. "
            "Make sure Codex is installed and available from the terminal."
        )

    return codex_executable


# ================================================================
# Token usage
# ================================================================
BASE_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")


def add_usage(total: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """
    Add every numeric field of `usage` into `total` (in place) and return it.

    Works with whatever fields Codex reports (reasoning_output_tokens,
    nested detail dictionaries, ...), so new fields never need code
    changes.
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
# Run Codex
# ================================================================

def run_codex(
    image_path: pathlib.Path,
    schema_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run Codex on an image and return the extracted JSON result.

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
            Token usage summed over all turns, with every numeric field
            Codex reported, for example:

                {
                    "input_tokens": ...,
                    "cached_input_tokens": ...,
                    "output_tokens": ...,
                    "reasoning_output_tokens": ...,   (if reported)
                    "total_tokens": ...,
                    "elapsed_seconds": ...
                }

    Raises:
        FileNotFoundError:
            If the image or schema does not exist.

        RuntimeError:
            If Codex fails or does not produce valid JSON.
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
    # Find Codex
    # ------------------------------------------------------------

    codex_executable = find_codex()

    # ------------------------------------------------------------
    # Build command
    # ------------------------------------------------------------

    command = [
        codex_executable,
        "exec",
        "--skip-git-repo-check",

        # Model
        "--model",
        MODEL,

        # Reasoning effort, set through a config override
        # (codex exec has no --effort flag).
        "-c",
        f"model_reasoning_effort={EFFORT}",

        # Do not persist the Codex session.
        "--ephemeral",

        # Return machine-readable JSONL events.
        "--json",

        # Allow Python/image processing inside the workspace.
        "--sandbox",
        "workspace-write",

        # Input image.
        "-i",
        str(image_path),

        # Output schema.
        "--output-schema",
        str(schema_path),

        # Prompt.
        EXTRACTION_PROMPT,
    ]

    # ------------------------------------------------------------
    # Run Codex
    # ------------------------------------------------------------
    start_time = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    except FileNotFoundError as exc:
        raise RuntimeError(
            "Codex CLI could not be executed."
        ) from exc

    except KeyboardInterrupt as exc:
        raise RuntimeError(
            "Codex execution was interrupted."
        ) from exc

    # ------------------------------------------------------------
    # Handle Codex errors
    # ------------------------------------------------------------

    if completed.returncode != 0:
        error_message = completed.stderr.strip()

        if not error_message:
            error_message = (
                f"Codex exited with return code "
                f"{completed.returncode}."
            )

        raise RuntimeError(
            f"Codex execution failed:\n{error_message}"
        )

    # ------------------------------------------------------------
    # Parse JSON event stream
    # ------------------------------------------------------------

    usage_records: list[dict[str, int]] = []
    output_events: list[dict[str, Any]] = []

    for line in completed.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            event = json.loads(line)

        except json.JSONDecodeError:
            # Ignore non-JSON lines.
            continue

        output_events.append(event)

        if event.get("type") == "turn.completed":
            usage = event.get("usage")

            if usage:
                usage_records.append(usage)

    # ------------------------------------------------------------
    # Extract result from Codex events
    # ------------------------------------------------------------

    result: dict[str, Any] | None = None

    # Codex may provide the final response through an event.
    # Look for the final assistant message.
    for event in reversed(output_events):

        if event.get("type") != "item.completed":
            continue

        item = event.get("item")

        if not isinstance(item, dict):
            continue

        if item.get("type") not in {
            "agent_message",
            "message",
        }:
            continue

        text = item.get("text")

        if not isinstance(text, str):
            continue

        text = text.strip()

        if not text:
            continue

        try:
            parsed = json.loads(text)

        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            result = parsed
            break

    # ------------------------------------------------------------
    # Fallback:
    # Try JSON-looking content from the event stream.
    # ------------------------------------------------------------

    if result is None:

        for event in reversed(output_events):

            # Common response fields that may contain the
            # model's final JSON.
            candidates = [
                event.get("text"),
                event.get("output_text"),
                event.get("content"),
            ]

            for candidate in candidates:

                if not isinstance(candidate, str):
                    continue

                candidate = candidate.strip()

                if not candidate:
                    continue

                try:
                    parsed = json.loads(candidate)

                except json.JSONDecodeError:
                    continue

                if isinstance(parsed, dict):
                    result = parsed
                    break

            if result is not None:
                break

    # ------------------------------------------------------------
    # Make sure we received JSON
    # ------------------------------------------------------------

    if result is None:
        stderr = completed.stderr.strip()

        raise RuntimeError(
            "Codex completed successfully, but no valid JSON "
            "result could be extracted from its response.\n"
            f"Codex stderr:\n{stderr}"
        )

    # ------------------------------------------------------------
    # Calculate token usage and its elapsed time
    # ------------------------------------------------------------
    usage: dict[str, Any] = dict.fromkeys(BASE_USAGE_KEYS, 0)

    # Sum every numeric field of every turn (all fields Codex reports).
    for record in usage_records:
        add_usage(usage, record)

    # Derived only when Codex does not report it:
    # cached tokens are part of input, reasoning tokens part of output.
    usage.setdefault(
        "total_tokens",
        usage["input_tokens"] + usage["output_tokens"],
    )

    # Total elapsed time, including Codex startup and JSON parsing
    usage["elapsed_seconds"] = round(
        time.perf_counter() - start_time, 3
    )

    return result, usage

# ================================================================
# Consistency check and retry
# ================================================================

RETRIES = 1                  # extra Codex runs when the result looks inconsistent (0 = never retry)
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

    If the numbers of the result do not add up (see receipt_problems), Codex is run again
    (up to `retries` times) and the result with fewer problems is kept; a tie keeps the first run.
    The returned usage adds up all runs and has an extra "retries" count.
    """

    image_path = pathlib.Path(image_path)
    schema_path = pathlib.Path(schema_path)

    result, usage = run_codex(image_path, schema_path)
    problems = receipt_problems(result.get("receipts"))
    usage["retries"] = 0

    for _ in range(retries):
        if not problems:
            break

        print(f"  Inconsistent result ({len(problems)} problem(s)): {'; '.join(problems[:3])}. Running Codex again.")
        try:
            new_result, new_usage = run_codex(image_path, schema_path)
        except RuntimeError as exc:  # a failed retry must not lose the first result
            print(f"  Retry failed: {exc}")
            break

        add_usage(usage, new_usage)  # tokens and time of both runs
        usage["retries"] += 1

        new_problems = receipt_problems(new_result.get("receipts"))
        if len(new_problems) < len(problems):
            result, problems = new_result, new_problems

    return result, usage
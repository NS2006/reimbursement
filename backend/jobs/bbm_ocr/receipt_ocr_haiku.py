"""
Reusable gas-station receipt extraction using Claude Code CLI and Claude Haiku 5.5.

Main usage:

    result, usage = extract_receipts(
        image_path="images/1.jpg",
        schema_path="gas_station_receipt.schema.json",
    )

The function returns:

    result -> Python dict containing the extracted receipts
    usage  -> dict containing token usage information

No output JSON file is created automatically.

Needs the Claude Code CLI ("claude") installed, and logged in (claude auth login) or given an API key
(ANTHROPIC_API_KEY, as deployed; see claude_environment).
Public functions: extract_receipts, add_usage, BASE_USAGE_KEYS, receipt_problems
"""

from __future__ import annotations

import contextlib
import time
import json
import os
import re
import pathlib
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import Any

from backend.jobs.bbm_ocr.receipt_config import MAX_PDF_BYTES, MAX_PDF_PAGES
from backend.jobs.bbm_ocr.receipt_utils import is_pdf, pdf_page_count


# ================================================================
# Configuration
# ================================================================

MODEL = "claude-haiku-5-5"
EFFORT = "max"           # low, medium, high, xhigh, max (Haiku 5.5 default: medium)
TIMEOUT_SECONDS = 300       # one Claude run per image; a hung run fails instead of blocking the batch
PDF_PAGE_SECONDS = 120      # extra time for each PDF page after the first


# ================================================================
# Prompt
# ================================================================

EXTRACTION_PROMPT = """
Extract every fuel-station receipt in the file as JSON matching the schema. Ignore other documents. Return JSON only.

FILE
The receipt file (a photo or a PDF) is the file named in the user message. Open it with the Read tool before answering. It is the only evidence.
- A PDF: read the whole file in one Read call, without the pages parameter. Look at every page; a page can show one receipt or several.

RECEIPTS
- One entry per physical receipt, in reading order (page by page; on a page top to bottom, then left to right). Never merge, skip or deduplicate receipts: receipts with identical values but different dates are separate entries. Several products on one receipt stay in that one entry.
- Use only printed evidence. Never invent, guess or back-solve a value. If a value is unreadable or unsupported use null with confidence 0 (discount uses 0).

FIELDS
- date: the transaction date written as DD-MM-YYYY with leading zeros, no time: 26/05/2026, 26.05.26, 26-Mei-2026 and Kamis, 26 Mei 2026 all become 26-05-2026.
  Indonesian receipts print the day first: keep that order, never swap day and month. Only a 4-digit year printed first is year-month-day: 2026-05-08 becomes 08-05-2026.
  A 2-digit year means 20YY. Month names can be Indonesian or English (Mei = May, Agu/Agt = Aug, Okt = Oct, Des = Dec).
  If the day, month or year is unreadable or not printed, use null.
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

CONFIDENCE
Per field, 0.0 to 1.0, as defined in the schema descriptions. Null means 0.0. Never raise confidence because the arithmetic fits.
""".strip()


# ================================================================
# Errors
# ================================================================

class ClaudeUnavailable(RuntimeError):
    """Claude could not run at all (the CLI is missing, not logged in, a usage limit, a service error): not a problem
    of the file, so the OCR worker waits and tries again instead of giving up on the file."""


class ClaudeInterrupted(RuntimeError):
    """The run was stopped with Ctrl+C."""


# ================================================================
# Find Claude
# ================================================================

def find_claude() -> str:
    """
    Find the Claude Code CLI executable.

    On Windows, npm installs a claude.cmd wrapper. Running it goes through
    cmd.exe, which can break long arguments with quotes or line breaks
    (the JSON schema and the prompt), so the claude.exe it wraps is used instead.

    Returns:
        Path to the Claude executable.

    Raises:
        RuntimeError: If Claude cannot be found.
    """

    claude_executable = shutil.which("claude")

    if claude_executable is None:
        claude_executable = shutil.which("claude.cmd")

    if claude_executable is None:
        raise ClaudeUnavailable(
            "Claude Code CLI was not found in PATH. "
            "Make sure Claude Code is installed and available from the terminal."
        )

    wrapper = pathlib.Path(claude_executable)

    if wrapper.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        native = wrapper.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"

        if native.is_file():
            claude_executable = str(native)

    return claude_executable


# ================================================================
# Environment: API key or login, and no secrets of the app
# ================================================================

# Environment variables Claude never gets: the app's own settings and secrets (DB_PASSWORD and the other DB_*,
# cloud credentials, other keys and tokens). It only needs to sign in and reach the internet.
SECRET_VARIABLE = re.compile(r"^DB_|PASSWORD|SECRET|TOKEN|CREDENTIAL|_KEY$", re.IGNORECASE)
CLAUDE_SIGN_IN = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"}


@contextlib.contextmanager
def claude_environment():
    """
    The environment Claude runs in, for one run: the worker's, without the app's secrets (SECRET_VARIABLE).

    ANTHROPIC_API_KEY set (deployed: the organization's API key): Claude also gets an empty config folder of its own,
    so the key is what it uses. With its usual folder, a `claude auth login` on the same machine wins over the key.

    Not set (or empty): Claude's usual config folder, so the logged-in account is used.
    """
    env = {
        name: value for name, value in os.environ.items()
        if name.upper() in CLAUDE_SIGN_IN or not SECRET_VARIABLE.search(name)
    }

    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        yield env
        return

    with tempfile.TemporaryDirectory(prefix="claude-config-", ignore_cleanup_errors=True) as config:
        yield {**env, "CLAUDE_CONFIG_DIR": config}


# ================================================================
# Token usage
# ================================================================
BASE_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")


def add_usage(total: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """
    Add every numeric field of `usage` into `total` (in place) and return it.

    Works with whatever fields Claude reports (thinking_tokens,
    cost_usd, nested detail dictionaries, ...), so new fields never need code
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
# Run Claude
# ================================================================

def run_claude(
    image_path: pathlib.Path,
    schema_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run Claude on an image or a PDF and return the extracted JSON result.

    Args:
        image_path:
            Path to the input receipt image or PDF.

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
            Token usage summed over all turns, for example:

                {
                    "input_tokens": ...,                  (all input, cached included)
                    "cached_input_tokens": ...,           (input read from cache)
                    "cache_creation_input_tokens": ...,   (input written to cache)
                    "output_tokens": ...,
                    "thinking_tokens": ...,               (if reported)
                    "cost_usd": ...,                      (Claude Code's estimate at list price)
                    "num_turns": ...,
                    "total_tokens": ...,
                    "elapsed_seconds": ...
                }

    Raises:
        FileNotFoundError:
            If the image or schema does not exist.

        ValueError:
            If a PDF is too large or has too many pages for Claude to read.

        ClaudeUnavailable (a RuntimeError):
            If Claude cannot run or its run fails.

        RuntimeError:
            If Claude does not finish in time or does not produce valid JSON.
    """

    image_path = pathlib.Path(image_path).resolve()
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
    # A PDF is read whole: check it fits (see MAX_PDF_PAGES)
    # ------------------------------------------------------------

    kind = "image"
    timeout = TIMEOUT_SECONDS

    if is_pdf(image_path):
        kind = "PDF"
        size = image_path.stat().st_size

        if size > MAX_PDF_BYTES:
            raise ValueError(
                f"The PDF is {size / 1024 / 1024:.1f} MB; Claude reads at most "
                f"{MAX_PDF_BYTES // 1024 // 1024} MB."
            )

        pages = pdf_page_count(image_path)

        if pages is not None and pages > MAX_PDF_PAGES:
            raise ValueError(
                f"The PDF has {pages} pages; Claude reads at most {MAX_PDF_PAGES} in one run."
            )

        timeout += PDF_PAGE_SECONDS * ((pages or MAX_PDF_PAGES) - 1)

    # ------------------------------------------------------------
    # Find Claude
    # ------------------------------------------------------------

    claude_executable = find_claude()

    # ------------------------------------------------------------
    # Build command
    # ------------------------------------------------------------

    # --json-schema takes the schema itself, not a file path.
    schema = json.dumps(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )

    command = [
        claude_executable,
        "-p",

        # Model
        "--model",
        MODEL,

        # Reasoning effort
        "--effort",
        EFFORT,

        # Ignore personal settings, CLAUDE.md, plugins, hooks and MCP
        # servers, so every run sees the same small context.
        "--safe-mode",

        # Replace Claude Code's default (coding) system prompt.
        "--system-prompt",
        EXTRACTION_PROMPT,

        # Only the Read tool, which is how Claude opens the image. No allow rule for it: Claude Code lets it read
        # in its working folder (the run's own folder, which holds only the receipt file), and anywhere else needs a
        # permission, which dontAsk refuses. So text in a receipt can't make it read .env or credentials.
        "--tools",
        "Read",

        # Deny anything else instead of waiting for an answer.
        "--permission-mode",
        "dontAsk",

        # Do not persist the Claude session.
        "--no-session-persistence",

        # Return one machine-readable JSON result.
        "--output-format",
        "json",

        # Output schema.
        "--json-schema",
        schema,
    ]

    # Prompt, sent through stdin.
    prompt = f"Extract the receipts from this {kind} file: {image_path}"

    # ------------------------------------------------------------
    # Run Claude
    # ------------------------------------------------------------
    start_time = time.perf_counter()

    try:
        with claude_environment() as env:   # without the app's secrets; the API key when one is set, else the login
            completed = subprocess.run(
                command,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=image_path.parent,   # the image folder is Claude's working folder, so Read may open it
                env=env,
                timeout=timeout,
            )

    except FileNotFoundError as exc:
        raise ClaudeUnavailable(
            "Claude Code CLI could not be executed."
        ) from exc

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Claude did not finish within {timeout} seconds."
        ) from exc

    except KeyboardInterrupt as exc:
        raise ClaudeInterrupted(
            "Claude execution was interrupted."
        ) from exc

    # ------------------------------------------------------------
    # Parse JSON result
    # ------------------------------------------------------------

    try:
        response = json.loads(completed.stdout)

    except json.JSONDecodeError:
        response = None

    # ------------------------------------------------------------
    # Handle Claude errors
    # ------------------------------------------------------------

    if (
        completed.returncode != 0
        or not isinstance(response, dict)
        or response.get("is_error")
    ):
        error_message = completed.stderr.strip()

        if isinstance(response, dict) and response.get("result"):
            error_message = f"{response.get('subtype')}: {response.get('result')}"

        if not error_message:
            error_message = (
                f"Claude exited with return code "
                f"{completed.returncode}."
            )

        raise ClaudeUnavailable(
            f"Claude execution failed:\n{error_message}"
        )

    # ------------------------------------------------------------
    # Extract result
    # ------------------------------------------------------------

    result: dict[str, Any] | None = None

    # --json-schema puts the validated JSON in "structured_output".
    structured = response.get("structured_output")

    if isinstance(structured, dict):
        result = structured

    # ------------------------------------------------------------
    # Fallback:
    # Try the final text answer.
    # ------------------------------------------------------------

    if result is None:
        text = response.get("result")

        if isinstance(text, str) and text.strip():

            try:
                parsed = json.loads(text.strip())

            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, dict):
                result = parsed

    # ------------------------------------------------------------
    # Make sure we received JSON
    # ------------------------------------------------------------

    if result is None:
        stderr = completed.stderr.strip()

        raise RuntimeError(
            "Claude completed successfully, but no valid JSON "
            "result could be extracted from its response.\n"
            f"Claude stderr:\n{stderr}"
        )

    # ------------------------------------------------------------
    # Calculate token usage and its elapsed time
    # ------------------------------------------------------------
    usage: dict[str, Any] = dict.fromkeys(BASE_USAGE_KEYS, 0)

    # "modelUsage" is summed over every turn (one entry per model used).
    for record in (response.get("modelUsage") or {}).values():
        cache_read = record.get("cacheReadInputTokens", 0)
        cache_write = record.get("cacheCreationInputTokens", 0)

        add_usage(usage, {
            # Cached tokens are counted as part of the input.
            "input_tokens": record.get("inputTokens", 0) + cache_read + cache_write,
            "cached_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "output_tokens": record.get("outputTokens", 0),
            "thinking_tokens": record.get("thinkingTokens", 0),
        })

    usage["cost_usd"] = response.get("total_cost_usd", 0)
    usage["num_turns"] = response.get("num_turns", 0)

    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]

    # Total elapsed time, including Claude startup and JSON parsing
    usage["elapsed_seconds"] = round(
        time.perf_counter() - start_time, 3
    )

    return result, usage

# ================================================================
# Consistency check and retry
# ================================================================

RETRIES = 0                  # extra Claude runs when the result looks inconsistent (0 = never retry)
MIN_UNIT_PRICE = 1000        # fuel costs thousands of rupiah per liter; less means a misread separator
PRODUCT_MATH_TOLERANCE = 150 # rupiah allowed between quantity x unit_price and total_price (largest seen: 107)
TOTAL_MATH_TOLERANCE = 1     # rupiah allowed between sum(total_price) - discount and total
DATE_FORMAT = re.compile(r"\d{2}-\d{2}-\d{4}")   # DD-MM-YYYY, as in the submitted data


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _is_date(value):
    if not isinstance(value, str) or not DATE_FORMAT.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%d-%m-%Y")
    except ValueError:
        return False
    return True


def receipt_problems(receipts) -> list[str]:
    """
    Arithmetic and sanity checks on extracted receipts. Returns a list of problems (empty = looks fine).
    It cannot see wrong dates or names, only numbers that do not agree with each other and dates not written as DD-MM-YYYY.
    """
    if not isinstance(receipts, list) or not receipts:
        return ["no receipts found"]

    problems = []
    for r, receipt in enumerate(receipts):
        label = f"receipt {r}"
        date = receipt.get("date")
        if date is None:
            problems.append(f"{label}: date is null")
        elif not _is_date(date):
            problems.append(f"{label}: date {date!r} is not a DD-MM-YYYY date")
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
    Extract all gas station receipts from an image or a PDF.

    If the numbers of the result do not add up (see receipt_problems), Claude is run again
    (up to `retries` times) and the result with fewer problems is kept; a tie keeps the first run.
    The returned usage adds up all runs and has an extra "retries" count.
    """

    image_path = pathlib.Path(image_path)
    schema_path = pathlib.Path(schema_path)

    result, usage = run_claude(image_path, schema_path)
    problems = receipt_problems(result.get("receipts"))
    usage["retries"] = 0

    for _ in range(retries):
        if not problems:
            break

        print(f"  Inconsistent result ({len(problems)} problem(s)): {'; '.join(problems[:3])}. Running Claude again.")
        try:
            new_result, new_usage = run_claude(image_path, schema_path)
        except RuntimeError as exc:  # a failed retry must not lose the first result
            print(f"  Retry failed: {exc}")
            break

        add_usage(usage, new_usage)  # tokens and time of both runs
        usage["retries"] += 1

        new_problems = receipt_problems(new_result.get("receipts"))
        if len(new_problems) < len(problems):
            result, problems = new_result, new_problems

    return result, usage

"""
Compare the saved OCR runs: accuracy, token usage and time.

Runs are grouped per model in a results_<model> folder next to this file, one folder per run
named evaluation_report_<effort>_<retries>:

    results_haiku/evaluation_report_max_0      Haiku, effort "max", 0 retries
    results_opus/evaluation_report_xhigh_0     Opus, effort "xhigh", 0 retries

Each run folder holds what extract and evaluate wrote for that run:

    batch_results_usage.json          token usage and time (total and per image)
    evaluation_report_<mode>.json     accuracy against the ground truth

Run:

    py backend/jobs/bbm_ocr/comparison.py

Prints, with the rich library (one row per run, so many runs stay readable):
    1. All runs: accuracy, tokens and time
    2. All runs: accuracy per field
    3. All runs: every mistake and which runs made it
    4. Best configuration of each model (by accuracy): accuracy, tokens and time
    5. Best configuration of each model: accuracy per field
    6. The mistakes of those best configurations
and saves a plain-text copy to comparison.txt next to this file.
"""

import json
from collections import Counter
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "comparison.txt"

MODEL_PREFIX = "results_"    # results_<model> holds the runs of one model

RUN_PREFIX = "evaluation_report_"
NUMERIC_MODE = "tolerance"   # which evaluation report to read when a run has several
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"]
FIELDS = ["date", "discount", "total", "name", "quantity", "unit_price", "total_price"]

# Table 3 hides mistakes that only one run made (they are counted under the table instead).
# Set to True to list every mistake.
SHOW_SINGLE_RUN_MISTAKES = False


# ================================================================
# Load runs
# ================================================================

def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run_name(folder):
    """
    results_haiku/evaluation_report_max_1 -> ("haiku", "max", 1)
    A run name that does not follow the pattern is kept as is.
    """
    model = folder.parent.name[len(MODEL_PREFIX):]
    name = folder.name[len(RUN_PREFIX):]
    effort, _, retries = name.rpartition("_")
    if effort and retries.isdigit():
        return model, effort, int(retries)
    return model, name, None


def _find_report(folder):
    preferred = folder / f"evaluation_report_{NUMERIC_MODE}.json"
    if preferred.is_file():
        return preferred
    return next(iter(sorted(folder.glob("evaluation_report_*.json"))), None)


def load_run(folder, console):
    """Read one run folder. Returns None (and says why) when a file is missing."""
    report_path = _find_report(folder)
    usage_path = folder / "batch_results_usage.json"

    if report_path is None or not usage_path.is_file():
        missing = "evaluation report" if report_path is None else usage_path.name
        console.print(f"[yellow]Skipping {folder.parent.name}/{folder.name}: {missing} not found.[/yellow]")
        return None

    report, usage = _load(report_path), _load(usage_path)
    total = usage.get("total", {})
    n_images = len(usage.get("per_image", {})) or report.get("n_images") or 1
    errors = report.get("error_summary", {})
    model, effort, retries = _run_name(folder)

    input_tokens = total.get("input_tokens")
    cached = total.get("cached_input_tokens")

    metrics = {
        # Accuracy
        "field_accuracy": report.get("overall_field_accuracy"),
        "receipt_exact": report.get("receipt_exact_accuracy"),
        "errors": errors.get("total"),
        "images_with_errors": errors.get("images_with_errors"),
        # Tokens
        "total_tokens": total.get("total_tokens"),
        "input_tokens": input_tokens,
        "cache_share": cached / input_tokens if cached is not None and input_tokens else None,
        "output_tokens": total.get("output_tokens"),
        "thinking_tokens": total.get("thinking_tokens"),
        "tokens_per_image": total["total_tokens"] / n_images if "total_tokens" in total else None,
        # Time
        "total_time": total.get("elapsed_seconds"),
        "retries": total.get("retries"),
    }
    for field in FIELDS:
        metrics[f"field_{field}"] = report.get("field_accuracy", {}).get(field)

    return {"name": folder.name[len(RUN_PREFIX):], "model": model, "effort": effort, "retries": retries,
            "images": n_images, "metrics": metrics, "errors": report.get("errors", [])}


def load_runs(console, base_dir=BASE_DIR):
    folders = [p for p in base_dir.glob(f"{MODEL_PREFIX}*/{RUN_PREFIX}*") if p.is_dir()]
    runs = [run for run in (load_run(folder, console) for folder in folders) if run]

    def order(run):
        effort = run["effort"]
        rank = EFFORT_ORDER.index(effort) if effort in EFFORT_ORDER else len(EFFORT_ORDER)
        return run["model"], rank, effort, run["retries"] if run["retries"] is not None else -1

    return sorted(runs, key=order)


def best_per_model(runs):
    """
    The most accurate run of each model. Ties go to more fully correct receipts,
    then fewer errors, fewer tokens and less time.
    """
    def rank(run):
        m = run["metrics"]
        return (-(m["field_accuracy"] or 0), -(m["receipt_exact"] or 0), m["errors"] or 0,
                m["total_tokens"] or 0, m["total_time"] or 0)

    best = {}
    for run in runs:
        if run["model"] not in best or rank(run) < rank(best[run["model"]]):
            best[run["model"]] = run
    return list(best.values())


# ================================================================
# Format
# ================================================================

def _pct(v):
    return f"{v * 100:.2f}%"


def _int(v):
    return f"{v:,.0f}"


def _seconds(v):
    minutes, seconds = divmod(round(v), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{v:.1f}s"


def _config(run):
    """effort-retries, e.g. max-0."""
    return run["effort"] if run["retries"] is None else f"{run['effort']}-{run['retries']}"


# (key, header, formatter, better): better is "high", "low" or None (shown, never coloured)
SUMMARY_COLUMNS = [
    ("field_accuracy", "Field\naccuracy", _pct, "high"),
    ("receipt_exact", "Receipts\ncorrect", _pct, "high"),
    ("errors", "Errors", _int, "low"),
    ("images_with_errors", "Images\nw/ errors", _int, "low"),
    ("total_tokens", "Total\ntokens", _int, "low"),
    ("output_tokens", "Output\ntokens", _int, "low"),
    ("thinking_tokens", "of which\nthinking", _int, None),
    ("cache_share", "Input\ncached", _pct, None),
    ("tokens_per_image", "Tokens\n/ image", _int, "low"),
    ("total_time", "Total\ntime", _seconds, "low"),
    ("retries", "Retries\ndone", _int, None),
]

FIELD_COLUMNS = [(f"field_{field}", field.replace("_", "\n"), _pct, "high") for field in FIELDS]


def _cell(value, fmt, best, worst):
    """Best value of the column in bold green with a *, worst in red, the rest plain."""
    if value is None:
        return Text("-  ", style="dim")
    text = fmt(value)
    if value == best:
        return Text(text + " *", style="bold green")
    if value == worst:
        return Text(text + "  ", style="red")
    return Text(text + "  ")


def _best_worst(values, better):
    known = [v for v in values if v is not None]
    if not better or len(known) < 2 or len(set(known)) == 1:
        return None, None
    high, low = max(known), min(known)
    return (high, low) if better == "high" else (low, high)


def _table(title, caption=None):
    return Table(title=title, title_style="bold", caption=caption, box=box.ROUNDED,
                 header_style="bold", title_justify="left", caption_justify="left")


def metric_table(title, runs, columns, best_config=False, caption=None):
    """
    One row per run, one column per metric; best value of each column green, worst red.
    best_config=True: one row per model with its best configuration (no grouping).
    """
    table = _table(title, caption or "[bold green]* best[/] / [red]worst[/] in the column.")
    table.add_column("Model", style="bold cyan", no_wrap=True)
    if best_config:
        table.add_column("Best config", no_wrap=True)
    else:
        table.add_column("Effort", no_wrap=True)
        table.add_column("Retries", justify="right", no_wrap=True)
    for _, header, _, _ in columns:
        table.add_column(header, justify="right", no_wrap=True)

    limits = {key: _best_worst([run["metrics"].get(key) for run in runs], better)
              for key, _, _, better in columns}

    previous_model = None
    for run in runs:
        new_model = run["model"] != previous_model
        if new_model and previous_model is not None and not best_config:
            table.add_section()
        previous_model = run["model"]

        if best_config:
            ids = [run["model"], _config(run)]
        else:
            retries = "-" if run["retries"] is None else str(run["retries"])
            ids = [run["model"] if new_model else "", run["effort"], retries]
        cells = [_cell(run["metrics"].get(key), fmt, *limits[key]) for key, _, fmt, _ in columns]
        table.add_row(*ids, *cells)
    return table


# ================================================================
# Error comparison
# ================================================================

def _error_key(error):
    """The same mistake in different runs: same image, receipt, product and field."""
    receipt = error.get("gt_receipt_index")
    if receipt is None:                       # a receipt that is not in the ground truth
        receipt = f"pred {error.get('pred_receipt_index')}"
    return (str(error.get("image")), error.get("type"), str(receipt),
            error.get("product_index"), error.get("field"))


def _image_order(image):
    return (0, int(image), "") if image.isdigit() else (1, 0, image)


def _value(v):
    """A value as the report holds it: null, a whole receipt, a number or text."""
    if v is None:
        return "null"
    if isinstance(v, dict):                   # extra or missing receipt: show its total
        total = v.get("total")
        return f"total {total:,.0f}" if isinstance(total, (int, float)) else "receipt"
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return f"{v:,.0f}"
    return str(v)


def _where(error):
    receipt = error.get("gt_receipt_index")
    where = f"receipt {receipt + 1}" if receipt is not None else "receipt not in GT"
    if error.get("product_index") is not None:
        where += f" / {error.get('product_name') or 'product ' + str(error['product_index'] + 1)}"
    return where


def _what(error):
    if error.get("type") == "field_mismatch":
        return error.get("field") or "-"
    return (error.get("type") or "-").replace("_", " ")


def collect_errors(runs):
    """
    Returns (keys, first_seen, per_run): every distinct mistake (most common first), one
    example of each, and per run a dict of the mistakes it made.
    """
    first_seen, per_run = {}, []
    for run in runs:
        errors = {}
        for error in run["errors"]:
            key = _error_key(error)
            errors[key] = error
            first_seen.setdefault(key, error)
        per_run.append(errors)

    def order(key):
        image, _, receipt, product, field = key
        wrong = sum(key in errors for errors in per_run)
        return -wrong, _image_order(image), receipt, -1 if product is None else product, field or ""

    return sorted(first_seen, key=order), first_seen, per_run


def _wrong_runs(key, runs, per_run):
    """Which runs made a mistake, grouped per model: "haiku: low-0, max-0 | opus: all"."""
    by_model = {}
    for run, errors in zip(runs, per_run):
        by_model.setdefault(run["model"], []).append((run, key in errors))

    parts = []
    for model, results in by_model.items():
        wrong = [_config(run) for run, is_wrong in results if is_wrong]
        if not wrong:
            continue
        parts.append(f"{model}: {'all' if len(wrong) == len(results) else ', '.join(wrong)}")
    return " | ".join(parts)


def error_overview_table(runs):
    """
    All runs: one row per mistake, with how many runs made it, what they read and which
    runs they were. Mistakes every run makes come first.
    """
    keys, first_seen, per_run = collect_errors(runs)
    if not keys:
        return None

    caption = ("Read = the wrong values and how many runs read them.  "
               "Wrong in every run first, then wrong in only some runs.")
    if not SHOW_SINGLE_RUN_MISTAKES and len(runs) > 2:
        single = [key for key in keys if sum(key in errors for errors in per_run) == 1]
        keys = [key for key in keys if key not in single]
        if single:
            owners = Counter(f"{run['model']} {_config(run)}"
                             for key in single for run, errors in zip(runs, per_run) if key in errors)
            caption += (f"\n{len(single)} mistakes made by only one run are hidden ("
                        + ", ".join(f"{owner}: {n}" for owner, n in owners.most_common())
                        + "). Set SHOW_SINGLE_RUN_MISTAKES = True to list them.")

    table = _table("3. All runs: mistakes made by more than one run"
                   if not SHOW_SINGLE_RUN_MISTAKES and len(runs) > 2 else "3. All runs: mistakes", caption)
    table.add_column("Image", style="cyan", justify="right", no_wrap=True)
    table.add_column("Where", no_wrap=True)
    table.add_column("Field", no_wrap=True)
    table.add_column("Expected", no_wrap=True)
    table.add_column("Wrong in", justify="right", no_wrap=True)
    table.add_column("Read", style="red", max_width=28, overflow="fold")
    table.add_column("Runs that got it wrong", max_width=60, overflow="fold")

    previous_group = None
    for key in keys:
        error = first_seen[key]
        count = sum(key in errors for errors in per_run)
        group = count == len(runs)
        if previous_group is not None and group != previous_group:
            table.add_section()
        previous_group = group

        readings = Counter(_value(errors[key].get("pred")) for errors in per_run if key in errors)
        read = ", ".join(f"{value} ×{n}" if n > 1 else value for value, n in readings.most_common())
        runs_text = "all runs" if group else _wrong_runs(key, runs, per_run)
        table.add_row(key[0], _where(error), _what(error), _value(error.get("gt")),
                      Text(f"{count}/{len(runs)}", style="bold red" if group else "yellow"),
                      read, runs_text)
    return table


def error_matrix_table(title, runs):
    """
    Few runs side by side: one row per mistake, one column per run with what that run read
    (red) or "ok" (green).
    """
    keys, first_seen, per_run = collect_errors(runs)
    if not keys:
        return None

    table = _table(title, "[red]red[/] = what the run read, [green]ok[/] = correct.")
    table.add_column("Image", style="cyan", justify="right", no_wrap=True)
    table.add_column("Where", no_wrap=True)
    table.add_column("Field", no_wrap=True)
    table.add_column("Expected", no_wrap=True)
    for run in runs:
        table.add_column(f"[bold cyan]{run['model']}[/bold cyan]\n[dim]{_config(run)}[/dim]",
                         justify="right", no_wrap=True)

    for key in keys:
        error = first_seen[key]
        cells = [Text(_value(errors[key].get("pred")), style="red") if key in errors else Text("ok", style="green")
                 for errors in per_run]
        table.add_row(key[0], _where(error), _what(error), _value(error.get("gt")), *cells)
    return table


# ================================================================
# Run
# ================================================================

def compare_runs(base_dir=BASE_DIR, output_path=OUTPUT_PATH):
    console = Console(record=True)
    runs = load_runs(console, base_dir)
    if not runs:
        console.print(f"[red]No run folders ({MODEL_PREFIX}<model>/{RUN_PREFIX}*) found in {base_dir}.[/red]")
        return None

    best = best_per_model(runs)
    tables = [
        metric_table(f"1. All runs ({len(runs)}): accuracy, tokens and time", runs, SUMMARY_COLUMNS,
                     caption="[bold green]* best[/] / [red]worst[/] in the column.  "
                             "Time is the sum of the per-image runs, retries included."),
        metric_table("2. All runs: accuracy per field", runs, FIELD_COLUMNS),
        error_overview_table(runs),
    ]
    if len(best) > 1:
        tables += [
            metric_table("4. Best configuration of each model (highest field accuracy)",
                         best, SUMMARY_COLUMNS, best_config=True),
            metric_table("5. Best configuration of each model: accuracy per field",
                         best, FIELD_COLUMNS, best_config=True),
            error_matrix_table("6. Mistakes of the best configurations", best),
        ]
    tables = [table for table in tables if table]

    # Never cut columns short: widen the output to fit the widest table, also for comparison.txt.
    wide = console.options.update(max_width=10_000)
    console.width = max([console.width] + [console.measure(table, options=wide).maximum for table in tables])
    for table in tables:
        console.print(table)
        console.print()
    console.save_text(str(output_path))   # plain-text copy, without colours
    console.print(f"[dim]Saved: {output_path}[/dim]", soft_wrap=True)
    return runs


if __name__ == "__main__":
    compare_runs()

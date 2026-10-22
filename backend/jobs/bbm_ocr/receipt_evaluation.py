"""
Evaluation for receipt extraction.

Compares predicted receipts with ground truth, per image, ignoring all
"confidence" blocks, and produces both accuracy numbers AND a detailed
report of what is wrong.

Key design points
-----------------
* Names are normalised (case, underscores, punctuation, extra spaces), so
  "PERTAMINA_DEX" == "pertamina dex" == "Pertamina  Dex".
* Dates are parsed, so "4/2/2026" == "04/02/2026" == "04-02-2026".
* Numeric fields support two modes: "exact" and "tolerance".
* Several receipts in one image have no coordinates / IDs, so predicted and
  GT receipts are paired with an optimal one-to-one assignment (Hungarian
  algorithm) that maximises the number of correct fields. The date is a
  field like any other, so receipts that are identical except for the date
  are paired by date. Ties (e.g. a misread date on otherwise-identical
  receipts) are broken by reading order, which preserves top-to-bottom order.
* Products inside a receipt are paired the same way.
"""

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from backend.jobs.bbm_ocr.receipt_config import GT_PATH, RESULT_PATH
from backend.jobs.bbm_ocr.receipt_utils import load_json

try:
    from scipy.optimize import linear_sum_assignment
except ImportError:
    linear_sum_assignment = None


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
NUMERIC_MODE = "tolerance"  # "exact" or "tolerance"

TOLERANCE = {
    "money": (1.0, 0.0),       # discount, total, unit_price, total_price
    "quantity": (0.01, 0.0),   # litres etc. (32.38 vs 32.389 passes)
}
NUMERIC_KIND = {
    "discount": "money",
    "total": "money",
    "unit_price": "money",
    "total_price": "money",
    "quantity": "quantity",
}

# 1.0 = names must match exactly after normalisation. 
# Lower (e.g. 0.9) allows small OCR typos.
NAME_THRESHOLD = 1.0

RECEIPT_FIELDS = ["date", "discount", "total"]
PRODUCT_FIELDS = ["name", "quantity", "unit_price", "total_price"]

# Where evaluate_results() saves the report files
# And how many errors it prints to the console (everything is always saved to the files).
REPORT_DIR = RESULT_PATH / "evaluation_report"
PRINT_MAX_ERRORS = 25


# --------------------------------------------------------------------------
# Normalisers / comparators
# --------------------------------------------------------------------------
def normalize_name(value):
    if value is None:
        return ""
    s = str(value).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)  # '_', '-', '.', etc. -> space
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a, b):
    a, b = normalize_name(a), normalize_name(b)
    if a == b:
        return 1.0
    if a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def names_match(a, b):
    return name_similarity(a, b) >= NAME_THRESHOLD


def normalize_date(value):
    if value is None:
        return None
    s = str(value).strip()
    parts = re.findall(r"\d+", s)
    if len(parts) == 3:
        d, m, y = (int(p) for p in parts)
        if d > 31:
            d, y = y, d
        if y < 100:
            y += 2000
        try:
            return datetime(y, m, d).date().isoformat()
        except ValueError:
            pass
    return re.sub(r"\s+", "", s).lower()


def to_float(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", ""))
    except ValueError:
        return None


def numbers_match(pred, gt, field, mode):
    p, g = to_float(pred), to_float(gt)
    if p is None or g is None:
        return p is None and g is None
    diff = abs(p - g)
    if mode == "exact":
        return diff < 1e-9
    abs_tol, rel_tol = TOLERANCE[NUMERIC_KIND[field]]
    return diff <= max(abs_tol, rel_tol * abs(g))


def field_match(field, pred, gt, mode):
    if field == "date":
        return normalize_date(pred) == normalize_date(gt)
    if field == "name":
        return names_match(pred, gt)
    return numbers_match(pred, gt, field, mode)


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------
def assign(sim):
    """Maximise total similarity. sim is a list of rows (preds) x cols (gts).
    Returns list of (pred_idx, gt_idx)."""
    if not sim or not sim[0]:
        return []
    if linear_sum_assignment is not None:
        import numpy as np
        rows, cols = linear_sum_assignment(-np.array(sim, dtype=float))
        return list(zip(rows.tolist(), cols.tolist()))
    pairs = sorted(
        ((sim[i][j], i, j) for i in range(len(sim)) for j in range(len(sim[0]))),
        reverse=True,
    )
    used_i, used_j, out = set(), set(), []
    for _, i, j in pairs:
        if i not in used_i and j not in used_j:
            used_i.add(i); used_j.add(j); out.append((i, j))
    return out


# --------------------------------------------------------------------------
# Helpers for error records
# --------------------------------------------------------------------------
def _clean_product(p):
    return {k: v for k, v in (p or {}).items() if k != "confidence"}


def _clean_receipt(r):
    out = {k: v for k, v in (r or {}).items() if k not in ("confidence", "products")}
    out["products"] = [_clean_product(p) for p in ((r or {}).get("products") or [])]
    return out


def _mismatch(level, field, gt_value, pred_value, product_index=None, product_name=None):
    err = {
        "type": "field_mismatch",
        "level": level,
        "field": field,
        "gt": gt_value,
        "pred": pred_value,
    }
    if level == "product":
        err["product_index"] = product_index
        err["product_name"] = product_name
    if field in NUMERIC_KIND:
        g, p = to_float(gt_value), to_float(pred_value)
        if g is not None and p is not None:
            err["diff"] = round(p - g, 6)
    return err


# --------------------------------------------------------------------------
# Product / receipt comparison
# --------------------------------------------------------------------------
def compare_product(pred, gt, mode):
    """-> {field: bool}"""
    pred = pred or {}
    return {f: field_match(f, pred.get(f), gt.get(f), mode) for f in PRODUCT_FIELDS}


def product_similarity(pred, gt, mode, i, j):
    res = compare_product(pred, gt, mode)
    score = sum(res.values())
    score += 0.1 * name_similarity(pred.get("name"), gt.get("name"))  # tie-break
    score += 1e-3 if i == j else 0.0
    return score


def compare_receipt(pred, gt, mode):
    """Compare one predicted receipt (or None) with one GT receipt.

    Returns (counts, extra_products, correct_total, errors)
      counts: {field: [correct, total]} based on GT fields
      errors: list of error dicts (without image / receipt context)
    """
    pred = pred or {}
    counts = defaultdict(lambda: [0, 0])
    errors = []

    for f in RECEIPT_FIELDS:
        ok = bool(pred) and field_match(f, pred.get(f), gt.get(f), mode)
        counts[f][0] += int(ok)
        counts[f][1] += 1
        if pred and not ok:
            errors.append(_mismatch("receipt", f, gt.get(f), pred.get(f)))

    gt_products = gt.get("products") or []
    pred_products = pred.get("products") or []

    sim = [
        [product_similarity(p, g, mode, i, j) for j, g in enumerate(gt_products)]
        for i, p in enumerate(pred_products)
    ]
    pairing = {j: i for i, j in assign(sim)}

    for j, g in enumerate(gt_products):
        p = pred_products[pairing[j]] if j in pairing else None
        if p is None:
            res = {f: False for f in PRODUCT_FIELDS}
            if pred:  # receipt was found, but this product was not
                errors.append({
                    "type": "missing_product", "level": "product",
                    "product_index": j, "product_name": g.get("name"),
                    "gt": _clean_product(g), "pred": None,
                })
        else:
            res = compare_product(p, g, mode)
        for f in PRODUCT_FIELDS:
            counts[f][0] += int(res[f])
            counts[f][1] += 1
            if p is not None and not res[f]:
                errors.append(_mismatch("product", f, g.get(f), p.get(f), j, g.get("name")))

    used = set(pairing.values())
    for i, p in enumerate(pred_products):
        if i not in used:
            errors.append({
                "type": "extra_product", "level": "product",
                "product_index": i, "product_name": p.get("name"),
                "gt": None, "pred": _clean_product(p),
            })

    extra_products = max(0, len(pred_products) - len(gt_products))
    correct = sum(c for c, _ in counts.values())
    return counts, extra_products, correct, errors


def is_exact(counts, extra_products):
    return extra_products == 0 and all(c == t for c, t in counts.values())


# --------------------------------------------------------------------------
# Main evaluation
# --------------------------------------------------------------------------
def _img_sort_key(k):
    k = str(k)
    return (0, int(k), "") if k.isdigit() else (1, 0, k)


def evaluate(predictions, gt, numeric_mode=NUMERIC_MODE):
    if numeric_mode not in {"exact", "tolerance"}:
        raise ValueError("numeric_mode must be 'exact' or 'tolerance'.")

    predictions = {str(k): v for k, v in predictions.items()}
    gt = {str(k): v for k, v in gt.items()}

    totals = defaultdict(lambda: [0, 0])
    per_image = {}
    all_errors = []
    n_gt = n_pred = n_exact = 0
    count_correct_images = 0

    for img_id, gt_receipts in gt.items():
        preds = predictions.get(img_id) or []

        # Pair receipts: more correct fields = better. Small order bonus
        # breaks ties between otherwise indistinguishable receipts.
        sim = []
        for i, p in enumerate(preds):
            row = []
            for j, g in enumerate(gt_receipts):
                _, extras, correct, _ = compare_receipt(p, g, numeric_mode)
                row.append(correct - 0.5 * extras + (1e-3 if i == j else 0.0))
            sim.append(row)
        pairing = {j: i for i, j in assign(sim)}

        img_counts = defaultdict(lambda: [0, 0])
        receipts_detail = []
        img_errors = []
        img_exact = 0
        extra_products_total = 0

        for j, g in enumerate(gt_receipts):
            p = preds[pairing[j]] if j in pairing else None
            counts, extras, _, errs = compare_receipt(p, g, numeric_mode)
            exact = p is not None and is_exact(counts, extras)
            img_exact += int(exact)
            extra_products_total += extras

            ctx = {
                "image": img_id,
                "gt_receipt_index": j,
                "gt_date": g.get("date"),
                "pred_receipt_index": pairing.get(j),
                "pred_date": p.get("date") if p else None,
            }
            if p is None:
                errs = [{
                    "type": "missing_receipt", "level": "receipt",
                    "gt": _clean_receipt(g), "pred": None,
                }]
            img_errors.extend({**ctx, **e} for e in errs)

            for f, (c, t) in counts.items():
                img_counts[f][0] += c
                img_counts[f][1] += t
                totals[f][0] += c
                totals[f][1] += t
            receipts_detail.append({
                "gt_index": j,
                "pred_index": pairing.get(j),
                "gt_date": g.get("date"),
                "pred_date": p.get("date") if p else None,
                "exact_match": exact,
                "fields": {f: f"{c}/{t}" for f, (c, t) in counts.items()},
            })

        used = set(pairing.values())
        for i, p in enumerate(preds):
            if i not in used:
                img_errors.append({
                    "image": img_id,
                    "type": "extra_receipt", "level": "receipt",
                    "gt_receipt_index": None, "gt_date": None,
                    "pred_receipt_index": i, "pred_date": p.get("date"),
                    "gt": None, "pred": _clean_receipt(p),
                })

        all_errors.extend(img_errors)
        n_gt += len(gt_receipts)
        n_pred += len(preds)
        n_exact += img_exact
        count_correct_images += int(len(preds) == len(gt_receipts))

        per_image[img_id] = {
            "n_gt_receipts": len(gt_receipts),
            "n_pred_receipts": len(preds),
            "exact_receipts": img_exact,
            "extra_pred_receipts": max(0, len(preds) - len(gt_receipts)),
            "extra_pred_products": extra_products_total,
            "field_accuracy": {f: round(c / t, 4) for f, (c, t) in img_counts.items() if t},
            "receipts": receipts_detail,
            "errors": img_errors,
        }

    extra_images = sorted(set(predictions) - set(gt), key=_img_sort_key)
    for img_id in extra_images:
        recs = predictions[img_id] or []
        if recs:
            all_errors.append({
                "image": img_id, "type": "extra_image", "level": "image",
                "gt_receipt_index": None, "gt_date": None,
                "pred_receipt_index": None, "pred_date": None,
                "gt": None, "pred": [_clean_receipt(r) for r in recs],
            })

    field_acc = {f: (c / t if t else 0.0) for f, (c, t) in totals.items()}
    all_c = sum(c for c, _ in totals.values())
    all_t = sum(t for _, t in totals.values())
    precision = n_exact / n_pred if n_pred else 0.0
    recall = n_exact / n_gt if n_gt else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    error_summary = {
        "total": len(all_errors),
        "by_type": dict(Counter(e["type"] for e in all_errors)),
        "by_field": dict(Counter(e["field"] for e in all_errors if e["type"] == "field_mismatch")),
        "images_with_errors": sum(1 for v in per_image.values() if v["errors"]),
    }

    return {
        "numeric_mode": numeric_mode,
        "overall_field_accuracy": all_c / all_t if all_t else 0.0,
        "field_accuracy": field_acc,
        "receipt_exact_accuracy": recall,   # exact receipts / GT receipts
        "receipt_precision": precision,
        "receipt_recall": recall,
        "receipt_f1": f1,
        "receipt_count_accuracy": count_correct_images / len(gt) if gt else 0.0,
        "n_images": len(gt),
        "n_gt_receipts": n_gt,
        "n_pred_receipts": n_pred,
        "images_only_in_predictions": extra_images,
        "error_summary": error_summary,
        "errors": all_errors,
        "per_image": per_image,
    }


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def _j(v):
    return json.dumps(v, ensure_ascii=False, default=str)


def _fmt_diff(d):
    return f"{d:+.4f}".rstrip("0").rstrip(".")


def _brief_product(p):
    if not p:
        return "-"
    return (f"{p.get('name')} | qty={p.get('quantity')} | unit_price={p.get('unit_price')} "
            f"| total_price={p.get('total_price')}")


def _brief_receipt(r):
    if not r:
        return "-"
    prods = "; ".join(_brief_product(p) for p in r.get("products", [])) or "no products"
    return (f"date={r.get('date')}, discount={r.get('discount')}, total={r.get('total')} "
            f"[{prods}]")


def format_error(e):
    t = e["type"]
    if t == "field_mismatch":
        where = ""
        if e["level"] == "product":
            where = f"product #{e['product_index'] + 1} ({e['product_name']}): "
        diff = f"  (diff {_fmt_diff(e['diff'])})" if "diff" in e else ""
        return f"{where}{e['field']}: expected {_j(e['gt'])}, got {_j(e['pred'])}{diff}"
    if t == "missing_product":
        return f"MISSING product #{e['product_index'] + 1}: {_brief_product(e['gt'])}"
    if t == "extra_product":
        return f"EXTRA product (not in ground truth): {_brief_product(e['pred'])}"
    if t == "missing_receipt":
        return f"MISSING receipt (nothing predicted for it): {_brief_receipt(e['gt'])}"
    if t == "extra_receipt":
        return f"EXTRA receipt (not in ground truth): {_brief_receipt(e['pred'])}"
    if t == "extra_image":
        return f"Image is not in ground truth, but {len(e['pred'])} receipt(s) were predicted"
    return str(e)


def error_prefix(e):
    parts = [f"image {e['image']}"]
    if e.get("gt_receipt_index") is not None:
        parts.append(f"receipt #{e['gt_receipt_index'] + 1}")
    elif e.get("pred_receipt_index") is not None:
        parts.append(f"predicted receipt #{e['pred_receipt_index'] + 1}")
    return " | ".join(parts)


def summary_lines(report):
    return [
        f"Numeric mode            : {report['numeric_mode']}",
        f"Images / GT receipts    : {report['n_images']} / {report['n_gt_receipts']} "
        f"(pred receipts: {report['n_pred_receipts']})",
        f"Overall field accuracy  : {report['overall_field_accuracy']:.2%}",
        *[f"  {f:<12}: {a:.2%}" for f, a in report["field_accuracy"].items()],
        f"Receipt exact accuracy  : {report['receipt_exact_accuracy']:.2%}",
        f"Receipt precision/recall/F1: {report['receipt_precision']:.2%} / "
        f"{report['receipt_recall']:.2%} / {report['receipt_f1']:.2%}",
        f"Receipt-count accuracy  : {report['receipt_count_accuracy']:.2%}",
    ]


def breakdown_lines(report):
    es = report["error_summary"]
    if not es["total"]:
        return ["No errors found."]
    lines = [f"Errors: {es['total']} in {es['images_with_errors']} of {report['n_images']} images"]
    lines.append("  by type:")
    for t, n in sorted(es["by_type"].items(), key=lambda kv: -kv[1]):
        lines.append(f"    {t:<16}{n}")
    if es["by_field"]:
        lines.append("  field mismatches by field:")
        for f, n in sorted(es["by_field"].items(), key=lambda kv: -kv[1]):
            lines.append(f"    {f:<16}{n}")
    return lines


def print_report(report):
    print("\n".join(summary_lines(report)))


def print_errors(report, limit=PRINT_MAX_ERRORS):
    print("\n".join(breakdown_lines(report)))
    errors = report["errors"]
    if not errors:
        return
    shown = errors if limit is None else errors[:limit]
    print()
    for e in shown:
        print(f"  [{error_prefix(e)}] {format_error(e)}")
    if len(shown) < len(errors):
        print(f"  ... {len(errors) - len(shown)} more (see the saved report)")


def build_text_report(report):
    L = []
    L.append("RECEIPT EXTRACTION - EVALUATION REPORT")
    L.append("=" * 70)
    L.extend(summary_lines(report))
    L.append("")
    L.extend(breakdown_lines(report))

    errs_by_img = {img: info["errors"] for img, info in report["per_image"].items() if info["errors"]}
    extra_img_errs = [e for e in report["errors"] if e["type"] == "extra_image"]
    for e in extra_img_errs:
        errs_by_img.setdefault(e["image"], []).append(e)

    if errs_by_img:
        L.append("")
        L.append("Images with the most errors:")
        worst = sorted(errs_by_img.items(), key=lambda kv: (-len(kv[1]), _img_sort_key(kv[0])))[:10]
        for img, errs in worst:
            L.append(f"  image {img}: {len(errs)} error(s)")

        L.append("")
        L.append("DETAILS BY IMAGE")
        L.append("(expected = ground truth, got = prediction)")
        L.append("=" * 70)

        for img in sorted(errs_by_img, key=_img_sort_key):
            info = report["per_image"].get(img)
            if info:
                head = (f"Image {img}  -  {info['n_gt_receipts']} GT receipt(s), "
                        f"{info['n_pred_receipts']} predicted, {len(errs_by_img[img])} error(s)")
            else:
                head = f"Image {img}  -  not in ground truth"
            L.append("")
            L.append(head)
            L.append("-" * len(head))

            groups = {}
            for e in errs_by_img[img]:
                groups.setdefault((e.get("gt_receipt_index"), e.get("pred_receipt_index")), []).append(e)

            for (gi, pi), items in groups.items():
                e0 = items[0]
                if gi is not None and pi is not None:
                    title = (f"Receipt #{gi + 1} (GT date {e0['gt_date']}) "
                             f"matched with predicted receipt #{pi + 1} (date {e0['pred_date']})")
                elif gi is not None:
                    title = f"Receipt #{gi + 1} (GT date {e0['gt_date']}) - no prediction"
                elif pi is not None:
                    title = f"Predicted receipt #{pi + 1} (date {e0['pred_date']}) - no GT match"
                else:
                    title = "Image level"
                L.append(f"  {title}")
                for e in items:
                    L.append(f"    - {format_error(e)}")

    return "\n".join(L) + "\n"


CSV_COLUMNS = [
    "image", "type", "level", "gt_receipt", "gt_date", "pred_receipt", "pred_date",
    "product", "product_name", "field", "expected", "predicted", "diff", "description",
]


def errors_to_rows(report):
    rows = []
    for e in report["errors"]:
        t = e["type"]
        if t == "field_mismatch":
            exp, got = e["gt"], e["pred"]
        elif t == "missing_product":
            exp, got = _brief_product(e["gt"]), None
        elif t == "extra_product":
            exp, got = None, _brief_product(e["pred"])
        elif t == "missing_receipt":
            exp, got = _brief_receipt(e["gt"]), None
        elif t == "extra_receipt":
            exp, got = None, _brief_receipt(e["pred"])
        else:
            exp, got = None, f"{len(e['pred'])} receipt(s)"

        def one_based(k):
            return None if e.get(k) is None else e[k] + 1

        rows.append({
            "image": e["image"],
            "type": t,
            "level": e.get("level"),
            "gt_receipt": one_based("gt_receipt_index"),
            "gt_date": e.get("gt_date"),
            "pred_receipt": one_based("pred_receipt_index"),
            "pred_date": e.get("pred_date"),
            "product": one_based("product_index"),
            "product_name": e.get("product_name"),
            "field": e.get("field"),
            "expected": exp,
            "predicted": got,
            "diff": e.get("diff"),
            "description": format_error(e),
        })
    return rows


def write_reports(report, report_dir=REPORT_DIR):
    """Save .txt (readable), .csv (flat, one row per error) and .json (full)."""
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    mode = report["numeric_mode"]

    txt = report_dir / f"evaluation_report_{mode}.txt"
    csv_path = report_dir / f"evaluation_errors_{mode}.csv"
    js = report_dir / f"evaluation_report_{mode}.json"

    txt.write_text(build_text_report(report), encoding="utf-8")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(errors_to_rows(report))
    js.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"txt": txt, "csv": csv_path, "json": js}


def evaluate_results(predictions, numeric_mode=None, both_modes=False,
                     report_dir=REPORT_DIR, save=True, max_print=PRINT_MAX_ERRORS):
    """Evaluate predictions against the ground truth at GT_PATH.

    numeric_mode: "exact" or "tolerance" (default: NUMERIC_MODE above).
    both_modes  : if True, run exact AND tolerance; returns
                  {"exact": report, "tolerance": report}.
    save        : write the .txt / .csv / .json report files to report_dir.
    max_print   : how many errors to print to the console (None = all).
    """
    gt = load_json(GT_PATH)
    modes = ("exact", "tolerance") if both_modes else (numeric_mode or NUMERIC_MODE,)

    reports = {}
    for mode in modes:
        report = evaluate(predictions, gt, mode)
        reports[mode] = report
        print_report(report)
        print()
        print_errors(report, max_print)
        if save:
            paths = write_reports(report, report_dir)
            print(f"\nReport saved: {paths['txt']}\n              {paths['csv']}")
        print()

    return reports if both_modes else reports[modes[0]]
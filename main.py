import json

from src.receipt_config import OUTPUT_PATH, GT_PATH
from src.receipt_extraction import extract_batch
from src.receipt_evaluation import evaluate_results
from src.receipt_validation import validate_batch, log_unmatched_cases
from src.receipt_utils import load_json


# Choose: "extract", "evaluate", or "validate"
MODE = "validate"

# validate mode: the employee-submitted data (same format as images/gt.json).
# Until you have a mock file, the ground truth is used as the "submitted" data.
SUBMITTED_PATH = GT_PATH
VALIDATION_PATH = OUTPUT_PATH.parent / "validation_results.json"
USAGE_PATH = OUTPUT_PATH.parent / "jev_usage.json"


def _need(path, label):
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path.resolve()}")
    return load_json(path)


def run_pipeline(mode=MODE):
    mode = mode.strip().lower()

    if mode == "extract":
        return extract_batch()

    if mode == "evaluate":
        predictions = _need(OUTPUT_PATH, "Prediction file")
        _need(GT_PATH, "Ground truth")
        return evaluate_results(predictions)

    if mode == "validate":
        ocr = _need(OUTPUT_PATH, "Prediction file (run extract first)")
        submitted = _need(SUBMITTED_PATH, "Submitted data")
        results = validate_batch(submitted, ocr, usage_path=USAGE_PATH)
        VALIDATION_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        log_unmatched_cases(results, "results/unmatched_cases.json")   # use .txt for a readable version
        counts = {}
        for r in results.values():
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        print("validation:", counts)
        return results

    raise ValueError("MODE must be 'extract', 'evaluate', or 'validate'.")


if __name__ == "__main__":
    run_pipeline()
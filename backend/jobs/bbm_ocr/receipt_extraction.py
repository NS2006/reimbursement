from backend.jobs.bbm_ocr.receipt_ocr_haiku import BASE_USAGE_KEYS, add_usage, extract_receipts

from backend.jobs.bbm_ocr.receipt_config import (
    IMAGE_DIR,
    SCHEMA_PATH,
    OUTPUT_PATH,
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
)

from backend.jobs.bbm_ocr.receipt_utils import load_json, save_json


def flatten_usage(usage, prefix=""):
    """
    Flatten nested usage dictionaries into one level, e.g.
    {"output_tokens_details": {"reasoning_tokens": 5}}
    -> {"output_tokens_details.reasoning_tokens": 5}
    """
    flat = {}

    for key, value in usage.items():
        name = f"{prefix}{key}"

        if isinstance(value, dict):
            flat.update(flatten_usage(value, f"{name}."))
        else:
            flat[name] = value

    return flat


def format_usage_value(name, value):
    if name == "elapsed_seconds":
        return f"{value:.3f}s"

    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.3f}"

    return f"{int(value):,}"


def print_usage(usage, indent=2):
    """Print every usage field (token counts, time, anything else Claude reported)."""
    flat = flatten_usage(usage)

    # Display-only value: input tokens that were not served from cache.
    if "input_tokens" in flat and "cached_input_tokens" in flat:
        items = []

        for name, value in flat.items():
            items.append((name, value))

            if name == "cached_input_tokens":
                items.append((
                    "uncached_input_tokens",
                    flat["input_tokens"] - flat["cached_input_tokens"],
                ))
    else:
        items = list(flat.items())

    width = max((len(name) for name, _ in items), default=0) + 2

    for name, value in items:
        print(f"{' ' * indent}{name + ':':<{width}}{format_usage_value(name, value)}")


def extract_batch():
    if not IMAGE_DIR.is_dir():
        raise FileNotFoundError(
            f"Image directory not found: {IMAGE_DIR.resolve()}"
        )

    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(
            f"Schema file not found: {SCHEMA_PATH.resolve()}"
        )

    # Photos and PDFs, named by their id like the photos (e.g. 65.pdf), so results and ground truth match by id.
    file_extensions = IMAGE_EXTENSIONS | PDF_EXTENSIONS

    image_paths = sorted(
        (
            path
            for path in IMAGE_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in file_extensions
            and path.stem.isdigit()
        ),
        key=lambda path: int(path.stem),
    )

    # Preserve previous results so a failed extraction doesn't
    # accidentally erase other images when rerunning the batch.
    all_results = (
        load_json(OUTPUT_PATH)
        if OUTPUT_PATH.exists()
        else {}
    )

    batch_stats = {
        "processed": 0,
        "failed": 0,
        "failed_images": [],
    }

    # Every usage field, summed over all successfully processed images
    # (input/cached/output tokens, reasoning tokens, elapsed_seconds, ...).
    batch_usage = dict.fromkeys(BASE_USAGE_KEYS, 0)
    batch_usage["elapsed_seconds"] = 0.0

    # Usage of each image, saved next to the results for later reporting.
    per_image_usage = {}
    usage_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_usage.json")

    pdf_count = sum(path.suffix.lower() in PDF_EXTENSIONS for path in image_paths)
    print(f"Found {len(image_paths)} files ({pdf_count} PDF).")

    for index, image_path in enumerate(image_paths, start=1):
        image_name = image_path.stem

        print(
            f"\n[{index}/{len(image_paths)}] "
            f"Processing: {image_path.name}"
        )

        try:
            result, usage = extract_receipts(
                image_path=image_path,
                schema_path=SCHEMA_PATH,
            )

            receipts = result.get("receipts")

            if not isinstance(receipts, list):
                raise ValueError(
                    "Extraction result must contain a "
                    "'receipts' list."
                )

            all_results[image_name] = receipts
            batch_stats["processed"] += 1

            add_usage(batch_usage, usage)
            per_image_usage[image_name] = usage

            print(
                f"  Receipts: {len(receipts)} | "
                f"Time: {usage.get('elapsed_seconds', 0):.3f}s | "
                f"Tokens: in {usage.get('input_tokens', 0):,} "
                f"(cached {usage.get('cached_input_tokens', 0):,}) / "
                f"out {usage.get('output_tokens', 0):,}"
            )

        except Exception as exc:
            batch_stats["failed"] += 1
            batch_stats["failed_images"].append({
                "image": image_name,
                "error": str(exc),
            })

            print(f"  FAILED: {exc}")

        # Persist after each image. Previous successful results
        # remain available if a later image fails.
        save_json(all_results, OUTPUT_PATH)
        save_json(
            {"total": batch_usage, "per_image": per_image_usage},
            usage_path,
        )

    print("\n" + "=" * 65)
    print("BATCH EXTRACTION SUMMARY")
    print("=" * 65)
    print(f"Images found:       {len(image_paths)}")
    print(f"Processed:          {batch_stats['processed']}")
    print(f"Failed:             {batch_stats['failed']}")
    print("\nUsage (processed images):")
    print_usage(batch_usage)
    print(f"\nResults saved:      {OUTPUT_PATH.resolve()}")
    print(f"Usage saved:        {usage_path.resolve()}")

    if batch_stats["failed_images"]:
        print("\nFailed images:")
        for item in batch_stats["failed_images"]:
            print(f"  {item['image']}: {item['error']}")

    return all_results
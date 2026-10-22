from pathlib import Path

from flask import send_from_directory

# The receipt photos of the dummy seed data (backend/database/seeds/dummy_reimbursement.sql).
DUMMY_RECEIPT_DIR = Path(__file__).resolve().parent.parent / "database" / "dummy_bbm_receipt"


def get_dummy_receipt(filename):
    """Serve one dummy receipt photo, so the seeded attachment urls are real web addresses like the ones
    callers send. Only files inside DUMMY_RECEIPT_DIR are served; anything else is 404."""
    return send_from_directory(DUMMY_RECEIPT_DIR, filename)

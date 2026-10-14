import hmac
import logging
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)
bp = Blueprint("reimbursement", __name__)


def _authorized() -> bool:
    """If REIMBURSEMENT_API_KEY is set, callers must send it as the x-api-key header."""
    expected = os.environ.get("REIMBURSEMENT_API_KEY")
    if not expected:
        return True
    given = request.headers.get("x-api-key", "").encode()
    return hmac.compare_digest(given, expected.encode())


@bp.post("/store-reimbursement")
def store_reimbursement():
    if not _authorized():
        return jsonify(error="unauthorized"), 401

    # TODO: Not Finished Yet
    return jsonify(error="not_implemented", message="Reimbursement endpoint is not built yet"), 501
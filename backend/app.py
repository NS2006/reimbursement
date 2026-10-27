"""Web API for the reimbursement website. Run from the repo root: py -m backend.app"""

import gzip
import logging
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.routes import bp

log = logging.getLogger(__name__)

# The DB_* settings live in the .env file in the repo root.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GZIP_MIN_BYTES = 1024  # smaller answers are sent as they are: compressing them saves next to nothing
MAX_BODY_BYTES = 5 * 1024 * 1024  # bigger request bodies get 413 Payload Too Large
ANY_BODY_SIZE = {"api.store_reimbursements"}  # Darwinbox's batches of reports: no limit on their size


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix="/api")

    @app.before_request
    def limit_body_size():
        # Per request, not MAX_CONTENT_LENGTH: a request can't lift the app's limit, only set its own.
        if request.endpoint not in ANY_BODY_SIZE:
            request.max_content_length = MAX_BODY_BYTES

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return jsonify(error=error.name.lower().replace(" ", "_"), message=error.description), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        # The details go to the server log only, so the response does not leak internals.
        log.exception("Unhandled error")
        return jsonify(error="internal_error", message="Something went wrong on the server."), 500

    @app.after_request
    def compress_json(response):
        # JSON is mostly the same keys and words again and again: gzip makes the report list about 14 times smaller
        # (13 MB -> under 1 MB with five years of reports). Files (receipts, the Excel export) are sent as they are.
        if response.mimetype != "application/json" or response.direct_passthrough or response.is_streamed:
            return response
        response.vary.add("Accept-Encoding")
        if request.accept_encodings["gzip"] and "Content-Encoding" not in response.headers:
            data = response.get_data()
            if len(data) >= GZIP_MIN_BYTES:
                response.set_data(gzip.compress(data, compresslevel=5))
                response.headers["Content-Encoding"] = "gzip"
        return response

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="127.0.0.1", port=5000)

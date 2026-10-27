from flask import Blueprint

from backend.services import (
    attachment_service,
    auth_service,
    comment_service,
    dummy_receipt_service,
    export_service,
    fuel_price_service,
    ocr_service,
    reimbursement_service,
    review_service,
    user_service,
)

# Every backend endpoint is listed here (served under /api, see app.py).
# This file only maps a URL to a service function; the service handles the request and calls a repository.
bp = Blueprint("api", __name__)

# For the website
bp.add_url_rule("/users", view_func=user_service.list_users, methods=["GET"])
bp.add_url_rule("/auth/login", view_func=auth_service.login, methods=["POST"])
bp.add_url_rule("/attachments/<int:attachment_id>/file", view_func=attachment_service.get_file, methods=["GET"])
bp.add_url_rule("/reimbursements", view_func=reimbursement_service.list_reimbursements, methods=["GET"])
bp.add_url_rule("/reimbursements/summary", view_func=reimbursement_service.summarize_reimbursements, methods=["GET"])
bp.add_url_rule("/reimbursements/codes", view_func=reimbursement_service.list_codes, methods=["GET"])
bp.add_url_rule("/reimbursements/export", view_func=export_service.export_reimbursements, methods=["POST"])
bp.add_url_rule("/reimbursements/ocr/retry", view_func=ocr_service.retry_failed_reports, methods=["POST"])
bp.add_url_rule("/reimbursements/<code>", view_func=reimbursement_service.get_reimbursement, methods=["GET"])
bp.add_url_rule("/reimbursements/<code>/decisions", view_func=review_service.add_decision, methods=["POST"])
bp.add_url_rule("/reimbursements/<code>/ocr/retry", view_func=ocr_service.retry_failed, methods=["POST"])
bp.add_url_rule("/reimbursements/<code>/comments", view_func=comment_service.add_comment, methods=["POST"])
bp.add_url_rule("/reimbursements/<code>/comments/<int:comment_id>", view_func=comment_service.edit_comment, methods=["PATCH"])
bp.add_url_rule("/reimbursements/<code>/comments/<int:comment_id>", view_func=comment_service.delete_comment, methods=["DELETE"])
bp.add_url_rule("/fuel-prices", view_func=fuel_price_service.list_fuel_prices, methods=["GET"])
bp.add_url_rule("/fuel-prices/refresh", view_func=fuel_price_service.queue_refresh, methods=["POST"])

# For other systems: they send their reimbursement reports here
bp.add_url_rule("/reimbursements", view_func=reimbursement_service.store_reimbursements, methods=["POST"])

# Development only: the receipt photos of the dummy seed data
bp.add_url_rule("/dummy-receipts/<path:filename>", view_func=dummy_receipt_service.get_dummy_receipt, methods=["GET"])

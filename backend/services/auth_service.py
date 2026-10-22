import re

from flask import jsonify, request

from backend.repositories import user_repository

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
EMAIL_MAX_LENGTH = 255  # app_user.email is varchar(255)


def login():
    """Sign in as the user picked on the login page.

    There is no password on purpose: real sign-in is done by the Blibli gateway. This only checks
    that the picked user exists, so the website knows who is acting.
    """
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else None
    if (
        not isinstance(email, str)
        or len(email) > EMAIL_MAX_LENGTH
        or not EMAIL_PATTERN.fullmatch(email.strip())
    ):
        return jsonify(error="invalid_email", message='Send a JSON body like {"email": "name@example.com"}.'), 400

    user = user_repository.find_by_email(email.strip().lower())
    if user is None:
        return jsonify(error="user_not_found", message="No user with that email."), 404
    return jsonify(user=user)

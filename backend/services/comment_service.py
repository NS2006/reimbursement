from flask import jsonify, request

from backend.repositories import comment_repository, user_repository
from backend.services.json_values import to_json

DESCRIPTION_MAX_LENGTH = 2000

# Who is signed in is checked by the Blibli gateway, not here. The body names the user ("user_email"), which only has
# to belong to a known user; a comment can only be edited or deleted by the user who wrote it.


def add_comment(code):
    """POST /api/reimbursements/<code>/comments with {"user_email": ..., "description": ...}."""
    user, error = _user_from_body()
    if error:
        return error
    description, error = _description_from_body()
    if error:
        return error

    comment = comment_repository.add(code, user["email"], description)
    if comment is None:
        return _error(404, "not_found", f"No reimbursement with code {code}.")
    return jsonify(comment=to_json(comment)), 201


def edit_comment(code, comment_id):
    """PATCH /api/reimbursements/<code>/comments/<id> with {"user_email": ..., "description": ...}."""
    user, error = _user_from_body()
    if error:
        return error
    description, error = _description_from_body()
    if error:
        return error
    error = _not_own_comment(code, comment_id, user, "edit")
    if error:
        return error

    comment = comment_repository.update(comment_id, description)
    if comment is None:  # deleted in the meantime
        return _comment_not_found(code, comment_id)
    return jsonify(comment=to_json(comment))


def delete_comment(code, comment_id):
    """DELETE /api/reimbursements/<code>/comments/<id> with {"user_email": ...}. Answers 204 with no body."""
    user, error = _user_from_body()
    if error:
        return error
    error = _not_own_comment(code, comment_id, user, "delete")
    if error:
        return error

    if not comment_repository.delete(comment_id):  # deleted in the meantime
        return _comment_not_found(code, comment_id)
    return "", 204


def _body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _user_from_body():
    """(the user named by "user_email", None) or (None, error response)."""
    email = _body().get("user_email")
    if not isinstance(email, str) or not email.strip():
        return None, _error(400, "invalid_user", 'Send the commenting user as "user_email".')
    user = user_repository.find_by_email(email.strip().lower())
    if user is None:
        return None, _error(400, "invalid_user", "No user with that email.")
    return user, None


def _description_from_body():
    """(the trimmed "description", None) or (None, error response)."""
    description = _body().get("description")
    if not isinstance(description, str) or not description.strip():
        return None, _error(400, "invalid_description", "The comment is empty.")
    description = description.strip()
    if len(description) > DESCRIPTION_MAX_LENGTH:
        return None, _error(400, "invalid_description", f"A comment can have at most {DESCRIPTION_MAX_LENGTH} characters.")
    return description, None


def _not_own_comment(code, comment_id, user, action):
    """An error response unless the comment is on this report and was written by this user."""
    comment = comment_repository.find_on_report(code, comment_id)
    if comment is None:
        return _comment_not_found(code, comment_id)
    if comment["user_email"] != user["email"]:
        return _error(403, "not_comment_author", f"You can only {action} your own comments.")
    return None


def _comment_not_found(code, comment_id):
    return _error(404, "not_found", f"Reimbursement {code} has no comment {comment_id}.")


def _error(status, error, message):
    return jsonify(error=error, message=message), status

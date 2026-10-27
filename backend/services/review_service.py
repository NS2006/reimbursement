from flask import jsonify, request

from backend.repositories import review_repository, user_repository
from backend.services.json_values import to_json
from backend.services.reimbursement_service import report_detail

REASON_MAX_LENGTH = 1000

# approved / rejected decide the report; reopened takes the decision in force back.
DECISIONS = ("approved", "rejected", "reopened")
VERBS = {"approved": "approved", "rejected": "rejected", "reopened": "took back the decision on"}

# Who is signed in is checked by the Blibli gateway, not here. The body names the user ("user_email"), which only has
# to belong to a known user.


def add_decision(code):
    """POST /api/reimbursements/<code>/decisions: a reviewer approves or rejects a report, or takes the decision
    back.

    Body: {"user_email": ..., "decision": "rejected", "reason": "...", "based_on": 41}
      decision     approved / rejected / reopened
      reason       why; required to reject, optional otherwise
      based_on     the id of the newest decision the reviewer saw on the report (null when it had none), so two
                   reviewers deciding at the same time do not overwrite each other: the second one gets 409 and the
                   decision that was made in the meantime

    Answers 201 with the new decision and the whole report as GET /api/reimbursements/<code> sends it.
    """
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}

    email = body.get("user_email")
    user = user_repository.find_by_email(email.strip().lower()) if isinstance(email, str) and email.strip() else None
    if user is None:
        return _error(400, "invalid_user", 'Send the deciding user as "user_email", the email of a known user.')

    decision = body.get("decision")
    if decision not in DECISIONS:
        return _error(400, "invalid_decision", f"decision must be one of: {', '.join(DECISIONS)}.")
    based_on = body.get("based_on")
    if based_on is not None and (not isinstance(based_on, int) or isinstance(based_on, bool)):
        return _error(400, "invalid_based_on", "based_on must be the id of the newest decision you saw, or null.")

    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _error(400, "invalid_reason", "reason must be text.")
    reason = reason.strip() if reason else None
    if decision == "rejected" and not reason:
        return _error(400, "reason_required", "Say why the report is rejected.")
    if reason and len(reason) > REASON_MAX_LENGTH:
        return _error(400, "invalid_reason", f"The reason can be at most {REASON_MAX_LENGTH} characters.")

    outcome, detail = review_repository.add(code, decision, reason or None, user["email"], based_on)
    if outcome == "not_found":
        return _error(404, "not_found", f"No reimbursement with code {code}.")
    if outcome == "changed":
        message = (f"{detail['user_name']} {VERBS[detail['decision']]} {code} in the meantime."
                   if detail else f"The decision on {code} was taken back in the meantime.")
        return _error(409, "decision_changed", message)
    if outcome == "nothing_to_reopen":
        return _error(409, "nothing_to_reopen", f"No decision on {code} to take back.")
    if outcome == "unchanged":
        return _error(409, "already_decided", f"{code} is already {detail['decision']}.")

    return jsonify(decision=to_json(detail), reimbursement=to_json(report_detail(code))), 201


def _error(status, error, message):
    return jsonify(error=error, message=message), status

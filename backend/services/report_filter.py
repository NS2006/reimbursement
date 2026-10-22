"""The filter of the report list, as the website sends it: as query parameters to GET /api/reimbursements, /summary
and /codes, and in the JSON body of the Excel export and "Retry OCR on all". Checked here once for all of them.

    type    the reimbursement type (bbm)
    period  "all" or a month like "2026-10": the reports whose current revision was received in it, in WIB for every
            reviewer (MONTH_ZONE)
    status  "all" or needs_review / processing / approved / rejected
    by      a part of the status: with approved how they were approved (matched / proceed / reviewer), with
            needs_review why they need review (differences / failed)
    q       search text, in the code, the employee's name or number (any case)
    sort    a column, descending with a "-" in front: code, employee, received, total, differences, status
            (default -received: newest first)
    tz      the reviewer's time zone, minutes east of UTC (default 420, WIB), for the times in the Excel export
    page    the page shown, from 1
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.repositories.reimbursement_repository import LIST_SORTS, ReportQuery

PERIOD = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
STATUSES = ("needs_review", "processing", "approved", "rejected")
# The parts each status has (as the website's STATUS_PARTS)
STATUS_PARTS = {
    "approved": ("matched", "proceed", "reviewer"),
    "needs_review": ("differences", "failed"),
}
MAX_SEARCH_LENGTH = 100
DEFAULT_UTC_OFFSET = 420  # WIB
# The months are in WIB for everyone: a report belongs to the month (WIB) it was received in, so every reviewer, the
# list, the home page and the Excel export put it in the same month whatever their own time zone.
MONTH_UTC_OFFSET = 420
MONTH_ZONE = timezone(timedelta(minutes=MONTH_UTC_OFFSET), "WIB")
MAX_PAGE = 100_000


class FilterError(Exception):
    """A value of the filter is not valid: error is the short code for the answer, the message says what to send."""

    def __init__(self, error, message):
        super().__init__(message)
        self.error = error


@dataclass(frozen=True)
class ReportFilter:
    query: ReportQuery
    period: str  # "all" or "2026-10"
    status: str  # "all" or a status
    by: str | None
    search: str
    utc_offset: int  # minutes east of UTC
    page: int


def parse(values, types):
    """The filter in values (request.args, or a JSON body as a dict); types: the reimbursement types allowed (an
    empty type means every type). Raises FilterError."""
    reimbursement_type = _text(values, "type") or None
    if reimbursement_type is not None and reimbursement_type not in types:
        raise FilterError("invalid_type", f"type must be one of: {', '.join(types)}")

    utc_offset = _integer(values, "tz", DEFAULT_UTC_OFFSET)
    if not -720 <= utc_offset <= 840:
        raise FilterError("invalid_tz", "tz must be minutes east of UTC, from -720 to 840.")

    period = _text(values, "period") or "all"
    month = PERIOD.fullmatch(period)
    if period != "all" and month is None:
        raise FilterError("invalid_period", 'period must be "all" or a month like "2026-10".')
    received_from = received_to = None
    if month:
        year, number = int(month[1]), int(month[2])
        received_from = datetime(year, number, 1, tzinfo=MONTH_ZONE)
        received_to = datetime(year + number // 12, number % 12 + 1, 1, tzinfo=MONTH_ZONE)

    status = _text(values, "status") or "all"
    if status != "all" and status not in STATUSES:
        raise FilterError("invalid_status", f"status must be all or one of: {', '.join(STATUSES)}")
    by = _text(values, "by") or None
    if by is not None and by not in STATUS_PARTS.get(status, ()):
        choices = "; ".join(f"with {name}: {', '.join(parts)}" for name, parts in STATUS_PARTS.items())
        raise FilterError("invalid_by", f"by must be a part of the status ({choices}).")

    search = _text(values, "q").strip()
    if len(search) > MAX_SEARCH_LENGTH:
        raise FilterError("invalid_q", f"q must be at most {MAX_SEARCH_LENGTH} characters.")

    sort = _text(values, "sort") or "-received"
    key = sort.removeprefix("-")
    if key not in LIST_SORTS:
        raise FilterError("invalid_sort", f"sort must be one of {', '.join(LIST_SORTS)}, with a - in front for descending.")

    page = _integer(values, "page", 1)
    if not 1 <= page <= MAX_PAGE:
        raise FilterError("invalid_page", "page must be a number from 1.")

    query = ReportQuery(
        reimbursement_type=reimbursement_type,
        received_from=received_from,
        received_to=received_to,
        status=None if status == "all" else status,
        part=by,
        search=search or None,
        sort=key,
        descending=sort.startswith("-"),
    )
    return ReportFilter(query=query, period=period, status=status, by=by, search=search, utc_offset=utc_offset,
                        page=page)


def _text(values, name):
    value = values.get(name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise FilterError(f"invalid_{name}", f"{name} must be text.")
    return value


def _integer(values, name, default):
    value = values.get(name)
    if value is None or value == "":
        return default
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,7}", value):
        return int(value)
    raise FilterError(f"invalid_{name}", f"{name} must be a whole number.")

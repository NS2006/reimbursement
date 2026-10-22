from datetime import date, datetime
from decimal import Decimal


def to_json(value):
    """Database values made ready for jsonify: amounts become numbers, dates are written DD-MM-YYYY (as callers
    send them) and timestamps ISO 8601 with their time zone. Dicts and lists are converted all the way down."""
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):  # before date: a datetime is also a date
        return value.isoformat()
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    return value

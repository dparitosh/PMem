"""Validate the complete governance state before storing a metadata revision."""
from datetime import datetime


def validate_asset_state(value):
    status = value.get('lifecycle_status', 'draft')
    if status not in {'draft', 'in_review', 'approved', 'deprecated', 'retired'}:
        raise ValueError('Unsupported metadata lifecycle status')
    if status == 'approved' and any(not str(value.get(key) or '').strip()
                                     for key in ('steward', 'approval_evidence')):
        raise ValueError('Approved metadata requires a steward and approval evidence')
    if status in {'deprecated', 'retired'} and not str(value.get('deprecation_reason') or '').strip():
        raise ValueError('Deprecated or retired metadata requires a deprecation reason')
    dates = []
    for key in ('effective_from', 'effective_to'):
        text = str(value.get(key) or '').strip()
        try:
            dates.append(datetime.fromisoformat(text.replace('Z', '+00:00')) if text else None)
        except ValueError as exc:
            raise ValueError('Metadata effective dates must use ISO-8601 format') from exc
    start, end = dates
    if start is not None and end is not None:
        if (start.tzinfo is None) != (end.tzinfo is None):
            raise ValueError('Metadata effective dates must use consistent timezone qualification')
        if end < start:
            raise ValueError('Metadata effective_to cannot precede effective_from')

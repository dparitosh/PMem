"""Resolve an absent graph receipt without masking a live publication attempt."""
from datetime import datetime, timezone


def missing_receipt_status(record, *, graph_idle=False):
    if graph_idle:
        # Ontology-side preparation can be active before the graph writer starts.
        if record.get('status') == 'publishing' and record.get('phase') == 'rdf_preparation':
            try:
                if datetime.fromisoformat(record['active_until']) > datetime.now(timezone.utc):
                    return 'publishing'
            except (KeyError, TypeError, ValueError):
                return 'unverified'
        return 'not_published'
    if record.get('status') == 'unverified':
        return 'unverified'
    if record.get('status') != 'publishing':
        return 'not_published'
    try:
        deadline = datetime.fromisoformat(record['active_until'])
        return 'publishing' if deadline > datetime.now(timezone.utc) else 'unverified'
    except (KeyError, TypeError, ValueError):
        return 'unverified'

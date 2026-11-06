"""Versioned internal context metadata. Never an authorization credential."""
from datetime import datetime

from .goal_runner import selected_scope


def assemble(*, owner, run_id, purpose, context, deadline_at, contract_digest='', evidence_bytes=32000):
    if not all(isinstance(value, str) and value.strip() for value in (owner, run_id, purpose)):
        raise ValueError('Context requires a server-established owner, run and purpose')
    if type(evidence_bytes) is not int or not 1024 <= evidence_bytes <= 120000:
        raise ValueError('Invalid context evidence budget')
    if datetime.fromisoformat(deadline_at).tzinfo is None:
        raise ValueError('Context deadline requires a timezone')
    scope = selected_scope(context)
    # Project only identifiers; arbitrary context, credentials and prompt text
    # belong neither in the envelope nor in a handoff identity.
    return {'schema_version': 1, 'owner_ref': owner, 'run_id': run_id,
            'purpose': purpose, 'scope': scope, 'deadline_at': deadline_at,
            'contract_digest': contract_digest, 'evidence_bytes': evidence_bytes,
            'source_revision_status': 'unverified', 'authorization': 'owner_service_required'}


def public(envelope):
    return {key: value for key, value in envelope.items() if key != 'owner_ref'}


def verify(record, *, context, contract_digest):
    envelope = record.get('context_envelope')
    if envelope is None:
        return False  # Retained pre-envelope runs keep their existing checks.
    if not isinstance(envelope, dict) or envelope.get('schema_version') != 1:
        raise ValueError('Unsupported context envelope')
    expected = assemble(owner=record['owner'], run_id=record['run_id'],
        purpose=envelope.get('purpose'), context=context, deadline_at=record['deadline_at'],
        contract_digest=contract_digest, evidence_bytes=envelope.get('evidence_bytes'))
    if envelope != expected:
        raise ValueError('Retained context binding changed')
    return True

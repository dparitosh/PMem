"""Durable companion sessions with credential ownership and fixed expiry."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.network import bounded_timeout_seconds

store = PostgresRegistry('agentic_sessions')


def now():
    return datetime.now(timezone.utc)


def owner(request, actor):
    # Gateway principals remain stable across JWT renewal. Shared API keys share
    # a principal; individual user isolation requires individual credentials.
    authorization = request.headers.get('authorization', '')
    credential = '' if os.getenv('AUTH_MODE', 'token').lower() == 'entra' else (
        authorization[7:].strip() if authorization.lower().startswith('bearer ') else request.headers.get('x-api-key', '').strip())
    # Delegations change on reconnect; authorization already validated the
    # server-assigned actor. Keep raw-key isolation for compatibility callers.
    from backend.depo_platform.browser_credentials import PREFIX
    if credential.startswith(PREFIX):
        return hashlib.sha256(f'browser-principal:{actor}'.encode()).hexdigest()
    return hashlib.sha256(f'{actor}:{credential}'.encode()).hexdigest()


def open_session(request, actor, session_id=None):
    current = now()
    identity = owner(request, actor)
    identifier = str(session_id or uuid4())
    if len(identifier) > 128 or not identifier or any(ord(c) < 32 for c in identifier):
        raise HTTPException(422, 'Invalid session_id')
    with store.advisory_lock(identifier) as acquired:
        if not acquired:
            raise HTTPException(409, 'Session is being updated; retry')
        record = store.get(identifier)
        if record:
            if record['owner'] != identity:
                authorization = request.headers.get('authorization', '')
                credential = authorization[7:].strip() if authorization.lower().startswith('bearer ') else ''
                legacy_owner = hashlib.sha256(f'{actor}:{credential}'.encode()).hexdigest()
                from backend.depo_platform.browser_credentials import PREFIX
                if not credential.startswith(PREFIX) or record['owner'] != legacy_owner:
                    raise HTTPException(403, 'Session belongs to another identity')
                record['owner'] = identity
            # Idle conversations can be resumed by their authenticated owner.
            # Access-session expiry is enforced separately by authorization.
            if current >= datetime.fromisoformat(record['expires_at']):
                raise HTTPException(410, 'Session expired; start a new session without session_id')
        elif session_id:
            # Do not let callers claim arbitrary identifiers or revive missing ones.
            raise HTTPException(404, 'Session not found; start without session_id')
        else:
            record = {'session_id': identifier, 'owner': identity, 'created_at': current.isoformat(),
                      'expires_at': (current + timedelta(seconds=int(bounded_timeout_seconds('AGENT_SESSION_MAX_SECONDS', default=86400, maximum=2592000)))).isoformat()}
        record['last_seen_at'] = max(current.isoformat(), record.get('last_seen_at', ''))
        record['status'] = 'active'
        store.put(identifier, record)
        return record


def memory_id(record):
    return hashlib.sha256(f"{record['owner']}:{record['session_id']}".encode()).hexdigest()


def prune():
    """Remove expired session metadata; graph history has its own retention."""
    with store._connect() as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE depo_registry SET value=jsonb_set(value, '{status}', '\"idle\"'::jsonb) WHERE namespace=%s AND (value->>'last_seen_at')::timestamptz + %s * interval '1 second' <= now() AND value->>'status' IS DISTINCT FROM 'idle'", (store.namespace, int(bounded_timeout_seconds('AGENT_SESSION_IDLE_SECONDS', default=1800, maximum=86400))))
        cursor.execute("DELETE FROM depo_registry WHERE namespace=%s AND (value->>'expires_at')::timestamptz <= now()", (store.namespace,))

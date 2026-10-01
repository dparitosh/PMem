"""Durable companion sessions with credential ownership and fixed expiry."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry

store = PostgresRegistry('agentic_sessions')


def now():
    return datetime.now(timezone.utc)


def owner(request, actor):
    # Gateway principals remain stable across JWT renewal. Shared API keys share
    # a principal; individual user isolation requires individual credentials.
    authorization = request.headers.get('authorization', '')
    credential = '' if os.getenv('AUTH_MODE', 'token').lower() == 'entra' else (
        authorization[7:].strip() if authorization.lower().startswith('bearer ') else request.headers.get('x-api-key', '').strip())
    return hashlib.sha256(f'{actor}:{credential}'.encode()).hexdigest()


def open_session(request, actor, session_id=None):
    current = now()
    identity = owner(request, actor)
    identifier = str(session_id or uuid4())
    if len(identifier) > 128 or not identifier or any(ord(c) < 32 for c in identifier):
        raise HTTPException(422, 'Invalid session_id')
    record = store.get(identifier)
    if record:
        if record['owner'] != identity:
            raise HTTPException(403, 'Session belongs to another identity')
        idle = int(os.getenv('AGENT_SESSION_IDLE_SECONDS', '1800'))
        if (current >= datetime.fromisoformat(record['expires_at']) or
                current >= datetime.fromisoformat(record['last_seen_at']) + timedelta(seconds=idle)):
            raise HTTPException(410, 'Session expired; start a new session without session_id')
    elif session_id:
        # Do not let callers claim arbitrary identifiers or revive missing ones.
        raise HTTPException(404, 'Session not found; start without session_id')
    else:
        record = {'session_id': identifier, 'owner': identity, 'created_at': current.isoformat(),
                  'expires_at': (current + timedelta(seconds=int(os.getenv('AGENT_SESSION_MAX_SECONDS', '86400')))).isoformat()}
    record['last_seen_at'] = max(current.isoformat(), record.get('last_seen_at', ''))
    store.put(identifier, record)
    return record


def memory_id(record):
    return hashlib.sha256(f"{record['owner']}:{record['session_id']}".encode()).hexdigest()


def prune():
    """Remove expired session metadata; graph history has its own retention."""
    with store._connect() as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM depo_registry WHERE namespace = %s AND (value->>'expires_at')::timestamptz < now()", (store.namespace,))

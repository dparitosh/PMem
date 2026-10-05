"""Short-lived, revocable delegation of registered service credentials.

Only opaque session digests are persisted. API-key digests are snapshots,
so rotation or revocation invalidates the corresponding delegated scope.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

PREFIX = 'depo_session_'
NAMESPACE = 'browser_credential_sessions'


def identifier(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_session(admin_key, include_writes=False):
    from fastapi import HTTPException
    from .credentials import connection, verify_key
    actor = verify_key('ADMIN_API_KEY', admin_key)
    current = datetime.now(timezone.utc)
    expires = current + timedelta(minutes=15)
    token = PREFIX + secrets.token_urlsafe(48)
    with connection() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':depo-credentials-import',0))")
        cursor.execute('SELECT profile,salt,digest,expires_at,revoked FROM depo_api_credentials')
        rows = {row[0]: row for row in cursor.fetchall()}
        admin = rows.get('ADMIN_API_KEY')
        from .credentials import key_digest, PROFILES
        import hmac
        if (not admin or admin[4] or (admin[3] and admin[3] <= current)
                or not hmac.compare_digest(key_digest(admin[1], admin_key), admin[2])):
            raise HTTPException(403, 'Administrator key changed; sign in again')
        profiles = {name: row[2] for name, row in rows.items()
                    if name in PROFILES - {'ADMIN_API_KEY'} and not row[4]
                    and (not row[3] or row[3] > current)
                    and (include_writes or name == 'GRAPH_READ_TOKEN')}
        if 'GRAPH_READ_TOKEN' not in profiles:
            raise HTTPException(409, 'Register an active GRAPH_READ_TOKEN before connecting')
        if admin[3]:
            expires = min(expires, admin[3])
        record = {'actor': actor, 'expires_at': expires.isoformat(),
                  'admin_digest': admin[2], 'profiles': profiles}
        cursor.execute("DELETE FROM depo_registry WHERE namespace=%s AND (value->>'expires_at')::timestamptz <= now()", (NAMESPACE,))
        cursor.execute('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s::jsonb)',
                       (NAMESPACE, identifier(token), json.dumps(record)))
    return {'token': token, 'expires_at': expires.isoformat(), 'profiles': sorted(profiles)}


def verify_session(profile, token, current_digest):
    from fastapi import HTTPException
    from .credentials import connection
    if profile == 'ADMIN_API_KEY':
        raise HTTPException(403, 'Browser service sessions cannot administer credentials')
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT value FROM depo_registry WHERE namespace=%s AND key=%s', (NAMESPACE, identifier(token)))
            row = cursor.fetchone()
            cursor.execute("SELECT digest,expires_at,revoked FROM depo_api_credentials WHERE profile='ADMIN_API_KEY'")
            admin = cursor.fetchone()
    except Exception:
        raise HTTPException(503, 'Central browser session authority is unavailable') from None
    record = row[0] if row else None
    now = datetime.now(timezone.utc)
    try:
        expired = not record or datetime.fromisoformat(record['expires_at']) <= now
        if record and (not isinstance(record.get('profiles'), dict) or not isinstance(record.get('actor'), str)):
            raise ValueError('invalid session')
    except (TypeError, ValueError, KeyError, AttributeError):
        raise HTTPException(503, 'Central browser session record is invalid; reconnect in Admin') from None
    if expired:
        raise HTTPException(401, 'Browser service session expired; reconnect in Admin')
    if (not admin or admin[2] or (admin[1] and admin[1] <= now)
            or admin[0] != record.get('admin_digest')
            or record.get('profiles', {}).get(profile) != current_digest):
        raise HTTPException(403, 'Browser session scope is unavailable or credentials changed; reconnect in Admin')
    return record['actor']


def delete_session(token):
    from .credentials import connection
    if not isinstance(token, str) or not token.startswith(PREFIX) or len(token) > 4096:
        return
    with connection() as db, db.cursor() as cursor:
        cursor.execute('DELETE FROM depo_registry WHERE namespace=%s AND key=%s', (NAMESPACE, identifier(token)))

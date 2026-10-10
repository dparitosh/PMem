"""Short-lived, revocable delegation of registered service credentials.

Only opaque session digests are persisted. API-key digests are snapshots,
so rotation or revocation invalidates the corresponding delegated scope.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from .network import bounded_timeout_seconds

PREFIX = 'depo_session_'
NAMESPACE = 'browser_credential_sessions'


def access_seconds():
    return bounded_timeout_seconds('DEPO_BROWSER_SESSION_IDLE_SECONDS', default=900, minimum=60, maximum=900)


def identifier(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_session(admin_key, include_writes=False, include_maintenance=False):
    from fastapi import HTTPException
    from .credentials import connection, verify_key
    actor = verify_key('ADMIN_API_KEY', admin_key)
    current = datetime.now(timezone.utc)
    absolute = current + timedelta(seconds=bounded_timeout_seconds('DEPO_BROWSER_SESSION_MAX_SECONDS', default=28800, minimum=900, maximum=86400))
    expires = min(absolute, current + timedelta(seconds=access_seconds()))
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
        if include_maintenance:
            profiles['ADMIN_API_KEY'] = admin[2]
        if admin[3]:
            expires = min(expires, admin[3])
            absolute = min(absolute, admin[3])
        record = {'actor': actor, 'expires_at': expires.isoformat(),
                  'created_at': current.isoformat(), 'absolute_expires_at': absolute.isoformat(),
                  'admin_digest': admin[2], 'profiles': profiles}
        cursor.execute("DELETE FROM depo_registry WHERE namespace=%s AND (value->>'expires_at')::timestamptz <= now()", (NAMESPACE,))
        cursor.execute('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s::jsonb)',
                       (NAMESPACE, identifier(token), json.dumps(record)))
    return {'token': token, 'expires_at': expires.isoformat(), 'absolute_expires_at': absolute.isoformat(), 'profiles': sorted(profiles)}


def renew_session(token):
    from fastapi import HTTPException
    try:
        return _renew_session(token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Central browser session authority is unavailable; retry before session expiry') from None


def _renew_session(token):
    """Extend live delegation without re-entering keys or expanding its scopes.

    Row locking serializes renewal with logout. Legacy delegations without an
    absolute deadline may be used until expiry but cannot be extended.
    """
    from fastapi import HTTPException
    from .credentials import connection
    if not isinstance(token, str) or not token.startswith(PREFIX) or len(token) > 4096:
        raise HTTPException(401, 'A browser service session is required')
    current = datetime.now(timezone.utc)
    with connection() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('SELECT value FROM depo_registry WHERE namespace=%s AND key=%s FOR UPDATE', (NAMESPACE, identifier(token)))
        row = cursor.fetchone()
        record = row[0] if row else None
        try:
            expiry = datetime.fromisoformat(record['expires_at'])
            absolute = datetime.fromisoformat(record['absolute_expires_at'])
            profiles = record['profiles']
            if expiry.tzinfo is None or absolute.tzinfo is None or not isinstance(record.get('actor'), str) or not record['actor']:
                raise ValueError('invalid session metadata')
            if not isinstance(profiles, dict) or 'GRAPH_READ_TOKEN' not in profiles:
                raise ValueError('invalid scopes')
        except (TypeError, ValueError, KeyError):
            raise HTTPException(401, 'Reconnect in Admin to create a renewable session') from None
        if current >= expiry or current >= absolute:
            raise HTTPException(401, 'Browser service session expired; reconnect in Admin')
        cursor.execute('SELECT profile,digest,expires_at,revoked FROM depo_api_credentials')
        rows = {item[0]: item for item in cursor.fetchall()}
        admin = rows.get('ADMIN_API_KEY')
        if not admin or admin[3] or (admin[2] and admin[2] <= current) or admin[1] != record.get('admin_digest'):
            raise HTTPException(403, 'Browser session scope is unavailable or credentials changed; reconnect in Admin')
        for profile, digest in profiles.items():
            active = rows.get(profile)
            if not active or active[3] or (active[2] and active[2] <= current) or active[1] != digest:
                raise HTTPException(403, 'Browser session scope is unavailable or credentials changed; reconnect in Admin')
        expiry = min(absolute, current + timedelta(seconds=access_seconds()))
        if admin[2]:
            expiry = min(expiry, admin[2])
        record.update(expires_at=expiry.isoformat(), last_renewed_at=current.isoformat())
        cursor.execute('UPDATE depo_registry SET value=%s::jsonb WHERE namespace=%s AND key=%s', (json.dumps(record), NAMESPACE, identifier(token)))
    return {'token': token, 'expires_at': expiry.isoformat(), 'absolute_expires_at': absolute.isoformat(), 'profiles': sorted(profiles)}


def verify_session(profile, token, current_digest, *, maintenance=False):
    from fastapi import HTTPException
    from .credentials import connection
    if profile == 'ADMIN_API_KEY' and not maintenance:
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
        if record and record.get('absolute_expires_at'):
            expired = expired or datetime.fromisoformat(record['absolute_expires_at']) <= now
        if record and (not isinstance(record.get('profiles'), dict) or not isinstance(record.get('actor'), str)):
            raise ValueError('invalid session')
    except (TypeError, ValueError, KeyError, AttributeError):
        raise HTTPException(503, 'Central browser session record is invalid; reconnect in Admin') from None
    if expired:
        raise HTTPException(401, 'Browser service session expired; reconnect in Admin')
    if maintenance:
        if profile != 'ADMIN_API_KEY':
            raise HTTPException(403, 'Invalid maintenance scope')
        current_digest = admin[0] if admin else None
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

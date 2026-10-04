"""Central API-key authority. No plaintext keys are stored or returned."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

PROFILES = frozenset({
    'GRAPH_READ_TOKEN', 'INGESTION_WRITE_TOKEN', 'DATA_JOB_EXECUTION_TOKEN',
    'DATA_JOB_APPROVAL_TOKEN', 'DATA_PRODUCT_APPROVAL_TOKEN', 'AGENTIC_APPROVAL_TOKEN',
    'ARTIFACT_RETENTION_APPROVAL_TOKEN', 'CEIM_PUBLISH_APPROVAL_TOKEN',
    'GRAPH_PUBLICATION_TOKEN', 'CATALOG_SERVICE_TOKEN', 'CEIM_RESOLUTION_APPROVAL_TOKEN',
    'SPEED_PATH_APPROVAL_TOKEN', 'SPEED_EVENT_TOKEN', 'SPARQL_FEDERATION_APPROVAL_TOKEN',
    'VOCABULARY_APPROVAL_TOKEN', 'ONTOLOGY_APPROVAL_TOKEN', 'ADMIN_API_KEY',
})


def uses_postgres():
    mode = os.getenv('DEPO_CREDENTIAL_STORE', 'environment').strip().lower()
    if mode not in {'environment', 'postgres'}:
        raise RuntimeError('DEPO_CREDENTIAL_STORE must be environment or postgres')
    return mode == 'postgres'


def key_digest(salt, key):
    # API keys must have at least 32 random characters; these are not passwords.
    return hashlib.sha256(bytes.fromhex(salt) + key.encode('utf-8')).hexdigest()


def connection():
    from backend.mesh_store import PostgresRegistry
    return PostgresRegistry('api_credentials')._connect()


def verify_key(profile, supplied):
    from fastapi import HTTPException
    if profile not in PROFILES:
        raise HTTPException(422, 'Unsupported credential profile')
    if not isinstance(supplied, str) or not supplied or len(supplied) > 4096:
        raise HTTPException(403, 'Required API key is missing or invalid')
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT salt, digest, actor, expires_at, revoked FROM depo_api_credentials WHERE profile=%s', (profile,))
            row = cursor.fetchone()
    except Exception:
        raise HTTPException(503, 'Central credential authority is unavailable; check database migration and connectivity') from None
    if not row:
        raise HTTPException(503, f'{profile} has not been registered in the central credential authority')
    salt, digest, actor, expiry, revoked = row
    try:
        matches = hmac.compare_digest(key_digest(salt, supplied), digest)
    except (TypeError, ValueError):
        raise HTTPException(503, 'Central credential record is invalid; contact the administrator') from None
    if revoked or not matches:
        raise HTTPException(403, f'Invalid or revoked {profile}')
    if expiry and expiry <= datetime.now(timezone.utc):
        raise HTTPException(401, 'API key has expired; contact the administrator')
    return actor


def validate_registration(profile, key, actor, expires_at=None):
    if profile not in PROFILES:
        raise ValueError('Unsupported credential profile')
    key, actor = str(key).strip(), str(actor).strip()
    if len(key) < 32 or len(key) > 4096 or key.startswith('<'):
        raise ValueError('Use a random API key with 32-4096 characters')
    if not actor or len(actor) > 200:
        raise ValueError('A server-assigned actor of 1-200 characters is required')
    if expires_at and (expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc)):
        raise ValueError('Expiry must be a future timezone-aware timestamp')
    return key, actor


def register_key(profile, key, actor, expires_at=None, *, bootstrap=False, audit_actor=None, db=None):
    key, actor = validate_registration(profile, key, actor, expires_at)
    salt = secrets.token_hex(32)
    def write(connection):
        with connection.transaction(), connection.cursor() as cursor:
            statement = ('INSERT INTO depo_api_credentials(profile,salt,digest,actor,expires_at) VALUES (%s,%s,%s,%s,%s) '
                         + ('ON CONFLICT(profile) DO NOTHING' if bootstrap else
                            'ON CONFLICT(profile) DO UPDATE SET salt=excluded.salt,digest=excluded.digest,actor=excluded.actor,expires_at=excluded.expires_at,revoked=false,updated_at=now()'))
            cursor.execute(statement, (profile, salt, key_digest(salt, key), actor, expires_at))
            if cursor.rowcount:
                cursor.execute('INSERT INTO depo_api_credential_events(profile,action,actor) VALUES (%s,%s,%s)',
                               (profile, 'bootstrap' if bootstrap else 'rotate', audit_actor or actor))
    if db is not None:
        write(db)
    else:
        with connection() as owned:
            write(owned)


def bootstrap_environment(db):
    if not uses_postgres():
        return
    for profile in sorted(PROFILES):
        with db.cursor() as cursor:
            cursor.execute('SELECT 1 FROM depo_api_credentials WHERE profile=%s', (profile,))
            if cursor.fetchone():
                continue  # Reinstall must not reset rotated, expired or revoked keys.
        key = os.getenv(profile, '').strip()
        if not key:
            continue
        expiry = os.getenv(profile + '_EXPIRES_AT') or os.getenv('DEPO_TOKEN_EXPIRES_AT')
        expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00')) if expiry else None
        register_key(profile, key, os.getenv(profile + '_ACTOR') or 'deployment-bootstrap', expiry, bootstrap=True, db=db)
    with db.cursor() as cursor:
        cursor.execute("SELECT profile FROM depo_api_credentials WHERE profile IN ('ADMIN_API_KEY','GRAPH_READ_TOKEN')")
        if {row[0] for row in cursor.fetchall()} != {'ADMIN_API_KEY', 'GRAPH_READ_TOKEN'}:
            raise RuntimeError('Central credential bootstrap requires ADMIN_API_KEY and GRAPH_READ_TOKEN in the selected environment file')

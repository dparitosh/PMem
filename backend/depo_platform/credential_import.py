"""Apply selected root-file API credentials atomically; never print key values."""
import argparse
import json
import sys
from datetime import datetime
from .credentials import PROFILES, connection, key_digest, register_key, uses_postgres, validate_registration
import hmac


class ImportValidationError(ValueError):
    """Messages safe to expose without configuration values."""


def apply_values(values, replace=False):
    prepared = []
    for profile in sorted(PROFILES):
        key = values.get(profile, '').strip()
        if not key:
            continue
        expiry = values.get(profile + '_EXPIRES_AT') or values.get('DEPO_TOKEN_EXPIRES_AT')
        try:
            expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00')) if expiry else None
        except ValueError:
            raise ImportValidationError(f'Invalid expiry for {profile}; use a future ISO timestamp with timezone') from None
        actor = values.get(profile + '_ACTOR') or 'deployment-bootstrap'
        try:
            key, actor = validate_registration(profile, key, actor, expiry)
        except ValueError as exc:
            raise ImportValidationError(f'{profile}: {exc}') from None
        prepared.append((profile, key, actor, expiry))
    if not prepared:
        raise ImportValidationError('The selected file contains no application API keys')
    results = []
    with connection() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':depo-credentials-import',0))")
        for profile, key, actor, expiry in prepared:
            cursor.execute('SELECT salt,digest,revoked,actor,expires_at FROM depo_api_credentials WHERE profile=%s FOR UPDATE', (profile,))
            existing = cursor.fetchone()
            if existing and not replace:
                if existing[2] or existing[3] != actor or existing[4] != expiry or not hmac.compare_digest(key_digest(existing[0], key), existing[1]):
                    raise ImportValidationError(f'{profile} differs from the central key/metadata or is revoked. Review the selected file, then use -ReplaceExisting only for deliberate rotation.')
                results.append({'profile': profile, 'status': 'unchanged'})
                continue
            register_key(profile, key, actor, expiry, db=db, audit_actor='deployment-import', bootstrap=not replace)
            # Insert-only default also protects against writers that do not use
            # the application advisory lock. Never silently overwrite a key.
            cursor.execute('SELECT salt,digest,revoked,actor,expires_at FROM depo_api_credentials WHERE profile=%s FOR UPDATE', (profile,))
            actual = cursor.fetchone()
            if not actual or actual[2] or actual[3] != actor or actual[4] != expiry or not hmac.compare_digest(key_digest(actual[0], key), actual[1]):
                raise ImportValidationError(f'{profile} changed concurrently. The batch was rolled back; retry after reviewing the central profile.')
            results.append({'profile': profile, 'status': 'replaced' if existing else 'created'})
        cursor.execute("SELECT profile FROM depo_api_credentials WHERE profile IN ('ADMIN_API_KEY','GRAPH_READ_TOKEN') AND revoked=false AND (expires_at IS NULL OR expires_at > now())")
        if {row[0] for row in cursor.fetchall()} != {'ADMIN_API_KEY', 'GRAPH_READ_TOKEN'}:
            raise ImportValidationError('An active ADMIN_API_KEY and GRAPH_READ_TOKEN must exist after import. Add missing profiles to the selected file; no batch changes were applied.')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list-profiles', action='store_true')
    parser.add_argument('--replace-existing', action='store_true')
    args = parser.parse_args()
    if args.list_profiles:
        print(json.dumps(sorted(PROFILES)))
        return 0
    try:
        if not uses_postgres():
            raise ImportValidationError('Set DEPO_CREDENTIAL_STORE=postgres in the selected root environment file')
        values = json.loads(sys.stdin.buffer.read().decode('utf-8'))
        results = apply_values(values, args.replace_existing)
        print(json.dumps({'status': 'ok', 'profiles': results}))
        return 0
    except ImportValidationError as exc:
        # Validation messages contain profile names only, never values.
        print(json.dumps({'status': 'failed', 'action': str(exc)}))
    except Exception:
        print(json.dumps({'status': 'failed', 'action': 'Credential import failed and was rolled back. Verify migration 008, database connectivity and table privileges.'}))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

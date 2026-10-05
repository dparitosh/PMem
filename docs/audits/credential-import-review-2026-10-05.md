# Credential import and Admin table audit — 2026-10-05

Scope: apply-depo-service-credentials.ps1, credential_import.py, shared register_key, Admin table/CSS and package validation. No customer VM, live PostgreSQL or browser renderer was available.

## Findings fixed

- P1: an insert checked as missing could race with Admin registration and be overwritten by the import default. Import and registration now share a schema-scoped advisory lock; import additionally uses insert-only registration unless -ReplaceExisting is explicit and verifies the saved record while holding a row lock. A conflicting concurrent record causes batch rollback.
- P2: a first import could report success without an active administrative/read profile. The batch now requires active ADMIN_API_KEY and GRAPH_READ_TOKEN records before committing.
- P2: token import under Entra configuration was misleading. The wrapper now rejects an explicitly non-token AUTH_MODE.

## Verified properties

Selected-file values only; 17 application profiles allowlisted; connector/database secrets excluded from stdin; no secrets in arguments or result JSON. Validation runs before writes. One outer transaction covers the entire batch and audit events. Default import preserves identical keys/actors/expiry and refuses differences or revocations. Explicit replacement rotates/revives records. Native stdin uses UTF-8 and restores PowerShell OutputEncoding. Unexpected database errors return a fixed safe message. Import does not install dependencies, start HTTP services, change the root environment file or inject browser keys.

The Admin table has semantic row/column headers, accessible key labels, theme colors, sticky headings and horizontal/vertical scrolling. The row-based test lookup was updated. Registration still requires explicit administrator credentials and confirmation; frontend tab keys remain memory-only.

## Validation

18 focused backend tests passed, package integrity passed (51 PowerShell files; 23 documented paths), real PowerShell-to-Python UTF-8 stdin check passed. Live SQL locking/rollback and visual browser acceptance remain pending; offline mocked transactions do not certify those environments.

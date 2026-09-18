# Release Hygiene Audit

## Customer release entry points

Use the supported PowerShell scripts from the repository root. `-NoProfile` and
the process-only execution-policy override make the commands work on locked-down
Windows workstations without changing the machine policy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\start-depo-services.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-release.ps1 -Bootstrap
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\stop-depo-services.ps1
```

## Runtime expectations

- Node.js: 20 LTS or newer, npm 10+
- Backend virtual environment: `backend/.dt_venv`
- Frontend dependencies: `frontend/node_modules`
- Backend API default: `http://<host>:8000`
- Frontend default: `http://<host>:3000`

## Folders to include in product release

- `backend/`
- `frontend/`
- `docs/`
- `tools/admin/`
- `tools/import/` helper scripts if needed by support
- `standalone/ontology_agentic_service/` only if releasing companion service

## Folders that are reference, generated, or legacy

Do not package these into the customer runtime unless explicitly needed:

- `external/sirius-web/`: reference clone only; not part of runtime app
- `tools/legacy_root_scripts/`: removed from active tree; historical debug helpers are not part of the runtime release
- `audit-shots/`, `.pytest_cache/`, `.mypy_cache/`, `logs/`, `uploads/`, `ontology_uploads/`: generated/runtime artifacts
- `_restore_ingest/`: recovery data, not runtime code

## Current installation script audit

- `install-depo.ps1` creates the backend virtual environment, installs the single
  requirements file, and runs `npm ci` for the frontend.
- `start-depo-services.ps1` validates the service manifest, PostgreSQL schema,
  and configured service endpoints before starting the local processes.
- `stop-depo-services.ps1` resolves virtual-environment wrapper processes before
  stopping child Python workers, avoiding stale port listeners.
- OSLC provider and TRS URLs use `OSLC_BASE_URL` when configured; otherwise they
  derive from `APP_HOST`/`APP_PORT` so customer VM links do not silently point to
  localhost.

## Known cleanup recommendation

`external/sirius-web/` is large and untracked. It should be removed from release packaging or deleted after confirmation if no longer needed as reference material.

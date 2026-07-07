# Release Hygiene Audit

## Customer release entry points

Use these scripts from the repository root:

```bat
setup.bat
start_backend.bat
start_frontend.bat
stop_backend.bat
stop_frontend.bat
```

`setup.bat` is a root wrapper over `backend/setup.bat` so customer users do not need to know the backend folder layout.

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

- `start_frontend.bat` uses local `node_modules/.bin/react-scripts.cmd`, avoiding global `react-scripts` failures.
- `start_backend.bat` detects existing port listener and avoids duplicate port binding.
- `start_backend.bat` sets `ALLOWED_ORIGINS` for localhost, 127.0.0.1, and LAN host.`r`n- OSLC provider and TRS URLs use `OSLC_BASE_URL` when configured; otherwise they derive from `APP_HOST`/`APP_PORT` so customer VM links do not silently point to localhost.
- `backend/setup.bat` installs backend and frontend dependencies and now has a root wrapper.

## Known cleanup recommendation

`external/sirius-web/` is large and untracked. It should be removed from release packaging or deleted after confirmation if no longer needed as reference material.

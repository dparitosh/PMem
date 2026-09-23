# Release Hygiene Audit

For the cleanup inventory and outstanding release work, see
[repository maintenance](REPOSITORY_MAINTENANCE.md). The authoritative
installation sequence is the [single installation guide](../INSTALLATION.md).

## Customer release entry points

Follow the [single installation guide](../INSTALLATION.md) from the project
root: check prerequisites, prepare server and public browser configuration,
install/build, validate configuration, start services, validate endpoints and
perform release preflight. Configure browser URLs before the combined installer
builds the frontend. Shutdown is a separate operational action.

The guide supplies the executable commands and profile-specific options. This
audit deliberately does not duplicate an installation command sequence.

## Runtime expectations

- Node.js: 24+, npm 10.2+
- Python: 3.11
- Backend virtual environment: `backend/.dt_venv`
- Frontend dependencies: `frontend/node_modules`
- Backend services: ports 8010–8019 in `infra/deployment/services.json`
- Frontend default: `http://<host>:3000`

## Folders to include in product release

- `backend/`
- `frontend/`
- `docs/`
- `infra/` and `config/`
- Required semantic assets and shared modules in `data/`, `ontology/`, `mapping/`
  and `parsers/`, selected according to the deployed features
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

- `install-depo-windows.ps1` is the customer installation entry point. It calls
  the dependency stage, validates configuration, migrates PostgreSQL, validates
  Neo4j and optional Spark, starts the services, and runs release preflight.
  `install-depo.ps1` remains the internal dependency stage; `-Development`
  includes test dependencies and `-CheckPrerequisites` performs checks only.
- `start-depo-services.ps1` validates the service manifest, PostgreSQL schema,
  and configured service endpoints before starting the local processes.
- `stop-depo-services.ps1` resolves virtual-environment wrapper processes before
  stopping child Python workers, avoiding stale port listeners.
- OSLC provider and TRS URLs use `OSLC_BASE_URL` when configured; otherwise they
  derive from `APP_HOST`/`APP_PORT` so customer VM links do not silently point to
  localhost.

## Reference material

Exclude `external/` from runtime packaging. Recovery and customer inputs are
retained because their disposability cannot be inferred from source references.

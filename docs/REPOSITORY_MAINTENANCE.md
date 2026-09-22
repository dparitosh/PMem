# Repository maintenance

## Directory ownership

| Directory | Contents |
| --- | --- |
| `backend/` | API services, shared Python modules and regression tests |
| `frontend/` | React application, lockfile, UI tests and public configuration template |
| `config/` | Server deployment template and optional Spark settings |
| `infra/` | Installation, service lifecycle, deployment and integration automation |
| `scripts/` | Format conversion and graph-loading command-line tools |
| `tools/` | Operator diagnostics, maintenance and manual integration utilities |
| `docs/` | Maintained documentation and reference material; screenshots in `assets/` |
| `deliverables/` | Office documents and presentation deliverables |
| `data/`, `ontology/`, `mapping/`, `parsers/` | Standards, semantic assets and supporting application modules |
| `plugins/`, `standalone/` | Optional separately packaged integrations |
| `external/`, `_restore_ingest/` | Local reference/recovery material; exclude from releases |

Keep generated logs, uploads, test reports and caches out of source control.
Do not delete customer evidence, ontology caches, engineering inputs or standards
based solely on filename, age or duplicate-looking content.

## Development checks

Use Python 3.11 for local development and validation. Install
`backend/requirements-dev.txt` for development; production installation uses
`backend/requirements.txt`. Node and npm constraints are in
`frontend/package.json`; frontend installation uses `npm ci`.

From the repository root:

Validation runs locally; this application does not use GitHub Actions.

```powershell
backend\.dt_venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
backend\.dt_venv\Scripts\python.exe -m pytest
powershell -NoProfile -ExecutionPolicy Bypass -File infra/deployment/test-config-generation.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/windows/test-install-prerequisites.ps1
cd frontend
npm.cmd test
npm.cmd run build
```

The default pytest configuration includes backend service parser tests. Manual
live scripts excluded by `backend/tests/conftest.py` require explicit setup and
can mutate external databases. Optional plugins and standalone packages have
their own documented test suites.

## Cleanup record

The September 2026 cleanup removed the unused backend npm lockfile, obsolete
frontend launcher, duplicate cleanup wrapper, three legacy environment
templates and generated verification results. Deployment/Spark templates moved
to `config/`; root presentations and the screenshot moved to their owned folders.
The [manifest](repository-cleanup-manifest.json) records paths and SHA-256 hashes.
It is an inventory, not a backup.

Validation performed: infrastructure PowerShell syntax checks, isolated
configuration generation (default path, distinct bootstrap secrets, admin key
and overwrite protection), and modified Python syntax. Full backend tests and
frontend build were not run in this checkout because application dependencies
were absent. Install development dependencies and run the local commands above
to repeat validation. No live database or customer deployment was changed.

Active compatibility code remains: `main.py`, `backend/main.py`,
`backend/Services`, `backend/core` and `backend/routes` still have consumers.
Follow the [retirement boundary](../backend/legacy/README.md) before removing
them. `test_upload.xsd` remains an input to a manual API smoke test.

## Remaining release work

- Backend runtime requirements use version ranges; a tested dependency lock and
  dependency vulnerability review are still needed for reproducible releases.
- Historical design/audit documents are reference material, not installation
  authority. Use the deployment guide and service manifest for operations.
- Manual support scripts still need incremental migration to service APIs and
  consistent argument/configuration handling.
- Customer deployment acceptance requires live PostgreSQL, Neo4j, authentication,
  gateway and endpoint validation; static checks alone do not certify a release.
- This supplied directory has no Git metadata. Perform release review in a
  version-controlled checkout before establishing a production baseline.

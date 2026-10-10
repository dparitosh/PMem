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
| `deliverables/` | Office documents and presentations; historical local test logs are generated evidence |
| `release-evidence/` | Ignored local validation output, grouped by run date |
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

Historical cleanup statements below describe their original validation run. Current validation and acceptance status is maintained in [the audit index](audits/README.md).

The September 2026 cleanup removed the unused backend npm lockfile, obsolete
frontend launcher, duplicate cleanup wrapper, three legacy environment
templates and generated verification results. Deployment/Spark templates moved
to `config/`; root presentations and the screenshot moved to their owned folders.
The [manifest](repository-cleanup-manifest.json) records paths and SHA-256 hashes.
It is an inventory, not a backup.

The subsequent whole-tree trace removed 83 macOS archive metadata files, stale
generated code-graph reports, an excluded duplicate Playwright audit, two
superseded Cypher chain copies, an unmounted ingestion router, an unreferenced
vendor developer sample that required missing compiled binaries, duplicated
ontology assets, CRA-only public files, branch review notes, and superseded
installation/audit snapshots. Generated code-graph output is now ignored and
must be regenerated locally. `INSTALLATION.md` remains the only customer
installation procedure.

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

## Reviewed cleanup — 2026-10-10

Removed an exact duplicate readiness test, a superseded service-start copy that
bypassed the current Windows runtime wrapper, and the unreachable SVG diagram
component/barrel. The active React Flow diagram remains in use and is retained.
The follow-up trace removed two unreferenced one-off Neo4j probes superseded by
the maintained infrastructure diagnostic, and four intermediate architecture
decks superseded by the consolidated 31-slide analytics release. Their slide
content differences were inspected before removal.
Removed reviewed presentation intermediates, superseded patch ZIPs and their
old patch deployment instructions, plus generated browser/build review outputs.
The [cleanup manifest](repository-cleanup-2026-10-10.json) records every deleted
file's SHA-256 and size; it is an inventory, not a backup. Current installation
authority remains INSTALLATION.md and the maintained infrastructure scripts.

Retained customer configuration, engineering inputs, ontology caches, standards,
final presentations, document-generation sources, optional integrations and
compatibility modules with active consumers. An old filename or lack of a static
Python import alone is insufficient evidence to remove dynamically loaded code,
operator tools or customer data.

## Remaining release work

- `backend/requirements-lock.txt` now provides the deployment lock. Validate its
  supported runtime/platform, artifacts and vulnerability/license review for
  each release; development requirement ranges are not the deployment lock.
- Historical design documents are reference material, not installation
  authority. Use the deployment guide and service manifest for operations.
- Manual support scripts still need incremental migration to service APIs and
  consistent argument/configuration handling.
- Customer deployment acceptance requires live PostgreSQL, Neo4j, authentication,
  gateway and endpoint validation; static checks alone do not certify a release.
- Establish a signed or tagged production baseline only after customer
  acceptance evidence is attached to the version-controlled release commit.

## Customer vanilla release cleanup (2026-10-10)

Removed unused backend/STP and backend/Data demonstration inputs, the local
_restore_ingest recovery copies, temporary review dependencies/test output,
root Vite cache and Python bytecode caches. Removed the five reviewed cached
TTL outputs after the user requested a vanilla customer installation. Their
previous hash verification and cleanup manifest retain provenance; manifests
are not backups. Current regression test source and production semantic assets
remain. Persisted content-addressed artifacts and uploads were not erased:
they can have live database references and are excluded from customer packaging.

The cleanup recorded 4,104 files and 215,224,275 bytes in
customer-release-cleanup-2026-10-10.json. Every recorded path was verified absent.
Windows denied access to .pytest_cache; it remains locally and is excluded from
the release. tools/build_customer_release.py creates an installation source ZIP
with a file hash manifest and without local credentials, runtime data or test
outputs. Test source remains in the repository for maintenance.

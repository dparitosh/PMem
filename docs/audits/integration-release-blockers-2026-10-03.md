# Integration and release audit — 2026-10-03

This audit does not assume a target bug count. Severity follows demonstrated impact. Code traces verify mounted router dependencies, not just endpoint decorators. No live customer VM, PostgreSQL, Neo4j, APIM or browser workflow was exercised.

## Confirmed findings

| ID | Priority | Code | Trigger and impact | Required fix |
|---|---|---|---|---|
| INT-01 | P1 | backend/data_pipeline_service/router.py:create_job_definition; app.py router mount | POST /api/v1/pipeline/jobs/definitions accepts an unauthenticated draft writer in token mode. Caller supplies owner and can reserve immutable baseline IDs/versions, poison drafts and exhaust registry storage. Approval/execution remain protected; this is not arbitrary code execution. | Require a governed definition-author credential; derive creator identity server-side; update frontend metadata and baseline seeder. |
| INT-02 | P1 | backend/data_pipeline_service/job_definitions.py:create; backend/mesh_store.py:put_many | Two creators read missing key before either upserts. ON CONFLICT DO UPDATE overwrites the first supposedly immutable job definition; an approval interleaving can be overwritten by the late creator. | Atomic INSERT-only creation with conflict mapped to HTTP 409; concurrency regression against PostgreSQL. |
| INT-03 | P2 | infra/windows/start-depo-services.ps1:recorded-process reuse and readiness | A live existing service with unchanged CORS is reused after GRAPH_READ_TOKEN changes. Readiness succeeds; frontend rejects the new key. | Verify authenticated access using current configuration or detect process configuration revision before accepting reused services. |
| INT-04 | P2 | infra/windows/install-depo-windows.ps1:frontend preflight | Installer receives custom -EnvFile but does not pass it as -RootEnvFile to frontend validator. Validator reads default .env.local, passing/rejecting the wrong routing settings. | Propagate selected root environment through every frontend validation caller. |
| INT-05 | P2 | infra/windows/install-depo-windows.ps1:PostgreSQL connectivity stage | Connectivity/migration occur before start-depo-services owns local PostgreSQL service/portable startup. A configured stopped local database fails initial installation before its startup stage. | Provision/start selected local database before connectivity; external mode remains customer managed. |
| INT-06 | P2 gap | certify-depo-release.ps1:Resolve-Evidence | Evidence acceptance checks file existence/nonempty only; a file recording failed or unrelated acceptance is still recorded as supplied evidence. This script records diagnostics plus supplied files, not verified successful workflow acceptance. | Structured evidence contract tied to deployment/release and reviewed passing outcomes, or explicitly label unvalidated attachments. |
| INT-07 | P2 gap | deployment endpoint validation and current regression coverage | Health/OpenAPI/OData validation does not authenticate real read/write workflows. Passing simulated gateway tests does not prove actual gateway policies, browser credentials or job materialization. | Run read-only authenticated service probes plus isolated governed workflow acceptance and real browser tests before customer certification. |

Ontology policy POSTs were initially suspected, then excluded: ontology_service/app.py mounts the router with Depends(_modeling_identity), which enforces write identity. No unprotected-policy finding remains.

## Twenty integration checks: honest coverage status

| Check | Status |
|---|---|
| Service manifest and package paths | Previously passed package validator |
| Local/gateway/legacy routing resolver | Offline script passed this audit |
| Invalid routing rejection | Offline script passed this audit |
| Frontend configuration validation | Offline script passed this audit |
| Ten gateway health/OpenAPI routes | Simulated HTTP passed; live pending |
| Gateway OPTIONS without credentials | Simulated HTTP passed; live pending |
| Gateway protected graph query | Simulated HTTP passed; live pending |
| Graph key forwarding from browser | Code reviewed; live browser pending |
| API contract refresh preservation | Previously passed Node regression |
| Nested gateway root ownership | Previously passed Node regression |
| OpenAPI streaming bounds | Previously passed Node regression |
| Browser credential build policy | Previously passed Node regression |
| Frontend stale build receipt | Previously tested generated inputs; full Vite build pending |
| Pipeline draft creation authorization | Failed code review INT-01 |
| Immutable job creation concurrency | Failed code review INT-02 |
| Existing service key changes | Failed code review INT-03 |
| Custom installer environment propagation | Failed code review INT-04 |
| Local PostgreSQL stopped-start sequence | Failed code review INT-05 |
| Evidence content validation | Gap INT-06 |
| End-to-end browser/XSD/job/database workflow | Pending INT-07 |

This documents two confirmed P1 defects, three P2 defects and two testing/acceptance gaps; it does not assert twenty P1 bugs or customer-release readiness. No code changed in this audit.


## Implementation follow-up

INT-01/02: definition creation requires DATA_JOB_APPROVAL_TOKEN, assigns server actor as owner, and uses atomic INSERT ON CONFLICT DO NOTHING RETURNING; conflicts are HTTP 409. Seeder credentials/routing updated; OpenAPI introspection advertises the token via the existing authorization helper.

INT-03: shared protected /auth/access added to all service apps; token-mode startup/deployment validation probes it with the selected read key and fails stale-key reuse explicitly.

INT-04/05: frontend preflight receives selected RootEnvFile; local PostgreSQL startup extracted into one helper and runs before installer connectivity/migration. External mode does not control remote PostgreSQL and helper does not overwrite unrelated Spark CLI settings.

INT-06: certification validates structured passing evidence by type, commit, deployment, reviewer, checks and non-future timezone-qualified timestamp. Nonempty arbitrary files no longer qualify. Evidence truthfulness remains a human acceptance responsibility.

INT-07: read authentication checks broadened; dedicated Python/PowerShell regressions added and existing test fixtures adjusted. Live customer browser/APIM and PostgreSQL concurrency verification remain pending; no production certification is claimed.

Validation: 23 focused Python checks passed; PowerShell external/service-mode selection and evidence pass/failure/wrong-commit tests passed with simulated services; package validator passed with 48 scripts and 8 migrations. Full dependency-bearing pytest/FastAPI/browser suite was not run. Commit and push status is recorded in Git.

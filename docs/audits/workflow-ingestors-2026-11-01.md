# Workflow and Semantica ingestor audit

Date: 1 November 2026. Source branch: `codex/windows-setup-audit-fixes`.

The shared workflow presentation now has explicit responsibilities across the six requested workspaces, reconnect-safe task controls and a single polling loop. Existing pipeline workers, agent workflows and owning-service approvals remain authoritative. This is a focused shared-layer refactor, not a replacement of all six page implementations.

## Findings and corrections

| Finding | Severity | Root cause and reproduction | Correction |
| --- | --- | --- | --- |
| Task history survives delegated-session replacement | High | `frontend/src/Components/PageTaskWorkspace.js:50` omitted `depo:session-replaced`. Replace access while a task is selected; earlier controls could remain visible. | Replacement aborts reads, closes task scope and invalidates the control generation. |
| Late control acknowledgement updates another selection | High | A pending resume/pause/cancel response had no generation check. Change access, route or task before the response resolves. | Generation fence and synchronous submission lock; stale acknowledgements cannot update notices or refresh another selection. |
| Aborted refresh schedules another poll | Medium | The old history request always scheduled its next timer even after a newer refresh aborted it. Rapid refresh could create competing loops. | Only a current, unaborted request schedules the next poll. A fake-timer regression verifies one poll after overlapping requests. |
| Loading appears as empty history | Medium | Initial empty rows rendered as successful empty history during retrieval. | Separate loading status and successful empty state. |
| Lazy acquisition dependency absent in isolated pipeline runtime | High | Pipeline locks intentionally omit Semantica to keep local ML out. `_worker_command` used pipeline Python, so REST lazy import would fail despite successful OpenAPI import. | Reuse the existing ontology runtime for the bounded acquisition child in isolated mode. Add actual acquisition-child smoke checks to shared and isolated installation. Keep pipeline locks unchanged. |
| Library availability confused with PMem connector support | Medium | Only REST had a direct Semantica acquisition adapter and configurable Admin registration. | Authenticated inventory endpoint and Admin support table explicitly classify all 17 types. No unsupported connector is presented as executable. |
| Fresh EmailIngestor import fails | Medium, upstream and unintegrated | A clean Python subprocess importing `EmailIngestor` raises `AttributeError: module 'email' has no attribute 'message'` in installed Semantica 0.6.7. | PMem now imports the missing stdlib prerequisite through its allowlisted lazy loader. A fresh-process regression passes without patching third-party files. No Email acquisition adapter is exposed or enabled. |

## Ingestor inventory

Import checks used a separate process per class in the installed shared Python runtime, with a 15-second budget. Import success does not establish configured external SDKs, source connectivity, safe acquisition or PMem integration.

| Semantica ingestor | Fresh import | Admin configuration and PMem execution | PostgreSQL connector registration | Installation |
| --- | --- | --- | --- | --- |
| FileIngestor | Pass | No generic Semantica adapter; existing Import file workflows | None for this class | Shared Semantica; native parser profiles separate |
| WebIngestor | Pass | Not connected | None | Optional adapter/dependencies not provisioned as a PMem connector |
| ParquetIngestor | Pass | Not connected | None | Optional adapter/dependencies not provisioned as a PMem connector |
| XMLIngestor | Pass | Native engineering XML import and approved XML analytics; not this generic class | None for this class; native run/analytics tables separate | Existing XML parser profiles |
| RESTIngestor | Pass | Admin Data sources; preview and approved `rest-source-ingest` worker job | `depo_registry`, namespace `rest_sources` | Shared Semantica, or existing ontology runtime in isolated mode |
| PublicAPIIngestor | Pass | Not connected; allowed public endpoints can use the REST adapter within its limits | None for this class | Optional adapter not provisioned |
| DBIngestor | Pass | Not connected; existing PostgreSQL application persistence is not DBIngestor acquisition | None | Optional source DB drivers not provisioned as a PMem connector |
| DatabricksIngestor | Pass | Not connected | None | Optional SDK and adapter not provisioned |
| SnowflakeIngestor | Pass | Not connected | None | Optional SDK and adapter not provisioned |
| EmailIngestor | Direct import fails; PMem compatibility loader passes | Not connected; class import is repaired, acquisition remains unimplemented | None | No email adapter enabled |
| FeedIngestor | Pass | Not connected | None | Optional adapter/dependencies not provisioned |
| MCPIngestor | Pass | Not connected; existing agent MCP tools are distinct from ingestion | None | Optional ingestion adapter not provisioned |
| OntologyIngestor | Pass | Native RDF/OWL lifecycle exists; RDFLib parsing and Semantica validation do not call this generic ingestor | None for this class | Existing ontology dependency runtime |
| RepoIngestor | Pass | Not connected; Code Audit is a separate deterministic workflow | None | Optional acquisition adapter not provisioned |
| StreamIngestor | Pass | Not connected; existing bounded speed-event API is a separate path | None for this class | No Kafka/RabbitMQ/cloud broker connector provisioned |
| ArrowIngestor | Pass | Not connected | None | Optional SDK and adapter not provisioned |
| CloudStorageIngestor | Pass | Not connected | None | No cloud source SDK/credential registration provisioned |

The implemented inventory is review metadata, not a dynamic plugin loader. It imports no optional ingestor classes, opens no external connections and exposes no secrets. Its route requires read authorization. Registration and execution retain their existing separate scopes.

## Workflow and database verification

The workflow ownership map is in [Workflow engine and workspace responsibilities](../WORKFLOW-ENGINE.md). Six workspace contract tests cover Change Control, Data Flow, Ontology Junction, Data Catalog, Data Products and Metadata Registry. Domain tests additionally exercise Data Flow, product/catalog loading, Registry, semantic bridging, merge controls and inference presentation.

A read-only transaction against local PostgreSQL schema `semantic` verified `depo_registry(namespace,key,value,updated_at)`, its primary key and ten additional indexes, including source lookup, runnable-worker and job-identity indexes. At inspection it contained 10 job definitions and 83 run records, and no REST-source registrations. This is schema and queue evidence, not an external source acquisition test. No schema drop, migration, data cleanup or credential rotation was needed.

The initial direct-Semantica pipeline dependency change failed the existing lean-service test because it introduced local ML/notebook packages. That approach was removed. Regenerated locks match the original pipeline profiles: 74 packages for the API and 69 for the worker. The final boundary reuses the already installed semantic dependency runtime without another API service.

## Validation

- Worker, control, error, manifest-concurrency and acquisition timing group: 57 tests passed.
- Final connector, authorization, runtime-selection, actual acquisition-child smoke, dependency-profile and REST group: 46 tests passed.
- Frontend targeted coverage: 106 distinct tests across 11 files passed, including 16 final shared task-panel tests. Groups overlap; their run totals are not added together.
- Pipeline API and worker import/OpenAPI smoke passed. The production frontend build passed using the native configuration loader. Default bundled configuration loading failed on sandbox directory traversal before application compilation; the native loader succeeded.
- React act/deprecation warnings, module-type warnings and existing large frontend chunks remain. No performance throughput claim is made from functional tests.
- The Windows isolated runtime path and missing-runtime failure are tested with temporary filesystem fixtures; a clean isolated customer installation and external SDK/source credentials still require customer acceptance. The shared acquisition child was executed locally.

These changes are source changes, not a deployed customer release. Customer environments and their source credentials were not changed. No LLM was invoked. Unsupported ingestor integrations remain explicit product gaps, rather than being represented by placeholder configuration or empty database tables.


## Optimization follow up

The compatibility entrypoint `backend/depo_platform/semantica_ingestors.py` now owns the reviewed class allowlist and stdlib prerequisites. REST uses it without changing endpoint policy or acquisition limits. The Email import failure is mitigated by importing `email.message` before Semantica resolves its lazy class; installed third-party files and dependencies remain unchanged. Loading a class does not instantiate a connector or enable source access.

Task history stops periodic requests after 401/403 and resumes after verified access or manual refresh. Transient failures back off instead of polling at a fixed rate. Selected-task read failures retry safely without replaying controls. Hidden workspaces stop their polling and immediately refresh on return, while rejected access remains stopped. Agent proposal controls initialize only when their section opens; the retained goal panel is lazy-loaded only for a selected goal. Admin runtime details distinguish the API package environment from the acquisition runtime, avoiding a false missing-package impression in isolated deployments.

Follow-up validation: 34 focused frontend tests passed, including hidden-tab return, transient status-read recovery, authorization rejection, deferred controls and malformed inventory protection. The backend connector/runtime/dependency group passed 49 tests, including a fresh-process Email import through the compatibility loader. These tests do not exercise email servers or provision any of the 13 unintegrated source adapters.


## Implemented follow-up: registered adapters and deferred workspaces

The earlier 13 unintegrated-adapter gap is superseded by the registered connector workflow documented in [CONNECTOR-SOURCES.md](../CONNECTOR-SOURCES.md). All 17 kinds have an application path: three existing native import paths, REST acquisition and 13 profile-bound worker adapters. This is implementation coverage, not customer connection acceptance. No cloud/mail/warehouse credentials were configured.

Confirmed fixes: Data Flow query-string run links now select the requested historical run; run lists paginate at 25 rows; workspace panels initialize on their first visit and retain state afterward; heavy Data Products subpanels load lazily; Catalog presence no longer appears as a blank delivery cell. The alternate Siemens manual-chunk experiment increased runtime size and was discarded.

Final focused checks: 49 frontend tests across six files and 35 backend connector/catalog/submission tests passed. Backend tests include real Parquet/Arrow/SQLite reads, a real child acquisition process and separate connector receipt recovery. React test deprecation warnings remain. These totals are targeted groups, not a whole-repository test claim.

The baseline source was committed and deployed locally as 76c4dbb with environment hashes preserved. The adapter/performance follow-up is a separate release. Customer deployment acceptance remains excluded at the user's request. External drivers require reviewed optional SDK locks; acquisition is not semantic validation or governed publication.

Production bundle analysis: the Data Products route chunk fell from 103,796 to 23,284 bytes (about 78%); its immediate imports no longer include the data-grid vendor chunk. The extracted panels still exist and download when visited. This is a route-loading improvement, not a 78% reduction in total application size. The existing large shared runtime warning remains.


Local upgrade acceptance exposed a read-access timeout while the ingestion registry was processing a synchronous graph query in an async route. The registry route now runs in FastAPI's thread pool. A concurrent-request regression holds the graph read and verifies an unrelated async probe remains responsive. Startup now distinguishes HTTP 0/404/5xx verification failures from actual 401/403 authentication rejection; transient failures do not recommend credential rotation. This finding was discovered by deployment, beyond the earlier mocked test groups.

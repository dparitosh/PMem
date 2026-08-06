# Repository-wide NetworkX code audit — 2026-08-05

## Scope and evidence

- 326 first-party source files (233 application, 93 test), excluding `.dt_venv`, `node_modules`, generated builds, uploads, logs, data, and vendored `external` code.
- Directed module graph: 627 import edges, 3 strongly connected components, 33 isolated files.
- Runtime API graph: 178 OpenAPI operations and zero duplicate method/path pairs.
- Tests: frontend 69/69 passed; focused Neo4j/security 13/13 passed; isolated backend set 242 passed, 7 failed, 2 skipped.
- Machine-readable graph and detector output: `data/code_audit/networkx_audit.json`.

Detector output is triage material, not automatically a defect. Empty package `__init__.py` files and route names repeated under different router prefixes were removed/downgraded as false positives.

## Confirmed critical/high issues

### 1. Backend tests write to the live Neo4j database (critical)

`backend/tests/test_ontology_upload.py` replaces filesystem storage but does not replace the graph connection. API uploads in lines 190-199 and 221-229 reach live Neo4j. The audit run changed `sematic` from 12,564 nodes/0 relationships to 12,682 nodes/102 relationships. Confirmed test prefixes include `sysarch`, `sysarch1`, and `sysml`; small `domain`/`domain1` records were also created. No cleanup was performed because that would be destructive.

Required change: tests must inject a fake graph or a dedicated disposable Neo4j database and fail closed if the database name is not explicitly a test database.

### 2. Most mutating APIs have no authorization boundary (critical outside an isolated sandbox)

`backend/main.py:1224` defines `require_api_key`, but no endpoint uses it. Import upload/commit/cancel, workflow execution, modeling node/link create-update-delete, index creation, seeding, embeddings, and proposal approval are callable without identity or role checks. Only destructive admin routes use `require_admin_api_key` (`backend/routes/admin_routes.py:554`, `:622`, `:826`, `:858`).

Required change: central authentication plus explicit read/write/admin authorization policies. Session IDs are correlation/security state, not authentication.

### 3. Agentic service boundary is internally contradictory and cannot start (high)

`start_agentic.bat:12` executes `start_service.py`, while `standalone/ontology_agentic_service/tests/test_registry_contract.py:63` explicitly asserts that file does not exist. `backend/tests/test_api_standalone_regressions.py:16` imports the deleted `ontology_agentic` package. Frontend agentic endpoints remain configured at `frontend/src/config.js:321-327` but have no running service.

Required change: either restore a supported service entry point/package or remove the startup command, stale tests, docs, and optional UI integration as one coherent deletion.

### 4. Architecture view drops nodes connected only outside the requested model (high)

`backend/Services/graph_view_service.py:1519-1526` includes a model node only when it has no relationships at all (`AND NOT (n)--()`). A node with no same-prefix neighbor but an unrelated external edge disappears. The regression expectation in `backend/tests/test_graph_view_service.py:16` fails.

Required change: use `NOT EXISTS { MATCH (n)--(peer) WHERE peer belongs to $prefix }`.

### 5. XSD relational report has an ambiguous/incorrect flattened column contract (high)

`backend/Services/xsd_relational_report.py:119-121` appends every table's columns to one global `columns` list. Nested anonymous field `inner` is therefore reported as if it were a root-level column, failing `backend/tests/test_metadata_taxonomy_inference_reports.py:214`. Per-table ownership is present, but the global response loses that distinction for consumers.

Required change: make `columns` explicitly table-qualified or expose root columns separately; nested anonymous fields must remain owned by their child table.

### 6. Semantic database content violates expected ontology graph invariants (high)

Before tests, `sematic` held 12,564 `OntologyClass`/`ObjectProperty`/metadata nodes and zero relationships. This means domain, range, subclass, inverse, and other ontology semantics were absent from Neo4j even though ontology statistics looked populated. The UI can show large ontology counts while graph/schema relationships are empty.

Required change: validate each ontology commit with minimum invariants and reject/flag imports where property/class nodes exist but expected semantic edges do not.

### 7. Import commits are batch-partial rather than atomic (high)

`backend/Services/unified_data_import.py:2421-2464` commits independent statements/batches. Execution now stops and reports failure, but earlier batches remain committed. Retrying can mix partial and new state.

Required change: stage by `import_id`, validate, then promote; on failure delete only the staged import scope.

## Reliability and maintainability issues

### 8. Live/procedural scripts are named as pytest tests

`test_ontology_corrected.py`, `test_ontology_creation.py`, `test_ontology_e2e.py`, `test_ontology_final_report.py`, and `test_stages_4_7.py` have no pytest test functions and execute requests/sleeps/database access at import time. This caused collection/runtime hangs and makes `pytest backend/tests` unsafe.

### 9. Import graph contains three cycles

- `ontology_extractor.py` ↔ `threedxml_ontology_extractor.py`
- `data_import_service.py` ↔ `ontology_upload_manager.py` ↔ `unified_data_import.py`
- root `main.py` ↔ `backend/main.py` ↔ `routes/admin_routes.py`

The cycles are currently hidden with local imports and dual `backend.*`/legacy import fallbacks. They increase initialization-order and test-patching failures.

### 10. Central modules are extreme change-risk hotspots

- `backend/main.py`: 5,501 lines
- `backend/Services/unified_data_import.py`: 3,969 lines
- `frontend/src/Components/GraphHEB.js`: 4,309 lines, 134 React hooks
- `frontend/src/Components/DataImportPipeline.js`: 3,578 lines, 65 hooks
- `frontend/src/Components/OntologyMapper.js`: 3,479 lines, 120 hooks
- `backend/Services/graph_view_service.py`: 2,204 lines

Highest complexity proxies include `_parse_plmxml` (124), `_commit_sync` (115), ArchiMate parsing (82), and ontology inference preview (82). These should be split along existing format/stage/view boundaries, not rewritten wholesale.

### 11. Exception handling suppresses diagnosis

The detector found 631 broad `Exception` handlers and 39 handlers containing only `pass`/`continue`. Confirmed user-visible examples include graph fallbacks in `backend/main.py:1875`, `:2344`, `:2355`, `:2371` and parsing/config fallbacks throughout `unified_data_import.py`. This is consistent with the earlier empty-schema failure being presented as valid empty data.

### 12. Component test names overstate coverage

`frontend/src/Components/GraphHEB.test.js` tests graph utility functions and does not import/render `GraphHEB`. No direct component test was found for the 4,309-line, 134-hook component. `OntologyMapper` and `WhereUsedView` are also dependency hubs without direct behavioral coverage.

### 13. Startup scripts do not enforce declared runtimes

`frontend/package.json:58` requires Node `>=20.11 <23`, but `start_frontend.bat:63` accepts every version >=20; this machine runs Node 24 and emits deprecation warnings. Backend setup's `where python` check failed despite Python 3.12 being installed, and frontend host discovery uses a privileged `Get-NetIPAddress` call that fails in restricted environments.

### 14. Configuration and runtime state can disagree for minutes

The prior `semantic` versus actual `sematic` typo caused `DatabaseNotFound`. The empty schema was then cached for ten minutes while live ontology stats continued to show data. Empty-cache recovery is fixed, but startup should validate that the configured database exists and report available database names without exposing credentials.

### 15. Optional service API paths do not exist in the main OpenAPI contract

Five configured frontend paths (`/api/v1/agents`, `/api/v1/tools`, `/api/v1/openapi/import`, `/api/v1/agents/{agent_name}/run`, `/api/v1/workflows/run`) are absent from the running main API. They are guarded by `REACT_APP_AGENTIC_ENABLED`, but enabling the documented option currently produces connection failure because the service entry point is missing.

## Validation results and limitations

- Python compile-all: pass.
- Frontend production build: pass.
- Frontend tests: 16 suites, 69 tests, all pass.
- Backend isolated set: 242 pass, 7 fail, 2 skip. Failures cover architecture filtering, XSD ownership, and live-database contamination/state leakage.
- Full backend discovery is not a safe unit suite because several files perform live operations during import.
- Dependency vulnerability lookup was not performed: registry audit approval was rejected because it would transmit lockfile-derived dependency metadata. `pip check` reports no broken Python requirements, which is compatibility—not vulnerability—validation.

## Recommended remediation order

1. Quarantine test databases and identify/remove test records only after explicit approval.
2. Add authentication/authorization to every mutation surface.
3. Resolve the agentic boundary coherently.
4. Fix the architecture-view and XSD ownership regressions.
5. Add semantic graph commit invariants and staged-import cleanup.
6. Separate procedural/live checks from unit tests and add pytest markers.
7. Break the three dependency cycles.
8. Incrementally split the largest backend stages and React components while preserving behavior with characterization tests.

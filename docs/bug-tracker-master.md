# Master Bug Tracker

Canonical merged release tracker.

Merged sources:
- docs/bug-tracker-pareto.md
- docs/bug-tracker-150.md

This file is the single tracker to use for release closure and audit status.
Legacy tracker files remain in docs/ only as source references.


---


# UI / API Bug Tracker and Pareto Plan

Date: 2026-06-15

This tracker groups the highest-confidence functional and logical issues by page so they can be closed systematically.
The list is intentionally biased toward release blockers, not cosmetic polish.

## Pareto summary

Most of the user pain is concentrated in four areas:

1. Graph Explorer search, expansion, and render state.
2. Import pipeline workflow selection, ontology linkage, and commit/progress handling.
3. Ontology Studio semantic bridge / alignment flow.
4. Admin destructive cleanup and graph reset behavior.

If we fix those first, we unblock most of the visible instability across the app.

## Audit update - 2026-06-16

Closed in current branch audit:

1. Graph search now preserves focused ontology search behavior instead of forcing all searches through the individual-only contextual API.
2. PLMXML import now preserves relationship properties, enforces stable row merge keys, and blocks duplicate-source commits before graph corruption.
3. Metadata-like wrapper nodes are filtered more safely so `id*`-style business nodes are no longer hidden by a broad heuristic.
4. Dead comparative-search modal code was removed from `GraphHEB.js` to reduce dormant state and legacy UI noise.
5. Collapse bookkeeping now uses the shared pruning utility and has a regression test for removing an expansion slice cleanly.
6. Contextual subgraph search now accepts actual instance/schema neighbors instead of filtering them down to `Individual` only, which was the blank-canvas root cause for contextual search.
7. Search inputs now normalize `*` wildcard markers before matching so full graph, where-used, and contextual searches use the same broad-text behavior.

Still open after audit:

1. Import workflow issues are closed in this area for the current pass; the remaining release work is outside the core import intent/state split.
2. Ontology Studio, Recommendations, Reports, Admin, and Where Used items below remain open unless explicitly marked otherwise.

## Audit update - 2026-06-20

Closed in current branch audit:

1. Contextual instance search now keeps wildcard-aware input and anchors the result to one selected root node instead of replacing the canvas with a broad traversal slice.
2. Clearing the contextual search no longer wipes the current one-hop instance graph; it now clears highlights/results while preserving the current explored context.
3. Contextual root resolution now prefers the active selected result or current root before falling back to heuristic matching.
4. Expand/collapse bookkeeping now uses stable relationship signatures, which keeps collapse reliable after merged or deduplicated relationships.
5. Contextual empty-state rendering now distinguishes `No Results Found` from the normal `search to begin` prompt.
6. Frontend audit validation passed with `npm run build` after the graph-state fixes.

Still open after 2026-06-20 audit:

1. `NEO-20` and broader Graph Explorer toolbar/interaction polish are still open inside `WS-01`.
2. `WS-02` Import pipeline and `WS-03` Semantic Bridge remain the largest unresolved release areas outside the graph patch set.

## Audit update - 2026-06-20 (WS-02)

Closed in current branch audit:

1. `instance.link` now requires one explicit imported instance artifact selection instead of inferring the source artifact implicitly from general page context.
2. Import workflow gating now uses one shared block-reason model, so workflow buttons disable consistently when ontology, target ontology, or source artifact selection is missing.
3. The import note and action guidance now describe structural import and semantic linking as separate steps with clearer user-facing prerequisites.
4. The bridge workflow payload now carries the selected source import file identity together with the retained artifact manifest.
5. Frontend validation passed with `npm run build` after the import workflow changes.
6. A follow-up patch added fresh-session checks for restored jobs, unified commit/status persistence, clearer queued/background commit messaging, and stage labels that align with actual workflow behavior.
7. A second follow-up patch added live ontology catalog refresh, cache-source visibility, and a dedicated ontology registration banner so ontology upload is no longer hidden inside the generic import surface.
8. A third follow-up patch removed automatic workflow switching on file attach and now enforces explicit file-intent routing: ontology/schema files stay in Create ontology, instance files stay in Import instance graph.

Still open after 2026-06-20 WS-02 audit:

1. No open `IM-*` item remains in the current import workflow clarification set; remaining work is broader cross-page architecture and backend standardization.
2. Backend task/progress semantics still need more standardization than this UI-side workflow clarification patch provides, but the frontend state machine is now materially safer for long-running imports, ontology selection workflows, and file-intent routing.


## Audit update - 2026-06-21

Closed in current branch audit:

1. `AD-02` Prefix cleanup now supports optional property/value filters, so targeted deletion by ontology scope and import/job metadata is possible without falling back to raw Cypher.
2. `AD-03` Admin preview and execute now use one shared scope model, which keeps previewed and destructive cleanup parameters aligned.
3. Validation passed with `python -m py_compile backend/Services/neo4j_schema_cleaner.py backend/routes/admin_routes.py`, `pytest backend/tests/test_neo4j_fixes.py -q`, and `npm run build` (one unrelated ESLint warning remains in `GraphExplorerToolbar.js`).


## Audit update - 2026-06-28 (release blockers)

Closed or materially improved in this pass:

1. `EXP-01` Registered ontology export is now first-class through `GET /api/v1/ontology/{ontology_id}/export?format=ttl|rdf|owl|jsonld`.
2. `EXP-02` XSD/XMI ontology registration now pre-generates durable TTL, RDF/XML, OWL/XML, and JSON-LD artifact files in ontology metadata.
3. `OWL-01` XSD-derived ontology metadata now promotes `targetNamespace` into stored namespace/prefix so generated ontology identity is not silently replaced by a UI fallback prefix.
4. `OWL-02` XSD OWL generation now writes source namespace into the generated ontology header metadata for OSLC/RDF consumers.
5. `ON-07` Ontology Junction now exposes compact active-ontology export links for TTL, RDF, OWL, and JSON-LD.
6. `ON-08` Semantic Bridge/merge workflow artifact links remain manifest-based and now align with the direct ontology export API.
7. `AD-05` Added read-only duplicate ontology audit endpoint at `GET /api/v1/admin/ontology-duplicate-audit` to diagnose duplicate `OntologyClass`/`OntologyProperty` keys before destructive cleanup.
8. `OSLC-04` OSLC ResourceShape payloads now expose ontology export links for external semantic clients.
9. `RP-01` Added backend compatibility report endpoints `POST /reports` and `POST /api/v1/reports` for customer environments where the Reports page/API integration expected this route.
10. `DQ-01` XSD smoke validation confirms header namespace `http://example.com/customer/plmxml` produces prefix `plmxml` and durable export formats `ttl/rdf/owl/jsonld`.

Validation in this pass:

- `python -m py_compile backend/main.py backend/routes/admin_routes.py backend/Services/ontology_upload_manager.py backend/Services/owl_generation_service.py backend/Services/oslc_service.py backend/Services/semantic_workflow_service.py`
- `npm run build` in `frontend/`
- `git diff --check` for touched backend/frontend files
- XSD engine smoke test for targetNamespace-derived prefix/base URI
- Ontology registration smoke test in temporary storage verifying export artifacts

Still open / requires customer-data confirmation:

1. Existing Neo4j duplicate schema data must be cleaned or reprocessed before uniqueness constraints can be safely enabled.
2. Existing backend process must be restarted before new `/api/v1/admin/ontology-duplicate-audit`, `/reports`, and ontology export routes are visible live.
3. Reports and recommendations now have safer API contracts, but customer graph semantics still need validation against the actual customer dataset.
4. Full OSLC write/update flows remain out of scope; current OSLC coverage is read/query/shape/taxonomy/dictionary/TRS/export discovery.

## Fix order

1. Graph Explorer search and expand/collapse correctness.
2. Import workflow selection and ontology linkage clarity.
3. Ontology Studio alignment model and candidate visibility.
4. Admin cleanup and batched delete safety.
5. Reports filtering / export correctness.
6. Where Used search and hierarchy completeness.
7. Recommendation result rendering and readiness handling.

## Code-wise workstreams

Use these workstreams to fix bugs and standardize/componentize the same code path in one task bundle.

| Workstream | Primary code areas | Bug groups | Refactor / standardization goal |
|---|---|---|---|
| WS-01 Graph Explorer core | `frontend/src/Components/GraphHEB.js`, `frontend/src/utils/graphUtils.js`, `frontend/src/services/apiClient.js`, graph APIs in `backend/main.py` and `backend/core/graph.py` | `GX-*`, `NEO-*` | Split search, context expansion, and render state into stable hooks/utilities; keep node-first search, one-hop expansion, and consistent labels in the same renderer contract. |
| WS-02 Import pipeline | `frontend/src/Components/DataImportPipeline.js`, `frontend/src/config.js`, `frontend/src/services/apiClient.js`, `backend/main.py`, `backend/Services/unified_data_import.py`, `backend/Services/data_import_service.py` | `IM-*`, `EXP-*` (artifact/export portions), `API-*` (import routes) | Componentize workflow selection, task progress, ontology linking, retry handling, and download/export actions so one task owns one state machine. |
| WS-03 Semantic Bridge / Ontology Studio | `frontend/src/Components/OntologyMapper.js`, `backend/Services/semantic_workflow_service.py`, `backend/Services/ontology_extractor.py`, `backend/Services/ontology_runtime.py`, `backend/routes/ontology_routes.py` | `ON-*`, `OWL-*`, `PAR-*` | Separate instance-to-ontology bridge from ontology-to-ontology merge; standardize one canonical semantic model for classes, properties, metadata, and exports. |
| WS-04 Backend API foundation | `backend/main.py`, `backend/core/db_config.py`, `backend/agent/*.py`, `backend/chains/*.py`, `backend/models/schema.py`, shared routers | `API-*` | Split monolithic route ownership into routers/services, enforce consistent response models, and centralize environment, driver, and timeout handling. |
| WS-05 Admin and destructive maintenance | `frontend/src/Components/AdminPanel.js`, `frontend/src/Components/AdminPage.js`, `backend/routes/admin_routes.py`, `backend/Services/neo4j_schema_cleaner.py` | `AD-*`, destructive cleanup portions of `API-*` | Separate preview, targeted cleanup, and destructive reset actions; make scope explicit and reuse the same query parameters for preview and execution. |
| WS-06 Reports and recommendations | `frontend/src/Components/ReportsTab.js`, `frontend/src/Components/RecommendationsTab.js`, recommendation services in `backend/main.py` and `backend/Services/*recommender*.py` | `RP-*`, `RC-*` | Normalize result schemas, keep renderers deterministic, and move recommendation/reporting logic into reusable service adapters. |
| WS-07 Export and artifact delivery | `backend/main.py`, `backend/Services/semantic_workflow_service.py`, `backend/Services/ontology_upload_manager.py`, frontend export controls | `EXP-*`, export portions of `API-*` | Make `.owl/.rdf/.ttl/.jsonld` download a first-class artifact path with background pre-generation and a single frontend export surface. |

Suggested execution rule:
- When a workstream is tackled, do the component split first or in the same patch set.
- Keep bug fixes, naming cleanup, and state consolidation in one branch so the code does not drift back into the old shape.

## Tracker



| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| GX-01 | Graph Explorer | Search state can fall back to the full canvas during a focused search. | Users see the whole graph instead of the searched node context. | `GraphHEB.js:3808-3819`, `4576-4603` | P0 | Patched | Search for a node and verify only the focused subgraph renders until cleared. |
| GX-02 | Graph Explorer | Collapse bookkeeping can desync from visible nodes. | Collapse appears to fail even after the user clicks it. | `GraphHEB.js:3657-3687` | P0 | Patched | Expand a node, collapse it, and confirm only the expansion slice is removed. |
| GX-03 | Graph Explorer | `expandedNodes`, `expandedNodesRef`, and `searchModeRef` are maintained separately. | The same node can expand in one interaction and fail in the next. | `GraphHEB.js:1135-1144`, `3490-3558` | P0 | Patched | Expand node A, then node B, then collapse either one without losing state. |
| GX-04 | Graph Explorer | Search results are mixed with graph canvas results. | Users cannot tell whether search found nodes or just filtered edges. | `GraphHEB.js:1178-1189`, `3808-3819` | P0 | Patched | Search must render node-first results, not a generic graph dump. |
| GX-05 | Graph Explorer | Expand/collapse controls depend on the current slice only. | A node can show a plus/minus affordance that is not actually actionable. | `GraphHEB.js:4181-4238`, `4506-4523` | P1 | Patched | Nodes with traversable neighbors show correct affordance in every mode. |
| GX-06 | Graph Explorer | Search centering can be lost when the graph re-renders. | The result is not visually anchored to the main context. | `GraphHEB.js:4575-4603` | P1 | Patched | Search a node and keep it centered/highlighted after rerenders. |
| GX-07 | Graph Explorer | The ontology graph can still render labels inconsistent with data-bearing fields. | Users see label noise instead of useful value labels. | `GraphHEB.js:35-42`, `1746-1776` | P1 | Patched | Full graph labels match the intended display rule for each node type. |
| GX-08 | Graph Explorer | Tooltip actions are embedded in node tooltips but not validated against result state. | The action buttons can appear to work while producing no visible result. | `GraphHEB.js:902-914`, `4408-4523` | P1 | Patched | Click each tooltip action and confirm visible downstream output. |
| GX-09 | Graph Explorer | The graph can show nodes with metadata-only IDs that look like data. | XML tag wrappers pollute the instance graph. | `frontend/src/utils/graphUtils.js:9-65` | P0 | Patched | Search and expand should exclude XML metadata-only wrappers unless explicitly requested. |
| GX-10 | Graph Explorer | View mode labels and result modes were overloaded. | Users did not know whether they were in full graph, ontology, or contextual instance mode. | `GraphHEB.js:4821-4950` | P1 | Patched | Each mode has a distinct render contract and visible behavior. |
| GX-11 | Graph Explorer | Global SVG styling can leak into embedded icons if not scoped. | Small toolbar icons and graph canvas symbols can render inconsistently. | `GraphHEB.css`, scoped SVG rules | P2 | Patched | Toolbar icons stay thumbnail-sized while the canvas still fills the panel. |
| GX-12 | Graph Explorer | Auto-refresh behavior can overwrite user focus while a search is active. | The user loses the selected node or sees flicker. | `GraphHEB.js:4820-4846`, `5156-5167` | P0 | Patched | Search, expand, and pan interactions do not reset the canvas unexpectedly. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| IM-01 | Import | Workflow selection still mixes structural import with ontology linkage concepts. | Users do not know whether they are importing data, mapping it, or linking it. | `DataImportPipeline.js:707-760`, `1392-1453` | P0 | Patched | Each workflow has one clear purpose and a single user action path. |
| IM-02 | Import | `instance.link` depends on retained artifacts from previous steps. | Linking can silently use stale source state. | `DataImportPipeline.js:748-753`, `1804-1808` | P0 | Patched | Link only runs against the selected import artifact for the current session. |
| IM-03 | Import | Ontology selection is required in some flows but hidden behind multiple conditions. | Users cannot predict when the workflow is runnable. | `DataImportPipeline.js:731-763`, `1379-1453` | P0 | Patched | The UI tells the user exactly when ontology selection is mandatory. |
| IM-04 | Import | Ontology creation is mixed with metadata capture and file-type inference. | The same file can appear to have several conflicting purposes. | `DataImportPipeline.js:316-406`, `1950-2029` | P1 | Patched | File attach now respects the selected workflow intent and blocks ontology files from structural import, and vice versa. |
| IM-05 | Import | Preview and commit state are tracked separately from the task state machine. | Progress can appear stuck at 92-94% or duplicate. | `DataImportPipeline.js:618-645`, `2340-2350` | P0 | Patched | Progress and commit state now share one persisted task record with a single authoritative status path. |
| IM-06 | Import | Timeout handling is long but not clearly surfaced to the user. | Large files look frozen during commit. | `DataImportPipeline.js:861-895`, `862-869` | P0 | Patched | Large commit runs now surface queued/background commit state directly in the job UI. |
| IM-07 | Import | `workflowApplyLinks` is only valid for one workflow but lives globally. | The toggle can be shown when it should not apply. | `DataImportPipeline.js:80`, `286-289`, `1439-1450` | P1 | Patched | The checkbox only appears for semantic bridge linking. |
| IM-08 | Import | A number of stage labels imply work that may not be happening yet. | The pipeline reads like a promise rather than the actual backend path. | `DataImportPipeline.js:1024-1046`, `2021-2028` | P1 | Patched | Stage names and step descriptions now match the actual import/create/link flow. |
| IM-09 | Import | Cached ontology catalog can outlive the live registry. | Users may select stale ontology options. | `DataImportPipeline.js:100-199` | P1 | Patched | The workflow now supports explicit live refresh and shows whether the catalog came from the registry or cache. |
| IM-10 | Import | Direct ontology files are routed through a special metadata form and can feel disconnected from the main pipeline. | Users do not know where ontology upload belongs. | `DataImportPipeline.js:316-406`, `1167-1180` | P1 | Patched | The ontology registration path is now explicit in the workflow UI and clearly separated from structural instance import. |
| IM-11 | Import | The selected ontology ID/prefix logic is reused across multiple workflows. | A wrong ontology can be applied to a file by accident. | `DataImportPipeline.js:439-490`, `757-763` | P0 | Patched | Workflow payloads only include the ontology fields that apply. |
| IM-12 | Import | The pipeline can resume persisted files without a clear freshness check. | Stale UI state can re-run old tasks after restart. | `DataImportPipeline.js:231-266`, `691-704` | P1 | Patched | Persisted jobs now resume only while fresh; stale sessions require explicit restart instead of auto-resume. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| ON-01 | Ontology Studio | The page mixes ontology browsing, dictionary tables, and alignment controls in one surface. | Users cannot tell what is the authoritative semantic bridge workflow. | `OntologyMapper.js:2054-2209`, `2261-2306` | P0 | Patched | Semantic Bridge now exposes an explicit step-by-step bridge flow, a separate ontology-merge section, and visible merge-plan export artifacts instead of leaving users to infer the workflow. |
| ON-02 | Ontology Studio | A single ontology selector is used for multiple meanings. | Source ontology, target ontology, and active ontology blur together. | `OntologyMapper.js:1365-1397`, `2278-2292` | P0 | Patched | Semantic Bridge now consumes one shared active ontology selection path; instance selection remains separate and the duplicate bridge-side ontology picker is removed. |
| ON-03 | Ontology Studio | Empty dictionary data silently falls back to taxonomy-derived data. | Users can mistake inference fallback for real ontology content. | `OntologyMapper.js:1658-1761` | P0 | Patched | Taxonomy-derived fallback is now explicitly flagged in ontology browser views and the Semantic Bridge target summary instead of silently masquerading as primary dictionary content. |
| ON-04 | Ontology Studio | Bridge candidate visibility was filtered by confidence thresholds before the user saw them. | Low-confidence but important suggestions disappeared too early. | `OntologyMapper.js:1405-1426`, `2381-2459` | P0 | Fixed | All preview candidates are visible; confidence/status is shown instead of silently filtering rows. |
| ON-05 | Ontology Studio | The alignment tab allowed editing by a generic mapping model instead of Semantic Bridge fields. | The app behaved like ontology-to-ontology merging only. | `OntologyMapper.js:1908-2009`, `2482-2684` | P0 | Fixed | Manual mapping now separates imported entity/attribute/relationship/metadata from ontology class/data/object/annotation property targets. |
| ON-06 | Ontology Studio | The ontology browser and alignment views are too coupled to the same selection state. | Switching views can reset the wrong state. | `OntologyMapper.js:2144-2209`, `2232-2340` | P1 | Patched | Changing between ontology browser views and Semantic Bridge now keeps one canonical active ontology selection instead of diverging page-level and bridge-level state. |
| ON-07 | Ontology Studio | Selected ontology output is often shown as prefix/id metadata instead of domain meaning. | Users cannot tell what they are aligning against. | `OntologyMapper.js:2334-2339`, `2278-2287` | P1 | Patched | The header and bridge summary now identify the active ontology as the semantic validation target rather than a raw technical selector only. |
| ON-08 | Ontology Studio | Ontology class/property lists can become empty even when reasoning has data. | The browser looks broken to users. | `OntologyMapper.js:507-511`, `707-756`, `867-875` | P0 | Patched | OWL Browser property coverage now includes annotation properties and keeps browser/property rows populated from reasoning or fallback dictionary sources instead of presenting blank sections. |
| ON-09 | Ontology Studio | Taxonomy rendering uses a compact outline plus a browser mode that can diverge from ontology data. | The visual tree does not match the actual OWL model. | `OntologyMapper.js:342-607`, `664-1204` | P1 | Patched | Taxonomy and OWL browser now compose nodes and edges from the same normalized ontology/taxonomy/reasoning inputs, including subclass and domain/range semantics, so both views describe the same ontology slice. |
| ON-10 | Ontology Studio | Mapping vocabulary rows are derived from heterogeneous sources with different key conventions. | Duplicate or malformed mappings can appear. | `OntologyMapper.js:1648-1701` | P1 | Patched | Semantic Bridge mapping rows now normalize source/target ids, types, status, confidence, and comment fields through one canonical frontend row shape before render. |
| ON-11 | Ontology Studio | The alignment view was not clearly scoped to instance-to-ontology mapping. | The user thought ontology merging was the main task. | `OntologyMapper.js:2222-2267` | P0 | Fixed | The panel is now explicitly labeled as instance-to-ontology bridge; ontology-to-ontology merge is called out as separate. |
| ON-12 | Ontology Studio | User-editable bridge mappings are not surfaced as a first-class review queue. | Corrections are hard to audit and approve. | `OntologyMapper.js:2475-2555`, `2570-2673` | P1 | Patched | The bridge mapping table now exposes explicit review state, approval toggles, confidence visibility, and persisted user comments so manual review is visible instead of implicit. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| RC-01 | Recommendations | Result renderers can return `null` for valid backend responses. | The user sees blank success states. | `RecommendationsTab.js:347-380`, `1200-1331` | P0 | Fixed | Successful but sparse recommendation responses now render an explicit empty-state card instead of disappearing. |
| RC-02 | Recommendations | Health/readiness defaults are permissive when the backend payload is incomplete. | The user can run a scenario that is not ready. | `RecommendationsTab.js:447-450` | P1 | Fixed | Missing or degraded readiness payloads now fail closed and show the service as unavailable instead of implicitly ready. |
| RC-03 | Recommendations | Prefill event flow depends on `dt-rec-prefill` and a global window fallback. | The feature can look inconsistent across pages. | `RecommendationsTab.js:443-460` | P1 | Open | Graph tooltip actions and recommendation panel always sync. |
| RC-04 | Recommendations | The scenario entry point is stateful but not strongly validated against input type. | Wrong inputs can still trigger service calls. | `RecommendationsTab.js:463-491` | P1 | Open | Input validation is explicit per scenario. |
| RC-05 | Recommendations | Search/impact/manufacturing results use different internal shapes. | Consistent reporting and export become harder. | `RecommendationsTab.js:641-643` | P1 | Open | Result schema is normalized before render. |
| RC-06 | Recommendations | The page mixes business guidance and action triggers, which can overstate certainty. | Users may treat guidance as authoritative truth. | `RecommendationsTab.js:199-248`, `555-584` | P2 | Open | The panel clearly separates suggestion from decision. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| RP-01 | Reports | Report filtering assumed `row.type.split(',')[0]` was always valid. | Valid rows could disappear if type formatting differed. | `ReportsTab.js:170-224`, `285-318` | P0 | Fixed | Reports show all expected rows from the source dataset, including rows whose type comes from labels or fallback semantic fields. |
| RP-02 | Reports | Column toggling stores `false` as the only hidden state. | A column can reappear unintentionally after repeated toggles. | `ReportsTab.js:303-304`, `415-428` | P1 | Fixed | Column visibility now persists across report-type switches because defaults are seeded from the full dataset header set instead of the current slice only. |
| RP-03 | Reports | Pagination reset on every filter or report change without preserving user intent. | The table jumped around during review. | `ReportsTab.js:390-400`, `1038-1075` | P1 | Fixed | Filters and sorting keep the user on the current page unless the filtered result set no longer has that page. |
| RP-04 | Reports | Relationship rows are built from graph edges, not necessarily from the same semantic scope as the search report. | Users can compare incompatible datasets in one panel. | `ReportsTab.js:322-331`, `655-725` | P1 | Fixed | Relationship reports now explicitly state that they come from the current graph canvas and call out when node rows are filtered by search results. |
| RP-05 | Reports | Search report export and relationship export are handled through separate paths with different row shapes. | Export consistency is fragile. | `ReportsTab.js:637-650`, `1078-1086` | P1 | Fixed | Relationship export now uses a normalized row schema and filenames aligned to the current filter scope, matching the visible table columns. |
| RP-06 | Reports | Dynamic type tabs are derived from the current processed results only. | Tabs can vanish when the filter changes. | `ReportsTab.js:213-223`, `442-453` | P2 | Open | Tabs remain stable for the current dataset. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| AD-01 | Admin | Bulk delete requires either label or prefix, but the UX makes the destructive scope easy to misread. | A cleanup action can delete too much data. | `AdminPanel.js:177-192`, `388-418` | P0 | Open | Cleanup actions require an explicit scope preview and confirmation. |
| AD-02 | Admin | Prefix deletes forbid property/value filters. | The user cannot do targeted prefix-based cleanup. | `AdminPanel.js:201-293`, `admin_routes.py:617-654`, `neo4j_schema_cleaner.py:370-450` | P1 | Fixed | Prefix cleanup now supports the same optional property/value scope in both preview and delete paths. |
| AD-03 | Admin | Preview state and destructive action state are separate and can diverge. | The user may preview one scope and execute another. | `AdminPanel.js:200-293` | P0 | Fixed | Preview and delete now use one shared scope builder and send the same query parameters to the backend. |
| AD-04 | Admin | Schema cleanup bundles nodes, relationships, metadata, indexes, and constraints into one irreversible action. | Recovery becomes hard and risky. | `AdminPanel.js:116-139` | P0 | Open | The UI clearly separates reset, purge, and targeted cleanup. |
| AD-05 | Admin | Registry state is read only, but the page still implies broader system control. | Operators may expect configuration edits that are not present. | `AdminPage.js:164-167` | P2 | Open | Read-only scope is explicit and stable. |
| AD-06 | Admin | Cleanup messages do not distinguish between graph data and ontology storage. | Users cannot tell what was actually deleted. | `AdminPanel.js:126-129`, `156-170` | P1 | Open | Deletion feedback splits graph, metadata, and file store outcomes. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| WU-01 | Where Used | Search fallback only checks a narrow set of fields. | Valid nodes are not discoverable. | `WhereUsedView.js:179-185`, `322-347` | P0 | Patched | Search now matches IDs, labels, display names, and common metadata/property fields. |
| WU-02 | Where Used | Upward traversal assumes parents will always be returned in a single shape. | Parent hierarchy can truncate or skip nodes. | `WhereUsedView.js:196-301` | P1 | Patched | Parent expansion now resolves endpoints from generic traverse responses and keeps multi-hop ancestry intact. |
| WU-03 | Where Used | Search results and hierarchy rows are displayed as separate grids without a direct link between them. | Users cannot intuitively move from result to context. | `WhereUsedView.js:352-489` | P1 | Patched | Search results and hierarchy rows now use the same focus action and update the hierarchy around the chosen node. |
| WU-04 | Where Used | The selected node can be expanded upward, but search and expansion are not tied to the same selection model. | Second-click expansion can feel inconsistent. | `WhereUsedView.js:314-320`, `479-489` | P1 | Patched | Search selection and hierarchy focus now share one node-selection path. |
| WU-05 | Where Used | Ancestor-level counts are calculated from reconstructed links rather than a stable graph model. | The displayed depth can drift from the real traversal. | `WhereUsedView.js:256-289` | P2 | Patched | Ancestor depth is now derived from the traversed parent-link set produced during expansion. |


## Audit update - 2026-06-21 (Recommendations)

Closed in current branch audit:

1. `RC-01` Recommendation results now render explicit empty-state cards for sparse-but-successful payloads instead of silently returning `null` from D3 helper sections.
2. `RC-02` Recommendation readiness now fails closed when the health payload is missing or degraded, so the page no longer treats incomplete health data as implicitly ready.
3. Validation passed with `npm run build`; one unrelated ESLint warning remains for unused `GitFork` in `GraphExplorerToolbar.js`.


## Audit update - 2026-06-21 (Reports)

Closed in current branch audit:

1. `RP-02` Column visibility now persists across report-type switches because the visibility map is seeded from the full processed dataset, not rebuilt from the current slice alone.
2. `RP-04` Relationship reports now state their scope explicitly so users can see that link rows come from the current graph canvas while node rows may reflect a narrower search subset.
3. `RP-05` Relationship CSV export now uses one normalized row schema and a scope-aware filename instead of drifting from the visible table structure.
4. Validation passed with `npm run build`; one unrelated ESLint warning remains for unused `GitFork` in `GraphExplorerToolbar.js`.

## Closure checklist

1. Graph Explorer search must return node-focused, centered results and preserve expansion state.
2. Import must clearly separate structural import, ontology creation, and semantic linking.
3. Ontology Studio must present instance-to-ontology mapping as the primary workflow.
4. Admin destructive actions must require explicit scope preview and produce unambiguous feedback.
5. Reports and Where Used must stay consistent with the same source model and search behavior.

## Suggested test pass order

1. Graph Explorer search, expand, collapse, and tooltip actions.
2. Import workflow: upload, preview, commit, link, and ontology create.
3. Ontology Studio: class/property visibility, bridge suggestions, and manual correction.
4. Admin cleanup: preview, targeted delete, and schema reset.
5. Reports export and filter behavior.
6. Where Used search and multi-hop ancestry.


---


# 150-Bug Audit Tracker

Date: 2026-06-20

This tracker is a release-oriented audit backlog for the current codebase.
It spans backend API, Neo4j graph behavior, import/export services, frontend rendering, parsers, and ontology expressivity.

Status legend:
- `Open` = still needs implementation or validation
- `Patched` = already addressed in this branch, but kept here for release traceability

## Backend API
1. `API-01` CORS origin handling can drift from the active frontend host when the app is moved off `localhost`. Status: Patched.
2. `API-02` Several routes still import service classes inside handlers instead of using shared router/service wiring.
3. `API-03` The API surface still mixes v1 routes with deprecated compatibility routes, which complicates release hardening.
4. `API-04` Some error handlers return generic 500 responses without enough structured context for the UI.
5. `API-05` `/api/v1/ontology/{ontology_id}/reason` previously routed through the taxonomy facade instead of the canonical reasoning service. Status: Patched.
6. `API-06` `/api/v1/ontology/{ontology_id}/taxonomy` and `/reason` are still two separate flows that need clearer contract boundaries.
7. `API-07` API timeout settings are duplicated across frontend and backend instead of being negotiated from one source of truth.
8. `API-08` Several endpoints still accept loosely shaped payloads that can hide bad input until downstream code fails.
9. `API-09` Some responses return deeply nested status objects without a stable schema for client rendering.
10. `API-10` Import endpoints still expose both task state and artifact state in a way that can be confused by the client.
11. `API-11` Route naming still reflects legacy workflow language in places that should now be semantic-bridge first.
12. `API-12` Some handlers still rely on inline local imports instead of central dependency injection or shared adapters.
13. `API-13` Sample-query fallback logic can mask backend data issues by returning placeholder examples.
14. `API-14` Health/readiness endpoints can report partial readiness without enough detail for UI decisions.
15. `API-15` API-level pagination and limit defaults are inconsistent across graph, ontology, and reports routes.
16. `API-16` Some endpoints still return `JSONResponse` for content that should be downloadable as artifact files.
17. `API-17` `openapi.json` and UI-facing documentation are not yet aligned with the full export/download surface.
18. `API-18` The API layer still exposes legacy compatibility endpoints that should be hidden from normal users.
19. `API-19` Error logging is not always paired with structured response detail, making frontend diagnosis harder.
20. `API-20` Some routes do not distinguish between “no data” and “service unavailable”.
21. `API-21` File/path parameters are not consistently validated for safe artifact access.
22. `API-22` Some endpoints need explicit response models to reduce client-side guesswork.
23. `API-23` Cross-origin behavior for LAN IP hosts should be tested with both browser and API clients.
24. `API-24` The API surface still has too many one-off routes for the same underlying ontology life cycle.
25. `API-25` Some workflow endpoints still return results without clearly separating metadata, report, and export payloads.

## Neo4j Graph
26. `NEO-01` Graph projections can mix ontology schema nodes with instance data if the query scope is not explicit.
27. `NEO-02` Some graph views still depend on broad default limits that can over-fetch and obscure the current context.
28. `NEO-03` Relationship label normalization is needed so raw edge codes do not leak into the canvas.
29. `NEO-04` Node labels can still collapse to technical IDs instead of business-readable names.
30. `NEO-05` Metadata wrapper nodes can pollute graph context if the filter is not strict enough.
31. `NEO-06` Some graph traversals still assume one-hop expansion always produces a connected slice.
32. `NEO-07` Duplicate node merge safety depends on stable element IDs and consistent labels.
33. `NEO-08` Some graph routes still use legacy fallback endpoints when the primary data shape is missing.
34. `NEO-09` Graph search can be too broad and show a traversal slice instead of the matching nodes first. Status: Patched in 2026-06-20 audit.
35. `NEO-10` Contextual graph selection can drift when search, expand, and collapse all modify the same graph state. Status: Patched in 2026-06-20 audit.
36. `NEO-11` Some graph projections do not consistently preserve label, domain, and range metadata for ontology nodes.
37. `NEO-12` Graph connection state is still vulnerable to stale cache or stale closure effects on the client.
38. `NEO-13` Graph query results should validate that every visible edge has both endpoints in the visible slice.
39. `NEO-14` Some contexts can render orphan nodes, which makes the layout look broken even when the database is healthy.
40. `NEO-15` Search on very common terms can return too many matches without a clear relevance ordering.
41. `NEO-16` Some nodes represent XML tags rather than domain instances and need explicit filtering rules.
42. `NEO-17` Graph view nodes should highlight the root context consistently after any expansion.
43. `NEO-18` Expand/collapse needs stronger bookkeeping so a node can be toggled multiple times reliably. Status: Patched in 2026-06-20 audit.
44. `NEO-19` Graph view state should distinguish full graph, ontology graph, and contextual instance graph more strongly. Status: Patched in 2026-06-20 audit.
45. `NEO-20` `WHERE USED` style ancestry graph logic should not share the same state path as general graph search.
46. `NEO-21` Relationship thickness and arrow size need to be bounded by a consistent visual token system.
47. `NEO-22` Graph tooltip actions should only show when the selected node is truly actionable.
48. `NEO-23` Graph metrics endpoints should not be treated as a substitute for actual graph data.
49. `NEO-24` Graph queries should avoid returning disconnected clusters unless the user explicitly requests a global view.
50. `NEO-25` Graph rendering should preserve user focus and zoom state while new data is loading. Status: Patched in 2026-06-20 audit.

## Import Services
51. `IMP-01` Import workflows still overlap conceptually between structural upload, ontology creation, and semantic linking.
52. `IMP-02` `instance.link` depends on retained artifacts, so stale import state can leak into bridge generation.
53. `IMP-03` Some files still use legacy fallback parsing paths when the unified import service should be canonical.
54. `IMP-04` Large-file commits can hit gateway timeouts if progress is reported only at the end.
55. `IMP-05` Import stage labels do not always match the actual backend execution order.
56. `IMP-06` Progress can appear to hover at 92-94 percent while relationships are still being written.
57. `IMP-07` Some ontology selection fields appear multiple times in the UI, which confuses the user about which one is active.
58. `IMP-08` File metadata capture and semantic mapping are still too tightly coupled in some import flows.
59. `IMP-09` The same file can be treated as both a source document and an ontology source if the workflow is ambiguous.
60. `IMP-10` Import tasks should expose a clear retry path that preserves parsed state after timeout.
61. `IMP-11` Batch commit logic needs stronger backpressure signaling for very large relationship sets.
62. `IMP-12` Some import steps do not make the difference between preview, verify, and load explicit enough.
63. `IMP-13` Persisted jobs can be resumed in the frontend without a freshness check against the backend snapshot.
64. `IMP-14` Commit error handling should not overwrite the useful parsing state from earlier stages.
65. `IMP-15` Import workflow recommendations can suggest incompatible flows if file-type inference is too coarse.
66. `IMP-16` Some generated TTL files are created during import but not surfaced as first-class artifacts.
67. `IMP-17` Ontology creation workflows need clearer namespace and prefix capture rules.
68. `IMP-18` Some file-type branches still fall back to generic parsing when a specialized parser should be used.
69. `IMP-19` Import state does not always separate ontology creation from instance ingestion.
70. `IMP-20` Structural import can still create metadata-like nodes that later pollute contextual graph search.
71. `IMP-21` Relationship batches should be written with indexed merge keys only.
72. `IMP-22` The import UI can suggest a workflow before the user has enough context to know if it is valid.
73. `IMP-23` Some import timeouts are still handled as hard failures instead of resumable background jobs.
74. `IMP-24` The import preview and commit flows still use different state labels for related progress.
75. `IMP-25` Import result summaries need a cleaner separation between parsed rows, generated ontology, and committed graph counts.

## Export Services
76. `EXP-01` Ontology export was historically only available as an API payload, not a user-facing download. Status: Patched.
77. `EXP-02` Export currently depends on generated Turtle and RDFLib serialization, so source integrity must be validated before converting.
78. `EXP-03` `.owl`, `.rdf`, `.ttl`, and `.jsonld` exports need a single consistent naming and artifact scheme.
79. `EXP-04` Export downloads should not force expensive regeneration at click time for large ontologies. Status: Patched.
80. `EXP-05` Merge outputs need retained artifacts so users can download merged ontologies after the workflow finishes. Status: Patched.
81. `EXP-06` Semantic Bridge mapping exports should be available after link generation, not only after manual API calls. Status: Patched.
82. `EXP-07` Export errors should be logged without breaking the successful workflow result.
83. `EXP-08` Export artifact links should be surfaced consistently in the UI across import, merge, and semantic bridge flows. Status: Patched.
84. `EXP-09` JSON-LD export should preserve enough semantic bridge metadata to reconstruct the mapping review.
85. `EXP-10` RDF/XML export should be validated against the generated Turtle before download.
86. `EXP-11` OWL/XML export should not assume every Turtle graph serializes cleanly without RDFLib fallback.
87. `EXP-12` Export helpers should not overwrite or duplicate the user’s source file names.
88. `EXP-13` Artifact manifests should clearly distinguish reports from downloadable ontology files.
89. `EXP-14` Export endpoints need explicit timeout and content-disposition behavior for large files.
90. `EXP-15` Ontology merge export should be pre-generated in the background to avoid browser wait states.
91. `EXP-16` Semantic Bridge exports should be skipped cleanly when there are no candidate mappings.
92. `EXP-17` Exported merged ontologies should preserve source ontology context metadata.
93. `EXP-18` UI export controls should stay compact and not dominate the file action row.
94. `EXP-19` Export types need a single contract in frontend config, API client, and backend route naming.
95. `EXP-20` Some export artifacts are still report-shaped instead of file-shaped.
96. `EXP-21` Workflow artifact browsing should not require the user to know task internals.
97. `EXP-22` Long-running export or serialization should fail soft and create an error artifact rather than blocking the workflow.
98. `EXP-23` Export of merged ontology should support both ontology file and bridge mapping file sets.
99. `EXP-24` Export flows should be accessible from both Data Import and Semantic Bridge pages.
100. `EXP-25` Export responses should have consistent MIME types and filenames across browsers.

## Frontend
101. `FE-01` Graph Explorer is still the most visually fragile part of the app.
102. `FE-02` Search can still be mistaken for a graph dump if results and canvas are not clearly separated.
103. `FE-03` Contextual instance search needs a strict one-root, one-hop render contract.
104. `FE-04` Expand/collapse affordances can look active when they are not actually actionable.
105. `FE-05` Some graph toolbars are too wide and can overflow the screen on smaller viewports.
106. `FE-06` Toolbar buttons and icons need a consistent miniature size system.
107. `FE-07` Graph labels can overlap in dense canvases and make the page unreadable.
108. `FE-08` Search reset and chat refresh actions can flicker when state updates race.
109. `FE-09` Search results should be highlighted in the canvas, not only in a side list.
110. `FE-10` Search should be case-insensitive and should handle wildcard patterns predictably.
111. `FE-11` Some graph nodes still show technical IDs instead of domain labels.
112. `FE-12` Search input can be non-editable or appear blocked if the wrong overlay state is active.
113. `FE-13` Full graph, ontology graph, and contextual instance graph need distinct display rules. Status: Patched in 2026-06-20 audit.
114. `FE-14` Node tooltips can become blank if event handlers hold stale state.
115. `FE-15` Graph layout stability can degrade after repeated zoom, pan, and node click operations.
116. `FE-16` The page should not auto-refresh the graph while the user is exploring a search result.
117. `FE-17` Some view labels and helper text are redundant and reduce confidence.
118. `FE-18` Recommendation panels can use large alerts or oversized icons that feel unprofessional.
119. `FE-19` The frontend still has legacy/compatibility wording that should be reduced in visible labels.
120. `FE-20` Tab transitions can appear to lose selection state even when backend data is present.
121. `FE-21` The import pipeline UI can hide important workflow conditions behind too much explanatory copy.
122. `FE-22` Export controls should be visible after successful workflow completion, not buried in a separate page.
123. `FE-23` The ontology browser layout can overlap text and pagination if container sizes are not constrained.
124. `FE-24` Some action buttons rely on browser defaults rather than explicit compact UI styling.
125. `FE-25` The app needs stronger visual separation between review, search, and destructive admin operations.

## Parsers
126. `PAR-01` The OWL/RDF extractor path was previously advertised but not implemented. Status: Patched.
127. `PAR-02` OWL/RDF parsing needs an Owlready2-first, RDFLib-fallback strategy for sparse or unusual files. Status: Patched.
128. `PAR-03` The parser stack still has a TODO for a dedicated OWL/RDF extractor in the legacy abstraction layer. Status: Patched.
129. `PAR-04` XML parsing should distinguish true instance elements from XML wrapper metadata.
130. `PAR-05` PLMXML parsing should preserve id, uid, xmi:id, href, instanceRefs, and relatedRefs as stable references.
131. `PAR-06` Parser output should clearly track unresolved cross-references instead of silently dropping them.
132. `PAR-07` Some parsers still use regex-based extraction where streaming or tree-aware parsing would be safer.
133. `PAR-08` Parser fallback behavior should be logged with enough detail to support customer support.
134. `PAR-09` XSD-to-OWL conversion needs strict namespace preservation from the source schema header.
135. `PAR-10` XML parser outputs can create metadata nodes that should not be treated as domain instances.
136. `PAR-11` Large PLMXML files need streaming parse logic to avoid memory spikes.
137. `PAR-12` Duplicate IDs should be reported separately from duplicate labels.
138. `PAR-13` Parser-generated ontology classes should preserve source comments and annotations where possible.
139. `PAR-14` Parser-generated object properties should retain domain and range semantics instead of flattening to generic edges.
140. `PAR-15` Parser-generated TTL needs validation before it is committed or exported.
141. `PAR-16` Some parser modules still describe `legacy` or `fallback` behavior in a way that confuses release readiness.
142. `PAR-17` XMI parsing should preserve member-end and reference semantics consistently across exports.
143. `PAR-18` CSV and Excel parsers should clearly distinguish entity rows from attribute rows.
144. `PAR-19` Parser error handling should preserve partial output for review when full conversion fails.
145. `PAR-20` Generated ontology files should be immediately reproducible from the same input and metadata.
146. `PAR-21` Parsers should mark data-property candidates versus object-property candidates before merge time.
147. `PAR-22` The model should retain a provenance trail from parsed source element to ontology term.
148. `PAR-23` Parser output must keep semantic bridge metadata separate from core ontology semantics.
149. `PAR-24` Some parser adapters are still too coupled to specific file names and source directory assumptions.
150. `PAR-25` Ontology expressivity handling should not degrade complex OWL constructs into plain labels only.

## Ontology Expressivity
- `OWL-01` Class hierarchy should preserve `rdfs:subClassOf` and not collapse complex inheritance into a flat list.
- `OWL-02` Object properties should retain domain and range in both reasoning output and visual render paths.
- `OWL-03` Datatype properties should preserve datatype ranges instead of generic string fallback.
- `OWL-04` Annotation properties should be represented explicitly, not hidden inside generic metadata.
- `OWL-05` Individuals should be distinguishable from classes in both graph views and export artifacts.
- `OWL-06` Restriction constructs such as min/max cardinality should not be lost during conversion.
- `OWL-07` Equivalent-class and disjoint-class semantics need explicit handling.
- `OWL-08` Ontology expressivity should keep labels, comments, and synonyms for search and display.
- `OWL-09` Cross-ontology imports should not silently drop imported semantic terms.
- `OWL-10` SHACL validation should reflect OWL domain/range constraints as actual checks.

## Release Notes
- The highest-risk areas remain Graph Explorer, import timeout handling, ontology bridge clarity, and parser fidelity.
- The current branch already includes several Patched items; the rest are the remaining backlog for closure and hardening.
- For release, the next practical step is to turn this tracker into a working backlog board and close the `Open` items in Pareto order.



### Audit update - 2026-06-28 late release smoke

Closed / improved in this pass:
- Duplicate ontology uniqueness blocker: live `/api/v1/admin/ontology-duplicate-audit` returns HTTP 200 and `duplicate_group_count = 0` against the active `semantic` Neo4j database. Uniqueness constraints are already present per Neo4j schema notices.
- Stale backend routes: restarted backend on `0.0.0.0:8000`; live `/health` returns 200 and `/docs` returns HTML 200.
- Reports API customer validation: live `/reports` and `/api/v1/reports` return HTTP 200 with paged results. Report queries now filter obvious metadata/wrapper nodes (`GeneralRelation`, `RelationshipCarrier`, `AttributeContext`, `MetadataWrapper`) and `id*` display names.
- Recommendation semantic source selection: `Bearing` now resolves to `Bearing System` with source tag `Part` for similar-parts, manufacturing, and change-impact. The previous false resolution to `Bearing Life` requirement is fixed.
- Recommendation performance: similar-parts no longer calls external embedding/vector similarity by default. Embedding similarity is opt-in via `scope.use_embeddings`, avoiding customer `CRITICAL SLOW` logs when Ollama/embedding gateway is down.
- Change-impact query hygiene: removed stale lowercase `source`/`target`, `traceSubType`, `hasChildInstance`, and missing-property assumptions from the default customer-data path.
- Registered ontology export: `/api/v1/ontology/{ontology_id}/export?format=ttl|rdf|owl|jsonld` is available and Semantic Bridge/Ontology Junction exposes export links for active ontology outputs.
- XSD ontology generation: XSD `targetNamespace` is captured before registration, promoted into metadata, and generated semantic artifacts include TTL/RDF/OWL/JSON-LD.

Live smoke results:
- `/health`: 200
- `/docs`: 200
- `/api/v1/admin/ontology-duplicate-audit`: 200
- `/reports` overview: 200, total 2157
- `/api/v1/reports` traceability: 200, total 2277
- `/recommendations/similar-parts` for `Bearing`: 200, ~35 ms, source `Bearing System` / `Part`
- `/recommendations/manufacturing` for `Bearing`: 200, ~48 ms, source `Bearing System` / `Part`
- `/recommendations/change-impact` for `Bearing`: 200, ~38 ms, source `Bearing System` / `Part`

Remaining watch item:
- Report overview still includes `Document` business rows derived from PLMXML datasets. That is valid as a business object only if customer wants document/data-set entities in reports; otherwise add a UI/API report scope to include/exclude Document entities separately.

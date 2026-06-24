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

1. `IM-01` through `IM-12` remain largely open; import workflow clarity and stale ontology-selection risk are still the main import concerns.
2. Ontology Studio, Recommendations, Reports, Admin, and Where Used items below remain open unless explicitly marked otherwise.


## Audit update - 2026-06-21

Closed in current branch audit:

1. `AD-02` Prefix cleanup now supports optional property/value filters, so targeted deletion by ontology scope and import/job metadata is possible without falling back to raw Cypher.
2. `AD-03` Admin preview and execute now use one shared scope model, which keeps previewed and destructive cleanup parameters aligned.
3. Validation passed with `python -m py_compile backend/Services/neo4j_schema_cleaner.py backend/routes/admin_routes.py`, `pytest backend/tests/test_neo4j_fixes.py -q`, and `npm run build` (one unrelated ESLint warning remains in `GraphExplorerToolbar.js`).

## Fix order

1. Graph Explorer search and expand/collapse correctness.
2. Import workflow selection and ontology linkage clarity.
3. Ontology Studio alignment model and candidate visibility.
4. Admin cleanup and batched delete safety.
5. Reports filtering / export correctness.
6. Where Used search and hierarchy completeness.
7. Recommendation result rendering and readiness handling.

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
| IM-01 | Import | Workflow selection still mixes structural import with ontology linkage concepts. | Users do not know whether they are importing data, mapping it, or linking it. | `DataImportPipeline.js:707-760`, `1392-1453` | P0 | Open | Each workflow has one clear purpose and a single user action path. |
| IM-02 | Import | `instance.link` depends on retained artifacts from previous steps. | Linking can silently use stale source state. | `DataImportPipeline.js:748-753`, `1804-1808` | P0 | Open | Link only runs against the selected import artifact for the current session. |
| IM-03 | Import | Ontology selection is required in some flows but hidden behind multiple conditions. | Users cannot predict when the workflow is runnable. | `DataImportPipeline.js:731-763`, `1379-1453` | P0 | Open | The UI tells the user exactly when ontology selection is mandatory. |
| IM-04 | Import | Ontology creation is mixed with metadata capture and file-type inference. | The same file can appear to have several conflicting purposes. | `DataImportPipeline.js:316-406`, `1950-2029` | P1 | Open | XSD/OWL/STEP/XML paths are separated by intent, not just extension. |
| IM-05 | Import | Preview and commit state are tracked separately from the task state machine. | Progress can appear stuck at 92-94% or duplicate. | `DataImportPipeline.js:618-645`, `2340-2350` | P0 | Open | Progress is monotonic and tied to a single authoritative task. |
| IM-06 | Import | Timeout handling is long but not clearly surfaced to the user. | Large files look frozen during commit. | `DataImportPipeline.js:861-895`, `862-869` | P0 | Open | Large commit runs show a clear “background processing” state. |
| IM-07 | Import | `workflowApplyLinks` is only valid for one workflow but lives globally. | The toggle can be shown when it should not apply. | `DataImportPipeline.js:80`, `286-289`, `1439-1450` | P1 | Open | The checkbox only appears for semantic bridge linking. |
| IM-08 | Import | A number of stage labels imply work that may not be happening yet. | The pipeline reads like a promise rather than the actual backend path. | `DataImportPipeline.js:1024-1046`, `2021-2028` | P1 | Open | Stage names match backend behavior and are testable. |
| IM-09 | Import | Cached ontology catalog can outlive the live registry. | Users may select stale ontology options. | `DataImportPipeline.js:100-199` | P1 | Open | Registry refresh replaces stale cached options when available. |
| IM-10 | Import | Direct ontology files are routed through a special metadata form and can feel disconnected from the main pipeline. | Users do not know where ontology upload belongs. | `DataImportPipeline.js:316-406`, `1167-1180` | P1 | Open | The ontology upload path is visible and intentional. |
| IM-11 | Import | The selected ontology ID/prefix logic is reused across multiple workflows. | A wrong ontology can be applied to a file by accident. | `DataImportPipeline.js:439-490`, `757-763` | P0 | Open | Workflow payloads only include the ontology fields that apply. |
| IM-12 | Import | The pipeline can resume persisted files without a clear freshness check. | Stale UI state can re-run old tasks after restart. | `DataImportPipeline.js:231-266`, `691-704` | P1 | Open | Restarting the frontend does not reprocess completed jobs. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| ON-01 | Ontology Studio | The page mixes ontology browsing, dictionary tables, and alignment controls in one surface. | Users cannot tell what is the authoritative semantic bridge workflow. | `OntologyMapper.js:2054-2209`, `2261-2306` | P0 | Open | The page has a clear left-to-right semantic bridge flow. |
| ON-02 | Ontology Studio | A single ontology selector is used for multiple meanings. | Source ontology, target ontology, and active ontology blur together. | `OntologyMapper.js:1365-1397`, `2278-2292` | P0 | Open | Source and target selection are explicit and not duplicated. |
| ON-03 | Ontology Studio | Empty dictionary data silently falls back to taxonomy-derived data. | Users can mistake inference fallback for real ontology content. | `OntologyMapper.js:1658-1761` | P0 | Open | Fallback data is clearly marked and cannot masquerade as primary data. |
| ON-04 | Ontology Studio | Bridge candidate visibility was filtered by confidence thresholds before the user saw them. | Low-confidence but important suggestions disappeared too early. | `OntologyMapper.js:1405-1426`, `2381-2459` | P0 | Fixed | All preview candidates are visible; confidence/status is shown instead of silently filtering rows. |
| ON-05 | Ontology Studio | The alignment tab allowed editing by a generic mapping model instead of Semantic Bridge fields. | The app behaved like ontology-to-ontology merging only. | `OntologyMapper.js:1908-2009`, `2482-2684` | P0 | Fixed | Manual mapping now separates imported entity/attribute/relationship/metadata from ontology class/data/object/annotation property targets. |
| ON-06 | Ontology Studio | The ontology browser and alignment views are too coupled to the same selection state. | Switching views can reset the wrong state. | `OntologyMapper.js:2144-2209`, `2232-2340` | P1 | Open | Changing tabs does not erase the selected ontology or bridge candidate. |
| ON-07 | Ontology Studio | Selected ontology output is often shown as prefix/id metadata instead of domain meaning. | Users cannot tell what they are aligning against. | `OntologyMapper.js:2334-2339`, `2278-2287` | P1 | Open | The ontology header states purpose, prefix, and domain role clearly. |
| ON-08 | Ontology Studio | Ontology class/property lists can become empty even when reasoning has data. | The browser looks broken to users. | `OntologyMapper.js:507-511`, `707-756`, `867-875` | P0 | Open | Classes, object properties, and datatype properties always have a fallback presentation. |
| ON-09 | Ontology Studio | Taxonomy rendering uses a compact outline plus a browser mode that can diverge from ontology data. | The visual tree does not match the actual OWL model. | `OntologyMapper.js:342-607`, `664-1204` | P1 | Open | Browser view and taxonomy view show the same ontology facts. |
| ON-10 | Ontology Studio | Mapping vocabulary rows are derived from heterogeneous sources with different key conventions. | Duplicate or malformed mappings can appear. | `OntologyMapper.js:1648-1701` | P1 | Open | Mapping rows use one canonical schema before render. |
| ON-11 | Ontology Studio | The alignment view was not clearly scoped to instance-to-ontology mapping. | The user thought ontology merging was the main task. | `OntologyMapper.js:2222-2267` | P0 | Fixed | The panel is now explicitly labeled as instance-to-ontology bridge; ontology-to-ontology merge is called out as separate. |
| ON-12 | Ontology Studio | User-editable bridge mappings are not surfaced as a first-class review queue. | Corrections are hard to audit and approve. | `OntologyMapper.js:2475-2555`, `2570-2673` | P1 | Open | Review, approve, reject, and comment actions are visible. |

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
| WU-01 | Where Used | Search fallback only checked a narrow set of fields. | Valid nodes were not discoverable. | `WhereUsedView.js:24-75`, `189-244` | P0 | Fixed | A search term can match IDs, labels, ontology metadata, import metadata, and common business-object fields. |
| WU-02 | Where Used | Upward traversal assumes parents will always be returned in a single shape. | Parent hierarchy can truncate or skip nodes. | `WhereUsedView.js:196-301` | P1 | Open | Parent expansion works for multi-hop chains and missing intermediate nodes. |
| WU-03 | Where Used | Search results and hierarchy rows were displayed as separate grids without a direct link between them. | Users could not intuitively move from result to context. | `WhereUsedView.js:423-451`, `541-589` | P1 | Fixed | Clicking a search result row or its action button immediately loads the hierarchy for that node. |
| WU-04 | Where Used | The selected node could expand upward while search used a separate interaction path. | Second-click expansion felt inconsistent. | `WhereUsedView.js:189-244`, `478-588` | P1 | Fixed | Clicking a different result row updates the same selected-node hierarchy model before expansion. |
| WU-05 | Where Used | Ancestor-level counts are calculated from reconstructed links rather than a stable graph model. | The displayed depth can drift from the real traversal. | `WhereUsedView.js:256-289` | P2 | Open | Depth and ancestor counts match the traversal source. |


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

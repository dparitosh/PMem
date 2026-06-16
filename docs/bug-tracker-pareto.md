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

Still open after audit:

1. `GX-03` expanded-node state is still split across multiple refs/state holders and needs consolidation or stricter sync rules.
2. `GX-05` expand/collapse affordance correctness still needs live browser validation across ontology mode and instance mode.
3. `GX-06` search centering/highlight persistence still needs a browser-level closure pass after rerenders.
4. `GX-08` tooltip action buttons are wired in code but still need end-to-end browser validation for all three actions.
5. `IM-01` through `IM-12` remain largely open; import workflow clarity and stale ontology-selection risk are still the main import concerns.
6. Ontology Studio, Recommendations, Reports, Admin, and Where Used items below remain open unless explicitly marked otherwise.

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
| GX-01 | Graph Explorer | Search state can fall back to the full canvas during a focused search. | Users see the whole graph instead of the searched node context. | `GraphHEB.js:3943-3944`, `4708-4734` | P0 | Patched | Search for a node and verify only the focused subgraph renders until cleared. |
| GX-02 | Graph Explorer | Collapse bookkeeping can desync from visible nodes. | Collapse appears to fail even after the user clicks it. | `GraphHEB.js:3745-3793` | P0 | Open | Expand a node, collapse it, and confirm only the expansion slice is removed. |
| GX-03 | Graph Explorer | `expandedNodes`, `expandedNodesRef`, and `searchModeRef` are maintained separately. | The same node can expand in one interaction and fail in the next. | `GraphHEB.js:933`, `1023-1024`, `4345-4350` | P0 | Open | Expand node A, then node B, then collapse either one without losing state. |
| GX-04 | Graph Explorer | Search results are mixed with graph canvas results. | Users cannot tell whether search found nodes or just filtered edges. | `GraphHEB.js:1019-1020`, `1112-1113`, `5242-5251` | P0 | Patched | Search must render node-first results, not a generic graph dump. |
| GX-05 | Graph Explorer | Expand/collapse controls depend on the current slice only. | A node can show a plus/minus affordance that is not actually actionable. | `GraphHEB.js:2507-2508`, `4316-4370` | P1 | Open | Nodes with traversable neighbors show correct affordance in every mode. |
| GX-06 | Graph Explorer | Search centering can be lost when the graph re-renders. | The result is not visually anchored to the main context. | `GraphHEB.js:4708-4734` | P1 | Open | Search a node and keep it centered/highlighted after rerenders. |
| GX-07 | Graph Explorer | The ontology graph can still render labels inconsistent with data-bearing fields. | Users see label noise instead of useful value labels. | `GraphHEB.js:1877-1912`, `1944-1971` | P1 | Open | Full graph labels match the intended display rule for each node type. |
| GX-08 | Graph Explorer | Tooltip actions are embedded in node tooltips but not validated against result state. | The action buttons can appear to work while producing no visible result. | `GraphHEB.js:902-914`, `4408-4523` | P1 | Open | Click each tooltip action and confirm visible downstream output. |
| GX-09 | Graph Explorer | The graph can show nodes with metadata-only IDs that look like data. | XML tag wrappers pollute the instance graph. | `GraphHEB.js:1944-1971`, user-reported `id*` nodes | P0 | Open | Search and expand should exclude XML metadata-only wrappers unless explicitly requested. |
| GX-10 | Graph Explorer | View mode labels and result modes are overloaded. | Users do not know whether they are in full graph, ontology, or contextual instance mode. | `GraphHEB.js:1026-1028`, `4954-5056` | P1 | Open | Each mode has a distinct render contract and visible behavior. |
| GX-11 | Graph Explorer | Global SVG styling can leak into embedded icons if not scoped. | Small toolbar icons and graph canvas symbols can render inconsistently. | `GraphHEB.css`, scoped SVG rules | P2 | Open | Toolbar icons stay thumbnail-sized while the canvas still fills the panel. |
| GX-12 | Graph Explorer | Auto-refresh behavior can overwrite user focus while a search is active. | The user loses the selected node or sees flicker. | `GraphHEB.js:4820-4846`, `5156-5167` | P0 | Open | Search, expand, and pan interactions do not reset the canvas unexpectedly. |

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
| ON-04 | Ontology Studio | Bridge candidate visibility is filtered by confidence thresholds before the user sees them. | Low-confidence but important suggestions disappear too early. | `OntologyMapper.js:1402-1422`, `2386-2390` | P0 | Open | All candidates are visible with a confidence filter, not hidden. |
| ON-05 | Ontology Studio | The alignment tab still allows editing by a generic mapping model instead of Semantic Bridge fields. | The app behaves like ontology-to-ontology merging only. | `OntologyMapper.js:1947-1975`, `2570-2673` | P0 | Open | Instance entity, attribute, relationship, and metadata are mapped separately. |
| ON-06 | Ontology Studio | The ontology browser and alignment views are too coupled to the same selection state. | Switching views can reset the wrong state. | `OntologyMapper.js:2144-2209`, `2232-2340` | P1 | Open | Changing tabs does not erase the selected ontology or bridge candidate. |
| ON-07 | Ontology Studio | Selected ontology output is often shown as prefix/id metadata instead of domain meaning. | Users cannot tell what they are aligning against. | `OntologyMapper.js:2334-2339`, `2278-2287` | P1 | Open | The ontology header states purpose, prefix, and domain role clearly. |
| ON-08 | Ontology Studio | Ontology class/property lists can become empty even when reasoning has data. | The browser looks broken to users. | `OntologyMapper.js:507-511`, `707-756`, `867-875` | P0 | Open | Classes, object properties, and datatype properties always have a fallback presentation. |
| ON-09 | Ontology Studio | Taxonomy rendering uses a compact outline plus a browser mode that can diverge from ontology data. | The visual tree does not match the actual OWL model. | `OntologyMapper.js:342-607`, `664-1204` | P1 | Open | Browser view and taxonomy view show the same ontology facts. |
| ON-10 | Ontology Studio | Mapping vocabulary rows are derived from heterogeneous sources with different key conventions. | Duplicate or malformed mappings can appear. | `OntologyMapper.js:1648-1701` | P1 | Open | Mapping rows use one canonical schema before render. |
| ON-11 | Ontology Studio | The “Ontology Alignment” view is not clearly scoped to instance-to-ontology mapping. | The user thinks ontology merging is the main task. | `OntologyMapper.js:2054-2306` | P0 | Open | The main action path is instance data to ontology concepts. |
| ON-12 | Ontology Studio | User-editable bridge mappings are not surfaced as a first-class review queue. | Corrections are hard to audit and approve. | `OntologyMapper.js:2475-2555`, `2570-2673` | P1 | Open | Review, approve, reject, and comment actions are visible. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| RC-01 | Recommendations | Result renderers can return `null` for valid backend responses. | The user sees blank success states. | `RecommendationsTab.js:309-359`, `1170-1266` | P0 | Open | Every successful API response produces visible content. |
| RC-02 | Recommendations | Health/readiness defaults are permissive when the backend payload is incomplete. | The user can run a scenario that is not ready. | `RecommendationsTab.js:414-416` | P1 | Open | Missing health data shows “unavailable,” not “ready.” |
| RC-03 | Recommendations | Prefill event flow depends on `dt-rec-prefill` and a global window fallback. | The feature can look inconsistent across pages. | `RecommendationsTab.js:443-460` | P1 | Open | Graph tooltip actions and recommendation panel always sync. |
| RC-04 | Recommendations | The scenario entry point is stateful but not strongly validated against input type. | Wrong inputs can still trigger service calls. | `RecommendationsTab.js:463-491` | P1 | Open | Input validation is explicit per scenario. |
| RC-05 | Recommendations | Search/impact/manufacturing results use different internal shapes. | Consistent reporting and export become harder. | `RecommendationsTab.js:641-643` | P1 | Open | Result schema is normalized before render. |
| RC-06 | Recommendations | The page mixes business guidance and action triggers, which can overstate certainty. | Users may treat guidance as authoritative truth. | `RecommendationsTab.js:199-248`, `555-584` | P2 | Open | The panel clearly separates suggestion from decision. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| RP-01 | Reports | Report filtering assumes `row.type.split(',')[0]` is always valid. | Valid rows can disappear if type formatting differs. | `ReportsTab.js:227-230` | P0 | Open | Reports show all expected rows from the source dataset. |
| RP-02 | Reports | Column toggling stores `false` as the only hidden state. | A column can reappear unintentionally after repeated toggles. | `ReportsTab.js:349-353`, `785-786` | P1 | Open | Toggling a column on/off is stable across page changes. |
| RP-03 | Reports | Pagination resets on every filter or report change without preserving user intent. | The table jumps around during review. | `ReportsTab.js:266-304`, `917-941` | P1 | Open | Filters do not unexpectedly send the user back to page 1 unless necessary. |
| RP-04 | Reports | Relationship rows are built from graph edges, not necessarily from the same semantic scope as the search report. | Users can compare incompatible datasets in one panel. | `ReportsTab.js:141-177`, `517-585` | P1 | Open | Relationship reports clearly state their source scope. |
| RP-05 | Reports | Search report export and relationship export are handled through separate paths with different row shapes. | Export consistency is fragile. | `ReportsTab.js:467-493`, `949-951` | P1 | Open | Export output schema matches what the user sees. |
| RP-06 | Reports | Dynamic type tabs are derived from the current processed results only. | Tabs can vanish when the filter changes. | `ReportsTab.js:213-223`, `442-453` | P2 | Open | Tabs remain stable for the current dataset. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| AD-01 | Admin | Bulk delete requires either label or prefix, but the UX makes the destructive scope easy to misread. | A cleanup action can delete too much data. | `AdminPanel.js:177-192`, `388-418` | P0 | Open | Cleanup actions require an explicit scope preview and confirmation. |
| AD-02 | Admin | Prefix deletes forbid property/value filters. | The user cannot do targeted prefix-based cleanup. | `AdminPanel.js:183-192` | P1 | Open | Prefix cleanup supports safe filtering rules or is clearly scoped. |
| AD-03 | Admin | Preview state and destructive action state are separate and can diverge. | The user may preview one scope and execute another. | `AdminPanel.js:233-280`, `382-405` | P0 | Open | Preview and delete use the same exact query parameters. |
| AD-04 | Admin | Schema cleanup bundles nodes, relationships, metadata, indexes, and constraints into one irreversible action. | Recovery becomes hard and risky. | `AdminPanel.js:116-139` | P0 | Open | The UI clearly separates reset, purge, and targeted cleanup. |
| AD-05 | Admin | Registry state is read only, but the page still implies broader system control. | Operators may expect configuration edits that are not present. | `AdminPage.js:164-167` | P2 | Open | Read-only scope is explicit and stable. |
| AD-06 | Admin | Cleanup messages do not distinguish between graph data and ontology storage. | Users cannot tell what was actually deleted. | `AdminPanel.js:126-129`, `156-170` | P1 | Open | Deletion feedback splits graph, metadata, and file store outcomes. |

| ID | Page | Bug | Why it matters | Evidence | Priority | Status | Closure test |
|---|---|---|---|---|---|---|---|
| WU-01 | Where Used | Search fallback only checks a narrow set of fields. | Valid nodes are not discoverable. | `WhereUsedView.js:179-185`, `322-347` | P0 | Open | A search term can match IDs, labels, and common metadata fields. |
| WU-02 | Where Used | Upward traversal assumes parents will always be returned in a single shape. | Parent hierarchy can truncate or skip nodes. | `WhereUsedView.js:196-301` | P1 | Open | Parent expansion works for multi-hop chains and missing intermediate nodes. |
| WU-03 | Where Used | Search results and hierarchy rows are displayed as separate grids without a direct link between them. | Users cannot intuitively move from result to context. | `WhereUsedView.js:352-489` | P1 | Open | Selecting a result centers the hierarchy on that node. |
| WU-04 | Where Used | The selected node can be expanded upward, but search and expansion are not tied to the same selection model. | Second-click expansion can feel inconsistent. | `WhereUsedView.js:314-320`, `479-489` | P1 | Open | Clicking a different result always updates the same hierarchy view. |
| WU-05 | Where Used | Ancestor-level counts are calculated from reconstructed links rather than a stable graph model. | The displayed depth can drift from the real traversal. | `WhereUsedView.js:256-289` | P2 | Open | Depth and ancestor counts match the traversal source. |

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

# Frontend UI Component Audit

> Review history: see [current validation](audits/README.md) for the latest test counts, correction records and pending acceptance. Earlier counts and findings below belong to their original review.

## Capability separation update — 2026-10-24

The local source now uses capability workspaces under `frontend/src/features/`. PMem remains one React SPA. Routes, service endpoints, credential profiles, task IDs and governance gates are retained. This is an incremental refactor, not a claim that every controller or historical timing issue is resolved.

| Former entry file | Current owner | Lines before / current |
| --- | --- | ---: |
| `Components/OntologyMapper.js` | `features/ontology/OntologyWorkspace.js` | 3,453 / 1,865 |
| `Components/GraphHEB.js` | `features/graph/GraphWorkspace.js` | 4,284 / 2,829 |
| `Components/DataImportPipeline.js` | `features/import/ImportWorkspace.js` | 3,935 / 3,485 |
| `Components/RecommendationsTab.js` | `features/recommendations/RecommendationsWorkspace.js` | 1,200 / 214 |

The former entry files are removed, rather than retained as compatibility wrappers. Pages and tests import the new owners directly. Existing `Components/ontology/` inference, mapping review, merge controls, Steward review and publication components are reused.

### Ownership now separated

- Ontology browser, taxonomy view, vocabulary table, relation badges and bridge option/identity presentation are separate modules. `useOntologyImportTasks` owns the import registry and selected-task status/preview reads. Requirements browsing lives in `features/traceability/RequirementsWorkbench.js`.
- `GraphCanvas` owns its SVG and D3 teardown. `useGraphSimulation` owns rendering, simulation reconciliation and drawing listeners; `useGraphData` owns ontology/architecture reads and cancellation. `GraphFilters`, `GraphLegend` and `GraphInspector` own their corresponding presentations. Rendering receives explicit model, runtime refs and interaction callbacks. Simulation coordinates stay on layout copies.
- `useImportTaskTracking` owns status/preview polling. `ImportLoadReview` presents the selected preview and approval controls; the workspace continues to own the commit request. Existing metadata and publication components are reused.
- Recommendations separates its investigation controller from Change Impact, Similar Parts, Manufacturing, insight banners, primitives and graph/timeline visuals.
- Shared authorization and transport stay in the existing services. `ReadGoalPanel` delegates request lifecycle to `features/agents/hooks/useReadGoal`; it does not create another session manager.

### Behavioral corrections and verification scope

Polling and user actions have separate cancellation ownership. Cancellation responses must match the retained goal ID. Superseded ontology errors cannot overwrite a newer registry request. Selecting an import task no longer refetches its entire registry; status and preview responses are cancelled and masked by task identity while the selection changes. Import cleanup stops both initial and subsequent reads; an old read cannot cancel a replacement poller for the same task. Exhausted task-not-found reads expose recovery guidance instead of leaving an active poller without a timer. Graph scope changes and unmount abort superseded reads, and commit-handler identity changes do not restart graph loading.

Regression checks cover cancellation/recovery, credential changes, stale status and preview reads, graph loading, route teardown, layout-copy isolation, metadata updates, vocabulary pagination, import routing, merge review and publication holds. The standalone graph interaction check also verifies concurrent expansion, shared/exclusive branch collapse, stale root responses and stable simulation positions. The legacy deployment check now uses the moved ontology handler; its obsolete removed-shell-form evaluator was removed. Current access behavior remains covered by `readAccessVerification.test.js` and `AppShell.test.js`.

Final validation on 2026-10-24: **598 frontend tests passed across 108 files** (197.46 seconds); Vite production build passed with Node.js v24.22.0 and `--configLoader runner`. Both `frontend/tests/graph-interaction-regressions.mjs` and `infra/deployment/test-ontology-import-access.mjs` passed. The affected backend contract test `test_ingestion_routes_and_bridge_use_supported_contracts` passed (one selected test; the backend suite was not run in full). The build receipt lists the new feature sources and none of the removed entry modules. `git diff --check` passed.

Changes are local source, not yet committed, pushed or deployed. No live installation, database migration or end-user service acceptance is implied by these checks.

### Thorough follow-up: lifecycle and UI/UX

The follow-up reproduced and corrected an aborted optional preview clearing a newer poller, cleanup retaining old instance choices in Ontology Junction, and session expiry retaining prior ontology/recommendation evidence. Regression tests exercise these paths. Graph scope loads now clear prior-scope nodes before fetching and expose projection loading in the toolbar and canvas; a failed fetch cannot present the previous graph as the new selection.

UI/UX corrections include an explicit **Refresh ontology** control that retains the selected identity, selection guidance in place of fabricated zero-count inventory, wrapping browser panels and responsive inspector/stat grids, and a named graph-inspector close control. Graph toolbar button backgrounds no longer inherit a gradient that masks selected state. Invalid alpha suffixes on CSS-variable colour tokens use `color-mix`. Relationship colour, width and opacity remain owned by D3/type policy; legacy CSS overrides were removed so links agree with the legend. Shared data-grid rules live in `widgets/dataGrid.css`, rather than loading only after Graph Explorer is visited. Graph scrollbar styles are scoped to its container; obsolete global OWL grid overrides were removed.

Follow-up validation: **605 tests passed across 108 frontend files** (204.01 seconds), both standalone frontend checks passed, the production build passed, and `git diff --check` passed. The final CSS cleanup, inspector accessible-name edit and shared refresh-button styling were compiled in a subsequent successful production build. The earlier full test run remains recorded above for history.

A browser inspection used an isolated production preview on port 3002 because `http://127.0.0.1:3000/` refused connections. It verified the no-selection/service-unavailable layout and that refresh enters a disabled/loading state. This is not evidence of populated customer data or successful live API workflows. Real populated-graph styling/interaction, narrow-screen and dark-theme visual acceptance still need the running services. Existing testing-library warnings and vendor-chunk warnings remain visible. No database or live deployment was changed.

### Remaining work

The graph workspace still coordinates search, expansion and tooltip interactions; its canvas callback contract can be narrowed further. The ontology workspace still coordinates instance mapping and governed merge state. Import source selection, restoration and job-history row actions still share a substantial controller. `ReportsTab` has not been decomposed in this pass. Continue extracting these behavioral owners with regression checks, rather than replacing them with large props-only wrappers. Other capability directories should be introduced when those implementations are actually moved; empty placeholder directories are not an architecture change.

Live acceptance still needs route navigation while requests are active, reconnect/refresh of retained workflows, real ontology/instance loads, and approved graph publication against the target installation. Unit tests use mocked service boundaries. React testing-library deprecation/`act` warnings and the build's existing large vendor-chunk warning remain visible; they are not suppressed.

---

Date: 2026-07-05

Historical audit. Findings below describe the July snapshot unless explicitly updated. The active route registry is frontend/src/app/pageRegistry.js; consult it for the current page inventory.

## Scope

Audited React frontend component structure, navigation, API coupling, component size, known legacy UI code, and automated validation behavior.

## Summary Verdict

The frontend is functional in structure, but not yet cleanly componentized. The app shell and page routing are in reasonable shape, while the main release risk is concentrated in three oversized components:

- `frontend/src/Components/GraphHEB.js`
- `frontend/src/Components/OntologyMapper.js`
- `frontend/src/Components/DataImportPipeline.js`

These components mix API calls, workflow state, rendering, layout, event listeners, and domain logic. That makes bug fixing fragile and contributes to slow test/build validation.

## Navigation And Page Audit

Status: Mostly aligned.

- Workspace is removed from side navigation and now aliases to Graph Explorer.
- Side navigation labels are: Home, Import, Ontology Junction, Graph Explorer, Where Used, Recommendations, Reports, Admin.
- Page wrappers are thin and acceptable:
  - `ImportPage.js` wraps `DataImportPipeline`.
  - Updated 2026-10-06: `OntologyJunctionPage.js` is the routed ontology page. Its unused former-name compatibility export has been removed.
  - `GraphExplorerPage.js` wraps `GraphHEB` in `GraphWidget`.
  - Recommendations and Reports wrappers are simple panel shells.

## Component Size Risk

| Component | Approx. size | Risk |
| --- | ---: | --- |
| `GraphHEB.js` | 240 KB | Critical: graph rendering, search, D3 state, tooltip, toolbar, expansion, and legacy tree code are still coupled. |
| `OntologyMapper.js` | 184 KB | Critical: ontology browsing, dictionary, taxonomy, semantic bridge, merge, and export concerns are coupled. |
| `DataImportPipeline.js` | 142 KB | High: workflow selection, uploads, progress, polling, artifacts, ontology linkage, and commits are coupled. |
| `RecommendationsTab.js` | 64 KB | Medium: recommendation scenarios and output rendering need clearer separation. |
| `ReportsTab.js` | 48 KB | Medium: report rendering depends on multiple context shapes and customer data availability. |

## Critical Findings

### UI-01 Graph Explorer Legacy Tree Layout Code

Status: Fixed in the 2026-07-05 release-risk pass.

`GraphHEB.js` no longer contains the indented tree layout renderer, tree-expanded state, hidden `indented-tree` branch, or tree-row highlight branch. The graph explorer now keeps the force-directed/contextual graph path only.

Validation:
- `npm run build` compiled successfully.
- `GraphHEB.test.js` passed.
- `graphUtils.test.js` passed.

### UI-02 GraphHEB Remains Too Large For Reliable Release Fixing

GraphHEB still owns:
- data fetch
- search
- contextual graph
- D3 render lifecycle
- tooltip HTML and event binding
- recommendations buttons
- ontology view controls
- expand/collapse
- health polling

Recommended closure:
- Split into `useGraphData`, `useGraphSearch`, `useGraphExpansion`, `useD3GraphRenderer`, `GraphTooltip`, and `GraphExplorerToolbar`.
- Keep React as graph state source of truth.

### UI-03 Automated Frontend Checks

Status: Partially fixed.

`npm run build` now compiles successfully after Graph Explorer cleanup. Focused Graph Explorer and graph utility tests pass. `DataImportPipeline.routing.test.js` also passes after hiding the import workspace while the ontology metadata modal is active.

Remaining issue:
- The broader `DataImportPipeline.test.js` still times out in this session and needs test lifecycle cleanup, likely around async polling/mocks.

Recommended closure:
- Harden `DataImportPipeline.test.js` mocks/timers.
- Add page-level smoke tests for Import, Ontology Junction, Graph Explorer, Where Used, Recommendations, Reports, Admin.

### UI-04 Config Planned/Stale Endpoint Mappings

Status: Improved.

Removed unused stale import schema-stage mappings/wrappers for `convert-schema`, `parse-schema`, `process-stages-4-7`, and `map-ontology` from the frontend release surface. Live import upload/status/preview/pre-commit/commit/cancel/artifact routes remain untouched.

Remaining issue:
- A full frontend-to-OpenAPI route classification should still be generated for all optional document/report/admin routes.

### UI-05 Ontology Junction Naming Is Partially Updated

Updated 2026-10-06: navigation and the routed page use `Ontology Junction` / `OntologyJunctionPage`. The older internal OntologyMapper component remains in use; the unused page alias was removed.

Recommended closure:
- Rename page/component labels gradually without breaking imports.
- Customer-facing text should consistently say `Ontology Junction`.

## Component Findings By Area

### App Shell / Navigation

Status: Good.

- Navigation is centralized in `frontend/src/app/navigation.js`.
- Workspace is safely aliased to Graph Explorer.
- Icons are lucide-based and small.

Open cleanup:
- Rename `QualityPage` to a clearer page name if the visible label remains `Recommendations`.

### Import

Status: Functional but too large.

Risks:
- Upload, workflow intent, ontology linkage, retained artifacts, progress polling, and commit handling are in one component.
- Direct `fetch` is still used for commit while most API calls use wrappers.

Recommended split:
- `ImportWorkflowSelector`
- `ImportFileQueue`
- `ImportProgressPanel`
- `ImportArtifactList`
- `ImportCommitControls`
- `useImportTaskPolling`

### Ontology Junction

Status: Functionally broad, structurally overloaded.

Risks:
- Data Dictionary, Taxonomy/OWL, Mapping Vocabulary, Semantic Bridge, ontology merge, and export live in one component.
- Needs separate component ownership for table layout, bridge workflow, and export controls.

Recommended split:
- `OntologyDictionaryTab`
- `OntologyTaxonomyTab`
- `MappingVocabularyTab`
- `SemanticBridgeTab`
- `OntologyMergePanel`
- `OntologyExportControls`

### Graph Explorer

Status: Highest release risk.

Risks:
- Dead tree layout code remains.
- D3 event binding and React state are still in one file.
- Search/context/expand behavior is hard to validate because multiple states can drive visible graph data.

Recommended split:
- `useGraphDataset`
- `useGraphSearch`
- `useContextualGraph`
- `useGraphExpansion`
- `useD3GraphRenderer`
- `GraphTooltip`

### Where Used

Status: Medium risk.

Risks:
- Needs clearer customer-facing interpretation: selected business object and one-line “where used” explanation.
- Should continue using grid/table-first output; graph view should not be default unless explicitly needed.

### Recommendations

Status: Medium risk.

Risks:
- Recommendation scenarios need clearer distinction between rule/GDS/LLM outputs.
- Large alert/icon styling has been a repeated issue and should be controlled with shared alert/icon classes.

### Reports

Status: Medium risk.

Risks:
- Customer environment reports depend on graph data and ontology registry quality.
- Empty states must explain whether data is absent, backend is down, or ontology projection is missing.

### Admin

Status: Medium risk.

Risks:
- Destructive actions need careful confirmation and preview.
- Cache cleanup and Neo4j cleanup should stay visibly separate.

## Recommended Fix Order

1. Remove dead tree layout code from `GraphHEB.js`. Status: Fixed.
2. Split Graph Explorer search/context/expand logic into hooks. Status: Pending larger componentization.
3. Compare frontend API config to backend OpenAPI and mark stale/planned routes. Status: Partially fixed for stale import schema-stage routes.
4. Split Ontology Junction tabs into separate components.
5. Split Import workflow into smaller components and hooks.
6. Add page-level smoke tests.
7. Re-run frontend build/test with longer timeout and record result.

## Validation Performed

- Static component inventory completed.
- Navigation audit completed.
- API config spot-check completed.
- Legacy tree layout code removed from `GraphHEB.js`.
- `npm run build` compiled successfully.
- `GraphHEB.test.js` and `graphUtils.test.js` passed.
- `DataImportPipeline.routing.test.js` passed.
- `DataImportPipeline.test.js` still timed out and remains a test-hardening item.

## Release Position

Do not call the frontend fully componentized yet. It is usable, but the release risk remains concentrated in Graph Explorer, Ontology Junction, and Import due to oversized components and coupled state/rendering logic.


## Page hierarchy and nested-surface review — 24 October 2026

### Review basis

Reviewed the current route inventory, page composition and shared table/panel styles. Opened the 17 route views in the installed browser build to inspect initial/empty structure; some lazy views were still loading during that pass, so this is not an end-to-end workflow pass for every page. The installed build had no registered ontologies. Verified the changed populated ontology browser separately using synthetic data and the real React/AG Grid components, without creating customer records.

Guidance: [W3C headings](https://www.w3.org/WAI/tutorials/page-structure/headings/), [W3C region labels](https://www.w3.org/WAI/tutorials/page-structure/labels/), and [Carbon dashboard hierarchy](https://www.carbondesignsystem.com/building-blocks/data-visualization/dashboards). The design decision to reduce card nesting is a contextual judgment: these sources support clear hierarchy and labeling; they do not prescribe a universal prohibition on nested cards.

### Applied rules

- Use one visible surface for an independent task or work area. Embedded tables do not create another card inside it.
- State the section heading once. Retain table counts and column names that convey different information.
- Use dividers and spacing for summary metrics, rather than treating every number as an independent card.
- Keep controls, validation findings and approval evidence visible. Disclose secondary explanation only.
- Preserve focus indicators, keyboard tab navigation, selected IDs, pagination, filtering and publication controls.
- Keep the full hierarchy count separate from the bounded hierarchy preview count.
- Keep changes scoped to presentation. A global selector that strips every descendant border would remove useful table/control boundaries and was deliberately avoided.

### Page-by-page disposition

| Page | Finding and disposition |
|---|---|
| Home | Registry, graph status and Companion are independent tasks; retained their distinct sections. Shared widget styling now uses solid surfaces, smaller radii and no decorative shadow/blur. No content or service behavior changed. |
| Import | Workflow/source tabs and approval/recovery stages are meaningful boundaries; retained. Shared page/panel spacing reduced. No upload, validation or approval step hidden. |
| Data Flow | Run monitor, job definitions and run evidence remain separate task areas. Summary KPIs are compact divider-based metrics; lifecycle navigation no longer looks like four separate content cards. |
| Ontology Junction | Removed duplicate Hierarchy/Class Hierarchy and Semantic Tables/Classes headings. Embedded grids are flat within their single parent surface. Summary metrics have no individual boxes. Empty Inspector no longer occupies a card above the primary work. Selecting a term reveals details and scrolls them into view. Term-table modes use keyboard-accessible tabs with a labeled panel. |
| Data Catalog | Registry tables use the flat embedded table presentation; overview counts and lifecycle links use compact grouping. Retained source inventory versus published-product distinction. |
| Data Products | Same shared improvements as Catalog. Retained the separate contract/evidence/approval work because these are distinct decisions, not redundant decoration. |
| Metadata Registry | Outer page-wide panel is now a borderless workspace. Summary counts are divider-based and theme-aware. Asset governance dialogs and source-selection controls remain distinct. |
| Graph Explorer | Outer GraphWidget is embedded rather than another decorative card around the graph workspace. Canvas controls, legend and inspector remain separate functional areas. |
| Code Network | Source review found a toolbar, graph and investigation panels serving different roles; retained them rather than blanket-removing every boundary. Populated graph visual acceptance remains to be performed. |
| Modeling | Header, toolbar and summary use the page surface rather than three more cards. Diagram, model tree and inspector retain work-area boundaries. |
| ReqIF / Requirements | Source filter, refresh/import actions and requirements table remain in one work area. Shared panel rhythm applies; no additional extraction or visual shell was introduced. |
| QIF | Secondary digital-thread stage explanations are under a native disclosure. Selected-run metrics, mapping/version selectors and validation evidence remain visible. |
| Where Used | Removed outer GraphWidget card styling; retained object selection, usage summary and result grid as task-specific sections. |
| Data Quality | Already one evidence work area; retained execution-versus-quality distinctions and native table caption. Shared panel radius/shadow/spacing improvements apply. |
| Recommendations | Existing analysis tabs are meaningful. Method/scope disclosure is a simple divider section rather than another bordered card inside results. Decision-policy evidence remains visible. |
| Reports | Removed the outer Outputs panel/header/body around ReportsTab. The report workbench owns its headings and sections. |
| Admin | Operational, access, agent, service and maintenance tabs remain separate. Registry grids inherit the flat presentation; destructive confirmation and cleanup receipts are unchanged. |

### Shared implementation

`DataGridWidget` supports explicit embedded presentation while preserving standalone use. `RegistryWidget` uses it, supplies an accessible table/filter label and no longer removes the input focus outline. Empty tables use a compact message height rather than reserving a full populated-grid viewport. GraphWidget supports embedded composition. Shared panel/widget styles use solid theme surfaces, 8px radii and no decorative shadows.

### Visual evidence and limitations

[Populated ontology preview](../../outputs/ontology-flat-layout-review.png) and [selected-term details](../../outputs/ontology-flat-layout-selected.png) use a clearly labeled synthetic fixture. They prove the changed component renders and responds to selection; they are not screenshots of a migrated customer ontology. The fixture has been kept separate from application data and will be removed from the source tree after verification.

Responsive ontology columns now stack below 1000px; the previous resize handles and forced 56vh empty sections were removed. A 600px iframe viewport was visually checked and the ontology panes stacked without page-width overflow. This is a synthetic component check; dark-theme and populated live workflows across every page remain unverified. Source changes are in the review checkout; the installed frontend on port 3000 is a separate deployment and is not silently replaced by this review.


### Interaction correction and validation

Found and corrected a pre-existing Catalog/Data Products interaction mismatch: RegistryWidget forwards a row object, but the page read `event.data`, so clicking a row could not open its details. The page now consumes the shared row callback correctly. Added tests for both Catalog and Product views.

- Full frontend regression run: 606 tests across 109 files passed in 205.84 seconds, before the final row-selection correction.
- Final focused run after that correction: 24 tests across 3 files passed in 10.04 seconds, covering row selection, ontology scope/merge selection and flat browser keyboard/inspection behavior.
- All six initially affected page/workspace suites passed (32 tests), and the first related set passed (39 tests); counts overlap and are not additive.
- Production build results are recorded in the companion build log; existing vendor-chunk warnings and React act deprecation warnings are not suppressed.
- Temporary synthetic HTML/source/config/build/cache files and the preview server were removed after visual review. The installed frontend/backend services were not stopped or replaced.

Evidence: [full frontend test log](../../outputs/frontend-card-hierarchy-tests.log), [production build log](../../outputs/frontend-card-hierarchy-build.log), [600px preview](../../outputs/ontology-flat-layout-narrow.png). Temporary preview setup hit sandbox restrictions on dependency optimization; using the production build for the fixture allowed review without changing permissions or the installed dependency tree.


## 24 October 2026 — Business demo dataset and graph read audit

Audience: business stakeholders. Demonstrate product understanding, requirements, engineering/manufacturing differences, and evidence for a change decision. Keep schema registration, UUID/IRI details and service administration as supporting technical material. Do not equate successful import, a lexical match, or an impact heuristic with validated cross-source traceability.

### Verified source preparation

Seven PLMXML files in `SPLMXML` are byte-identical to the seven in `plmxml_individual`; use one canonical copy. The additional `SPLMXML/ECR-000011_A_2 4 1.xml` supplies the bearing-noise change request. MBD3D_BO contains two distinct ISO namespace XSDs (`bom.xsd` and `DomainModel.xsd`); do not present these as instance assemblies. XMI contains two different SugarPlant MBSE exports; they are not byte duplicates and must be reconciled before treating both as separate business models.

Live end-user import on port 3000, reviewed using the authorized local identity `pmem-ui-test`:

| Business source | File | Imported entities | Imported relationships |
|---|---|---:|---:|
| System requirements | 000098-Induction Motor System Req Specification.xml | 22 | 39 |
| Engineering product assembly | 000138_A_4-JuicePurification-InductionMotor.xml | 3283 | 5721 |
| Manufacturing BOM | 000740_A_2-mBOM_INDUTION_MOTOR_ASSEMBLY 1.xml | 704 | 1324 |
| Bearing-noise change request | ECR-000011_A_2 4 1.xml | 92 | 186 |
| Sum of four import receipts | | 4101 | 7270 |

These are per-import receipts, not deduplicated business-object counts or proof of semantic equivalence. No existing data was deleted. No customer backup/restore validation has been completed.

### Defects reproduced and correction scope

1. The successful structural import was searchable but Graph Explorer overview showed no graph data. `Neo4jPublisher.overview()` read published/legacy ontology terms only. Added bounded retained-instance selection requiring both `import_id` and `import_row_key`, with staged resources/chunks excluded. Preserve relationships between selected instance and ontology nodes and deduplicate candidates by Neo4j identity. RDF class metrics remain unchanged.
2. The graph's Impact action returned “No entity found” for the selected imported change request. Context lookup also selected ontology terms only. Added the same retained-instance eligibility without removing explicit node-ID, namespace/prefix or ontology scope filters.
3. Graph-mode controls were icon-only. Added visible Overview/Ontology/Processes/Instances captions and pressed-state semantics in the review frontend.
4. SVG forced a 720px minimum height and graph nodes/edges used CSS transition-all alongside D3 animation. Added a viewport-relative canvas minimum and removed blanket transform promotion/transition effects. This removes redundant rendering work; no FPS improvement is claimed without measurement.

Validation: 15 backend regression tests passed, including mixed ontology/instance overview, cross-type edges, bounded selection and scoped instance lookup. Five existing graph canvas/toolbar tests passed. Production frontend build passed in 16.03s with existing large-chunk warnings. Backend read fixes were backed up and copied to the installed app for restart/retest; frontend source changes require a separate matched-source deployment and are not yet claimed as live acceptance.

### Business walkthrough acceptance

Start from a named product or issue, rather than the entire graph. Show the source file and revision behind the selected record, then a small relevant neighborhood. Explain the distinction between source-provided relationships, proposed matches and approved semantic links. Show a clear missing-evidence state when impact cannot be established. Finish with the proposed review action and its owner. Catalog/product publication and quality results must be demonstrated only when real governed records exist; do not manufacture green status or analytical KPIs to fill empty pages.

Live graph evidence before correction: `outputs/business-demo-bearing-search.png` (66-node bearing search; useful for diagnosing clutter, not a final presentation view).


#### Follow-up: prevent a misleading business conclusion

The first live impact retest resolved the imported record, but exposed a critical pre-existing assumption: every adjacent record (including application references and revision metadata) was treated as an impacted part, giving the bearing issue 100/100. This is not acceptable business evidence. Change-impact context now requires explicit impact or traceability relationship types, discards unclassified technical neighbors, and reports `evidence_status=insufficient` with a null score when none qualify. Both graph-inspector and Recommendations views explain “impact unknown” and do not display a green zero or fabricated confidence. Positive results are labeled linked review candidates and the numeric indicator is explicitly heuristic.

Final targeted checks before deployment: 16 backend tests passed, including the 11-metadata-reference regression; 18 frontend tests passed, including both missing-evidence views. Another 6 graph search/page tests passed. Counts refer to distinct runs and overlap earlier results. Direct read-only Neo4j verification found 4,101 retained import records and a bounded five-node sample using the new overview predicate.

The matched frontend source was backed up and rebuilt in the installed app using its existing environment and Node.js 24.22.0; build passed in 17.97 seconds with existing vendor-chunk warnings. Backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/20261024-160752`. PostgreSQL/Neo4j data and credentials were retained. Live UI acceptance follows restart and is recorded separately from unit/build checks.


### Live business acceptance observations

- Final installed frontend: `index-PI-4lzWE.js`. Installed build completed in 15.62 seconds; backend services remain running. One lifecycle endpoint-validation attempt timed out on ingestion health after service readiness; a subsequent 30-second health probe returned 200 and the frontend was started separately. This transient timeout is recorded, not suppressed or described as an uninterrupted restart.
- Refreshed Graph Explorer renders the retained instance overview. Its visible slice was 528 nodes/478 links after client presentation filtering, not the complete import. Focused “Undesired noise” search returns 3 nodes/4 links. Corrected a further stale-state defect: the legend previously retained overview totals during search; it now describes the visible search results. Added a regression covering a one-node result over a two-node overview.
- The deployed Impact action resolves the selected change request and explicitly reports impact unknown, without a score, because no qualifying direct impact/traceability link was found. This is a bounded-neighborhood result, not proof that the change has no impact anywhere in the source set.
- Catalog's Ingested sources tab displays all four new completed tasks. It also retains older import history: the 14 records shown are history records, not 14 verified live graph datasets. Published product versions remain zero.
- Data Products exposes Structural analytics and Pipeline evidence as separate creation choices. Schema drafts and retained packages are zero; no dimensions/KPIs or product approvals were invented.
- Data Flow shows four configured baseline jobs, one worker and no durable runs. Data Quality accurately reports no retained quality evidence. Neither is a successful execution/quality acceptance test.
- Recommendations reports graph ready and offers agent/direct methods. The graph action was tested with exact record context; the separate agent investigation was not certified by this pass.
- Reports loads a bounded 1,176-row sample, explicitly distinguished from full RDF aggregation.
- Where Used resolves the selected issue and returns revision/master-reference neighbors. Business usability issue remains: similarly named records cannot be easily distinguished in the candidate list, and revision/master references must not be presented as proven physical assembly impact. Do not use that view as engineering approval evidence.
- Admin was inspected read-only; no cache purge, graph reset, schema deletion or history deletion was performed.
- Remaining routes (Home, Ontology Junction, Metadata Registry, Code Network, Modeling, ReqIF, QIF) received navigation/initial-render smoke checks only. The retained snapshots are `outputs/business-demo-page-smoke.json`. Async loading and detailed workflow completion on those routes remain unverified. Home/Ontology/Registry have no registered ontologies; Modeling has no loaded MBSE model. This is not full end-to-end acceptance of every page.

### Recommended business presentation sequence

1. Introduce the bearing-noise issue and the motor product context, with the business consequence and decision to be made.
2. Find the retained engineering assembly, manufacturing BOM, requirements and change source in Catalog. Explain provenance in business terms; keep IDs and schema details in the technical appendix.
3. Open a focused graph neighborhood and show the source record, its revision and source-provided connections. Use visible-scope counts, not total-import counts, for the displayed graph.
4. Ask what the change could affect. Show confirmed links separately from missing evidence. The current source set needs explicit semantic/impact linking before demonstrating a validated cross-source impact conclusion.
5. Close with review ownership and the next action. Demonstrate published data products, analytical KPIs, quality conformance and MBSE traceability only after their real source/model, execution evidence and approved contracts have been prepared.

Demo readiness is partial: source discovery and focused graph review are verified; a complete business decision workflow still needs semantic linking, an MBSE model import, retained quality runs and an approved product. Large-chunk warnings, resize/FPS/heap performance under larger workloads, full cross-page acceptance and backup/restore validation remain open. No claim of customer-release readiness is made.


Final search-state follow-up: immediate search after refresh reproduced a late-overview race. The ontology-selection effect reran when its loader callback changed after initial data arrived, resetting search even though the selected scope had not changed. Reset is now conditional on an actual scope change; overview updates do not replace active search data. Regression explicitly resolves the delayed overview inside React act after a completed search. Three search tests passed; the related scope/inspector run passed nine tests. Live immediate-submit retest preserved “Undesired noise” and the 3-node/4-link search result after background overview loading. Final installed bundle: `index-Dynvn4iC.js` (15.61-second build). Backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/search-state-20261024-162628`.

Graph relationship badges now use the shared readable relationship names and the highlight action no longer displays literal Unicode escape text. Final screenshot: `outputs/business-demo-impact-evidence.png`. This confirms the verified business-facing decision-support state; it does not close the remaining end-to-end, MBSE, ontology, quality/product or performance acceptance items listed above.

### 24 October follow-up: primary schema and instance bridge

- Fixed alphabetical namespace selection when bundling XSDs. Root references now determine the namespace; multiple independent namespaces require an explicit primary schema. The Teamcenter root and classification companion form a cycle, so the end-user path selected `schemas/PLMXMLSchema.xsd` first and resolved companions from the original folder. No namespace was hardcoded.
- Live UI registered Teamcenter PLMXML (`plmxmlschema_a7251ea743764fec`), submitted review and approval under the authorized `pmem-ui-test` identity, and verified publication: 6,202 resources and 18,979 relationships. Counts exclude staging and receipt nodes. Initial background verification temporarily reported uncertainty before the final receipt became available.
- Where Used now distinguishes source references from physical assembly usage, and shows source type, revision and source file in candidate rows. Frontend regression checks passed 37 tests across bundle, routing and Where Used suites. Installed bundle: `index-BoOFH7XA.js`.
- A live requirements bridge run exposed that substring checks on provenance fields (`source_filename`, source references) misclassified XML entities as relationships. The first run held two ambiguous Header property mappings; none was published. Fixed XML entity classification and added preserved `source_element_name` as a type signal. Explicit edge rows retain relationship classification. Backend regression suites passed 21 tests and 8 subtests after isolating unit tests from live graph transport.
- Targeted backed-up backend deployment: `logs/business-demo-backup/bridge-xml-20261024-171017`. Post-restart live bridge verification is recorded below when completed. This does not certify MBSE loading, quality/product publication or full customer acceptance.

Live bridge retest after restart completed (`run-1798b434-ac0b-4964-8cbe-7c7b94a9fd77`): 57 candidates, 7 policy-approved mappings published, 50 held. Receipt: `bridge-publication-27c6ab895f894d25b2bb21bba18b7beb`. This is classification evidence, not established cross-source impact or identity equivalence.

Mapping review presentation was replaced with one summary and a paginated table (25 proposals per page), decision filter, source/target identity, match score, main finding and evidence-on-demand. Removed the duplicate per-candidate hold-reason list and collapsed assessment scope/policy details. High scores do not override held decisions. Identically named targets retain their full IRI in the row; no candidate is silently dropped by pagination. Regression checks: 29 tests passed across review table, explanation and bridge workflow suites. Existing React test-utils deprecation warning remains. Deployment backup: `logs/business-demo-backup/mapping-table-20261024-171638`.

Compact mapping frontend build passed (32.09 seconds), installed asset index-Cg4xdoW5.js. Existing large-chunk warnings remain; this is not a graph performance certification.

Mapping grouping follow-up: proposals are now categorized by mapping purpose (entity classification, relationships, attributes, metadata) and grouped by retained source import/row/type identity. A source name appears once above competing target rows. Category and decision filters can be combined; pagination is by 25 source groups so alternatives are not split between pages. Same-name records from different revisions/imports are never merged by display name. Relevant regression suites: 25 tests passed. Targeted frontend backup: `logs/business-demo-backup/mapping-groups-20261024-172151`.

Grouped review production build passed in 15.32 seconds; installed asset index-BSWr43C7.js. Backend and database servers remained running.

Mapping workspace usability follow-up: reduced repeated agent instructions to a one-line sequence with expandable workflow help, keeping publication authorization visible. Added per-source collapse/expand and bulk controls; collapsed groups retain counts of targets and held/policy-approved/unassessed decisions. Added consistent button/select styling, keyboard focus indication and disabled-state styling scoped to the mapping workspace. No policy or publication access rules changed. Regression checks: 26 tests passed, including collapse/reopen and group summary retention. Backup: `logs/business-demo-backup/mapping-cockpit-20261024-174113`.

Production frontend build passed in 18.22 seconds; installed asset index-Czj-dqgN.js. Existing large-chunk warnings remain. Backend, PostgreSQL and Neo4j were not restarted for this UI change.

Flat-layout correction after end-user screenshot review: previous mapping child was an unconstrained flex item, so it shrank within an extra bordered selection panel. Removed both review borders/padding layers, made the mapping region a full-width flex row, and hid redundant stage/output cards specifically for instance linking. Completed-run controls and workflow policy are collapsed above results; errors stay visible. Summary and filters use compact wrapping toolbars. The table has explicit column proportions, sticky headers and a bounded keyboard-focusable scroll region; long IRIs use ellipsis with a full-value tooltip and remain available in evidence. No workflow authorization or publication logic changed. Regression suites: 46 tests passed (mapping table, bridge jobs, import routing). Backup: `logs/business-demo-backup/mapping-flat-20261024-182902`.

Flat layout production build passed in 16.49 seconds; installed asset index-BU5Fgh49.js. Existing large-chunk warnings remain. Frontend-only deployment; backend and databases retained.

Context-specific follow-up: instance linking no longer displays the XSD-registration checkbox/instructions or enclosing workflow-selector card. Registration settings remain available in the registration workflow. Import routing regression: 20 tests passed after this change. Backup: logs/business-demo-backup/mapping-context-20261024-183132.

Final context-specific production build passed in 16.08 seconds; installed asset index-BVbYI5yy.js.

Ontology alignment correction: the right pane's private tab bar, independently wrapping headings, top-aligned outer grid and differently wrapping pagination caused uneven vertical boundaries. Moved tabs to a common toolbar, shared the pane heading row through CSS subgrid, stretched both panes, and standardized pagination height within the ontology browser only. At narrow widths the panes stack with independent natural headings. Keyboard tabs and selected-term inspection regression passed. Backup: `logs/business-demo-backup/ontology-alignment-20261024-183748`.

Alignment build passed in 17.01 seconds; installed asset index-DiH7G7DN.js. Existing chunk-size warnings remain.

Live browser measurement confirmed both panes have identical top, bottom and height (718.92px), identical grid start/end positions, and identical pagination start/end positions. Evidence: outputs/ontology-panels-aligned.png.

### Cross-page visual consistency pass, 24 October

Read-only navigation audit covered Catalog, Data Products, Data Flow, Modeling, Registry, Reports, Admin, Recommendations and Graph. Navigation snapshots include initial/loading states; this is not full functional acceptance of those pages. Catalog received a settled screenshot review. No imports, approvals or maintenance actions were triggered.

Source findings and corrections:
- Added shared semantic success, warning/error surface, selected-state and on-primary text tokens for light/dark themes. Success is no longer aliased to navigation blue in shared widgets.
- Data Flow had literal light-theme status/text/background colors. Mapped these to the shared palette, preserving semantic status distinctions and textual labels.
- Modeling had many literal white/slate/navy surfaces and a generic `.panel-title` selector. Updated common surfaces/text/borders/actions to theme tokens and scoped the panel heading selector to Modeling. Domain-specific diagram accent colors remain intact.
- Reports chart cards now share heading rows through CSS subgrid and keep equal empty/chart regions. Shared service-card actions anchor to the bottom, and KPI labels reserve two lines so values remain aligned when labels wrap.
- Lifecycle cards and page intros wrap within their container rather than forcing a fixed width. This is scoped to the shared data workspace.

Validation before deployment: 32 tests passed across Data Flow, Data Products, Modeling, Admin and Reports categories. Existing React test-utils deprecation warnings remain. Backup: `logs/business-demo-backup/shared-visual-20261024-185004`. Large graph performance, all dialogs/responsive breakpoints, domain graph color legend contrast, and full interaction acceptance remain separate work; do not infer completion from this styling pass.

Shared visual build passed in 17.09 seconds; installed asset index-BZ-PWuHm.js. Frontend-only restart; backend and databases retained. Existing chunk-size warnings remain.

Live dark-mode audit additionally found literal page/tree backgrounds and a permanently dark canvas in Modeling. Replaced those remaining common surfaces and canvas label colors with theme tokens; preserved domain accent palette. Follow-up backup: logs/business-demo-backup/model-theme-20261024-185241. Modeling had no loaded diagram in this check, so populated model contrast remains unverified.

Final visual follow-up build passed in 16.68 seconds; installed asset index-DQjqDtzs.js.

Live verification: Modeling page/tree/canvas backgrounds now resolve to dark palette colors with light text. Data Flow dark-mode surface/status labels were inspected and original light preference restored. Reports chart-card measurements match within each row: first three cards top 705px, plot start 773px, bottom 1054px; next pair top 1066px, plot start 1134px, bottom 1415px. Data Flow KPI label wrapping required a final shared label-height correction; backup logs/business-demo-backup/flow-kpi-20261024-185434. Evidence: outputs/model-theme-dark.png, outputs/data-flow-theme-dark.png, outputs/reports-layout-light.png.

Final alignment build passed in 15.91 seconds; installed asset index-Cw0e45gh.js. No backend restart or data mutation during this visual audit.

Wide-screen margin audit: Catalog/Data Products/Data Flow shared `.data-cockpit` was capped at 1600px and centered, Recommendations at 1500px, and Home content at 1600px. Removed those workspace caps/auto margins, retaining normal page gutters, narrow-screen wrapping and bounded prose/dialog/column widths. Other inspected route containers did not have the same page-level cap. These gaps were layout margins, not missing data. Backup: logs/business-demo-backup/fluid-pages-20261024-185831.

Fluid workspace production build passed in 15.84 seconds; installed asset index-CY1EnhYZ.js. Existing chunk warnings remain.

### Contextual graph investigation verification (2026-10-24)

Frontend asset index-KUZFJwFI.js passed the business issue search (3 nodes/4 reference links), selected-node context, small-slice labels and dark-theme surface/text checks. A real read-only graph-analyst goal was submitted through the UI; it failed with goal rate limited before any tool actions. Provider availability and grounded answer quality remain an acceptance blocker, not a successful agent test. No publication or database changes were performed. Research and remaining benchmark scope are in contextual-graph-visualization-audit-2026-10-24.md.

## AP242 taxonomy timeout fix (2026-10-24)

Observed against retained draft `domain_model_40c563f76dee4839`, not a replacement import. Its Turtle artifact is 21,205,084 bytes with 315,976 triples. A direct cold taxonomy read took 35.8 seconds and extracted 71,041 terms / 204,126 links, exceeding the frontend's 30-second deadline before serialization/rendering.

Corrections: taxonomy-specific frontend deadline 120 seconds with the existing cancellation guard; striped locks coalesce same-artifact cold reads before entering the cached extractor; extracted-payload cache reduced to four entries; browser endpoint returns at most 10,000 terms / 20,000 endpoint-contained links with declared terms prioritized and exact retained totals/truncation in the summary. Full inventory and mapping callers retain the full extraction. The browser shows an explicit slice notice and full-artifact export guidance.

Validation: 14 frontend tests and two backend tests passed. Updated stale test mocks to honor the grid's ariaLabel and current mapping-workflow control. Pytest is not installed in the application runtime; backend tests were executed with unittest. Production build passed. Backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/ap242-taxonomy-20261024-233107`. Live retest follows deployment.

Live acceptance after restart, asset `index-BY3SJTa6.js`: the same AP242 draft loaded successfully through Ontology Junction. The browser displayed 6,379 classes and 3,621 properties within 10,000 retained terms, 10,097 in-slice axiom links, and the explicit 71,041-term / 204,126-link retained totals. Refresh completed without the prior timeout. Screenshot: `outputs/ap242-taxonomy-fixed.png`. Lifecycle remains draft/not published; no new import or publication was performed.

## Graph visualization live test (2026-10-24)

- Overview: grouped source slice 528 nodes / 478 links. Entity mode renders 528 circles with bulk labels suppressed. These are slice counts.
- Search `Undesired noise`: 3 nodes / 4 links, visible focused labels, exact selected-object investigation context.
- Teamcenter scope: 717 nodes / 900 links. The former `registered only` selector suffix contradicted live graph availability; replaced the unsupported claim with `graph status unverified` when catalog metadata has not verified graph state. Absent relationship counts no longer imply classes-only publication.
- AP242 draft scope: no graph records, as it is not published. Scope switching removed nodes correctly but retained an SVG-root Nodes: 3 counter. Fixed empty render to remove that counter and added populated-to-empty coverage.
- Return to ALL restores 528 nodes. No graph publication was requested or performed by this visualization test.
- 13 renderer/loading/grouping/search tests plus two toolbar tests passed. Production build passed. Backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/empty-graph-counter-20261024-234815`.
- Full multi-published-ontology cluster acceptance remains pending AP242 publication; this test does not establish FPS, huge-graph capacity, or graph-wide completeness.

Post-deploy verification (`index-CsRxheRd.js`): switching from a populated graph to AP242 yields zero node circles and zero stale count elements. Teamcenter then renders 717 nodes with matching Nodes: 717 counter. Screenshot: `outputs/graph-visualization-tested.png`. Dense schema rendering remains visually crowded and is not certified as a business-demo layout; scoped search/group drill-down is preferred. Layout/zoom benchmarking remains separate work.

## Four graph modes acceptance (2026-10-25)

Overview: 528 nodes / 478 links; grouped and entity presentations switch successfully. Ontology: Teamcenter restores its bounded 717-node / 900-link slice; unpublished AP242 returns no graph records and clears previous nodes/counter. Processes: no ArchiMate model is loaded; empty-state message is correct and previous SVG elements are cleared. A populated process scenario remains untested without a model.

Instances initially exposed two defects: overview grouping appeared in individual mode, and an ALL-scope search silently used the preferred registered ontology ID. Restricted grouping to ontology/ALL mode and removed the implicit fallback from contextual instance search. A registry-backed regression verifies the search has instances_only=true with no scope for ALL. Nine tests passed across search, canvas and toolbar. Production build passed, asset `index-UJTowM_z.js`; backup `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/graph-modes-20261025-000033`.

Live instance retest: Undesired noise resolves to three connected nodes, exact investigation context, and no overview group controls. Global Reset clears the query and returns to the Overview workspace. Screenshot: `outputs/graph-instances-mode-tested.png`. No publication or database cleanup occurred. This is functional mode acceptance, not a claim of performance certification or agent answer quality.

## Contextual instance traversal (2026-10-25)

UI search/traversal cases: `Undesired noise` gives three nodes/four Master Reference edges; expansion finishes, changes the control to collapse, and does not duplicate existing neighbors. Collapse restores expansion state. `INDUCTION MOTOR ASSY 5HP` gives two nodes/two Master Reference edges; expanding the related record and collapsing keeps counts stable. Inspector exposes the selected retained IRI and relationships. No additional hop records were revealed in these cases; this is not evidence of a complete BOM or downstream impact chain.

A no-match query after inspecting the assembly left the old graph and tooltip displayed. Corrected the no-match branch to cancel pending root traversal, clear expansion/selection/contextual rendering and hide the tooltip. It preserves the shared overview/base graph: clearing that shared state would retrigger the search effect. Added populated-to-no-match regression coverage. Eight tests passed, production build passed. Backup `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/instance-traversal-20261025-000450`.

Final live retest with asset `index-9ICEqG1R.js`: populated assembly -> inspected node -> no-match query settles to No Results Found, zero circles/counters, hidden tooltip and no selected agent context. Searching again recovers the bearing context; expansion shows three nodes/four edges and one collapse control. Screenshot: `outputs/contextual-instance-traversal-tested.png`. No new graph data was published.

## Induction motor contextual completeness correction (2026-10-25)

User screenshot correctly showed a master/reference pair, not an adequate contextual graph. Prior tests certified expansion mechanics without testing a business path through reified relationship records.

Read-only Neo4j inspection confirmed FND_TRACELINK and RELATEDREFS edges on the requirement revision and GeneralRelation records. Root cause: raw traversal was limited to one hop; normalization automatically collapsed relationship carriers, and sanitizeContextualGraph then kept only immediate root neighbors and discarded GeneralRelation nodes. Product -> revision -> GeneralRelation -> related revision requires three source hops.

Correction: contextual root and expansion requests use a bounded depth of three (existing backend limits retained), explicitly preserve relationship carriers in contextual normalization, and keep the root-connected component after metadata/schema filtering instead of one-hop pruning. Default normalization elsewhere remains unchanged. No same-name entities were merged, no relationships inferred, no graph records migrated or re-imported. Help text now explains three-hop source neighborhoods.

29 tests passed across search, rendering and graph normalization, including an explicit master/revision/trace/related-revision fixture. Production build passed; deployed asset `index-mfnswJhA.js`; backup `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/motor-context-20261025-003858`.

Live acceptance: exact query `induction motor` -> 10 nodes / 18 links including assembly and source change/problem/impacted-item records; expansion -> 23 nodes / 46 links; collapse -> 10 nodes. `Induction Motor System Req Specification` -> 14 nodes / 26 links including six FND_TraceLink records, Sugarplant, Motor Housing, Spacer, Power Supply, Busing/Rotor and Bearing subsystem specifications. These are retained source references, not a certified complete impact/BOM analysis. Screenshot: `outputs/induction-motor-context-fixed.png`.

## Restore business-context behavior after historical branch review (2026-10-25)

Compared local `codex/ontology-bridge-stability` and committed `2f3f8c8` GraphHEB history without changing branches or resetting current work. The diff shows contextual retrieval switched from getContextualSubgraph to searchUniversal, and Overview changed from a loaded-slice projection to universal node/relationship/property substring matches. One-hop sanitization predates the component split, so reverting file decomposition alone would not fix it.

Restored dedicated contextual business seed retrieval (best-match mode, no implicit ontology scope), retained bounded three-hop root traversal, and applied that connected-context path to Overview searches as well as Instances. Technical relationship carriers are projected to SOURCE_PATH connections using retained via_node_id and raw relationship-type evidence. These connections are undirected in the renderer and explicitly described as projections, not asserted direct edges. Root-connected business entities remain visible; unrelated components, non-business metadata nodes and schema terminals are filtered. Ontology browsing remains a separate schema mode.

29 tests passed, including business-context API routing, no-match clearing and master/revision/trace-path projection. Production deployment backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/business-context-restore-20261025-120403`. Live checks are recorded below after deployment.

Live restoration verified with final asset `index-0c7buupV.js`: Overview query induction motor -> six root-connected business records / six links. Expansion -> nine business records / fourteen links; collapse -> six. Instances shows the same six business records. Four collapsed source paths have no directional arrowheads; provenance remains in via_node_id and the projection explanation.

Live mode switching also exposed pre-settlement centering drift: programmatic zoom marked itself as user interaction, then the force layout moved nodes below the viewport. Corrected that distinction and fit settling search coordinates until actual user pan/zoom. Added viewport regression tests; 31 tests passed. All six nodes were measured inside the SVG after both mode loads; actual wheel zoom was also exercised. Screenshot: `outputs/business-context-restored.png`.

Application services were found stopped during verification and started through manage-depo Start. Readiness, PostgreSQL schema and existing credential validation passed; database servers were not stopped and no graph records were republished. Existing bounded-depth and sampling limits still apply; this is not a claim of whole-graph completeness.


### 2026-10-25 contextual graph evidence audit

Found and corrected loss of relationship-carrier provenance: projection and subsequent display deduplication previously keyed only on endpoints and relationship type. Separate source records between the same business entities could overwrite one another. Projected path identity now includes its carrier ID and canonical undirected endpoints. Normal asserted-edge deduplication is unchanged. Regression coverage verifies two distinct carriers survive normalization and SOURCE_PATH relabeling, while the reversed duplicate of the same path is deduplicated.

Validation: 32 tests passed across graph utilities, contextual search/state, canvas cleanup, and viewport fitting. `git diff --check` passed. Remaining audit coverage: business classification uses a fixed label list and needs AP242-specific type fixtures; populated process graph and multiple published ontologies are not yet certified. These tests do not establish database-wide completeness or rendering performance at large scale.


### 2026-10-25 follow-up: AP242 business types

Context filtering now reuses the existing CAD/STEP classifier, retaining PRODUCT_DEFINITION and SHAPE_REPRESENTATION alongside PLMXML business labels. Replaced semantic-role substring matching with exact role membership; the unrelated role `department` no longer matches `part`. Boolean parsing no longer treats the string `false` as a CAD business flag. Added a connected AP242 fixture with unrelated and disconnected controls. All 33 graph regression tests passed; production build and frontend restart succeeded (index-Dm6zQ2t9.js).

Live UI: induction-motor Instances search rendered six connected business objects. Processes returned an explicit no-ArchiMate-model-loaded message. AP242 selection returned no graph records. Thus populated process traversal and multiple published ontology visualization remain unverified because the required graph data is absent; registration alone is not evidence of Neo4j publication. Build still warns about chunks larger than 500 kB. Database data was not modified.


### 2026-10-25 enhancement follow-up: responsive context canvas

Bounded the SVG height to clamp(280px,56dvh,640px) and removed the workspace minimum of 82vh. Added ResizeObserver sizing and disposal so the simulation responds to container changes. Dragging now marks a manual interaction, preventing automatic viewport fitting from fighting the drag. Viewport extent calculation is linear without coordinate-array spreads and handles extreme extents without a minimum-scale clipping floor; fitting includes right-hand label space. Regression tests cover narrow containers, extreme positions, observer disposal, and two explicit ontology groups with a recorded semantic mapping.

Deployed production build index-bqbsCBi0.js; live Instances motor search rendered six nodes in a 1025x403 canvas with all six visible. AP242 lifecycle was inspected in Ontology Junction: draft, graph status not_published, no verified receipt. It is an unpublished dataset rather than a renderer failure. Processes has no imported ArchiMate graph. These two live acceptance scenarios remain pending source publication/import. No lifecycle approval was invented and no database data changed.

Reproducible CPU-only benchmark: frontend/tools/benchmark-graph-preparation.mjs, Node 24.22.0, ten repetitions per size, synthetic five-ontology grouping plus viewport fit. Median times: 750 nodes/749 links 1.28ms; 10,000/9,999 12.47ms; 100,000/99,999 121.86ms. This is not a browser rendering/FPS benchmark or a supported display-size claim. Existing >500kB bundle warnings remain. Backup/restore acceptance requires disposable PostgreSQL and Neo4j targets; requested from user before restoring anything.


Follow-up validation: 40 graph tests passed across six files. Neo4j online full backup succeeded (97,513,100-byte compressed artifact, transaction 3859) and restored into isolated workspace folders. Offline consistency check exited 0 with graph/index/count/property-owner checks. Detailed local evidence: outputs/neo4j-recovery-20261025/RECOVERY-RESULT.md and backup-manifest.json (outside repository). This does not certify a started secondary DBMS, role restoration, application query parity, or coordinated PostgreSQL/artifact recovery. Existing running databases were retained.

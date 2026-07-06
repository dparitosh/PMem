# Frontend UI Component Audit

Date: 2026-07-05

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
  - `OntologyStudioPage.js` wraps `OntologyMapper` but should eventually be renamed to `OntologyJunctionPage.js` for naming consistency.
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

Navigation says `Ontology Junction`, but page file/component names still use `OntologyStudioPage` and `OntologyMapper`.

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

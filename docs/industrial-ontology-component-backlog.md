# Industrial Ontology Component Backlog

This backlog turns the current codebase into a componentized industrial ontology platform.

It is intentionally scoped to the existing repo and avoids external platform assumptions.

## Goals

- split mixed-responsibility screens into focused components,
- separate governance, ontology, traceability, quality, graph, and agent concerns,
- keep ReqIF, semantic bridge, and inference capabilities usable while refactoring,
- make the platform easier to extend for design, engineering, and manufacturing use cases.

## Pending Bugs To Address In The Same Track

These are not separate from the refactor. They should be fixed as part of the same componentization work because they are caused by mixed responsibilities, weak boundaries, or fragile state handling.

### Frontend

- ontology loading can fail when the active ontology selection becomes invalid or when registry state refreshes out of order,
- ontology workbench state is still too coupled, which makes bridge and SWRL views easier to break when ontology data is slow or missing,
- metadata registry is still missing distinct ownership, glossary, and product-domain subviews,
- import and graph-heavy views still feel too coupled to page-local state and can expose loading latency or blank states,
- graph explorer performance still depends on broad query and render paths for large datasets.

### Python API

- `unified_data_import.py` is too large and still mixes parsing, validation, normalization, commit orchestration, and workflow state,
- `ontology_routes.py` bundles ontology browsing, mapping, SKOS, SWRL, inference preview, and pipeline behavior into one route file,
- `metadata_registry_routes.py` does not yet expose a full governance model for domains, products, glossary, or approvals,
- graph view and retrieval context services are still not fully separated, which affects GraphRAG and large graph performance,
- canonical metadata identity and provenance logic still need a dedicated service boundary.

## Priority 1: Core Gaps to Close

### 1. Canonical Metadata Model

Current gap:

- metadata concepts are spread across registry, ontology, import, and graph services.

Target:

- one internal schema for governed assets, ontologies, requirements, trace links, quality, and product/domain metadata.

Files involved:

- `backend/Services/metadata_*` to introduce
- `backend/routes/metadata_registry_routes.py`
- `backend/routes/ontology_routes.py`
- `frontend/src/contexts/OntologyContext.js`
- `frontend/src/pages/MetadataRegistryPage.js`

Refactor action:

- introduce canonical model classes and converters,
- stop using page-local state as the source of truth for metadata identity.
- move bug-prone identity, provenance, and selection logic into the canonical model layer so the frontend stops re-deriving it.

### 2. Governance Registry Layer

Current gap:

- registry page is mostly a source list with limited lifecycle controls.

Target:

- registry summary, asset table, ownership panel, lifecycle panel, sync status, and domain/product metadata.

Files involved:

- `frontend/src/pages/MetadataRegistryPage.js`
- `backend/routes/metadata_registry_routes.py`
- `backend/Services` registry-facing services

Refactor action:

- split the page into subcomponents,
- keep registry editing and lifecycle transitions in dedicated panels,
- add ownership/domain/product metadata to the registry model.
- make missing-governance states explicit instead of leaving the page to infer them from empty registry rows.

### 3. Ontology Workbench Split

Current gap:

- `OntologyMapper.js` mixes ontology browsing, mapping vocabulary, semantic bridge, inference preview, and SWRL validation.

Target:

- separate ontology browser, vocabulary panel, bridge workbench, inference workbench, rule editor, and export panel.

Files involved:

- `frontend/src/Components/OntologyMapper.js`
- `frontend/src/pages/OntologyJunctionPage.js`
- `backend/routes/ontology_routes.py`
- `backend/Services/ontology_*`
- `backend/Services/swrl_reasoning_service.py`

Refactor action:

- split the monolith component into feature-specific components,
- keep shared ontology selection and loading state in a smaller parent container,
- isolate SWRL UI and bridge UI from taxonomy browsing.
- centralize active ontology validation so bridge and SWRL panels do not inherit stale selection state.

### 4. Traceability Product Layer

Current gap:

- ReqIF and graph requirements are present, but traceability is not a first-class product layer.

Target:

- requirement list, requirement detail, trace links, impact analysis, and review panel.

Files involved:

- `frontend/src/pages/RequirementsPage.js`
- `frontend/src/Components/WhereUsedView.js`
- `frontend/src/Components/DataImportPipeline.js`
- `backend/Services/unified_data_import.py`
- `backend/Services/semantic_workflow_service.py`
- `backend/Services/graph_view_service.py`

Refactor action:

- move trace-specific logic out of generic import and graph views,
- create a dedicated traceability service boundary.
- ensure ReqIF-related loading and review states do not depend on the ontology workbench being available.

### 5. Quality Product Layer

Current gap:

- quality is partially represented in backend utilities, but not as a cohesive product layer.

Target:

- tests, suites, incidents, profiler summaries, and trust indicators.

Files involved:

- `frontend/src/pages/QualityPage.js`
- `backend/Services/ontology_quality_guard.py`
- `backend/Services/pipeline_stages_4_7.py`
- `backend/Services/data_import_service.py`

Refactor action:

- unify quality-related UI and backend helpers under a dedicated quality service and page.
- make quality states first-class rather than inferred from generic error or warning messages.

### 6. Graph and GraphRAG Context Layer

Current gap:

- graph traversal and retrieval context are spread across multiple services.

Target:

- a graph layer for visualization and a separate GraphRAG/agent layer for retrieval context.

Files involved:

- `frontend/src/pages/GraphExplorerPage.js`
- `frontend/src/Components/GraphExplorerToolbar.js`
- `backend/Services/graph_view_service.py`
- `backend/agent/chat.py`
- `backend/chains/vector.py`
- `backend/Services/agent_memory_service.py`

Refactor action:

- separate graph display concerns from agent context assembly,
- create a reusable context packaging service.
- add explicit load-size controls and result caps so graph pages do not stall on large datasets.

## Priority 2: Frontend Component Breakdown

### Metadata Registry

Current file:

- `frontend/src/pages/MetadataRegistryPage.js`

Split into:

- `RegistrySummaryCards`
- `RegistryAssetTable`
- `RegistryLifecyclePanel`
- `RegistryOwnershipPanel`
- `RegistrySyncStatusPanel`

### Ontology Junction

Current file:

- `frontend/src/Components/OntologyMapper.js`

Split into:

- `OntologyBrowser`
- `OntologyVocabularyPanel`
- `OntologyBridgeWorkbench`
- `OntologyInferenceWorkbench`
- `OntologyRuleEditor`
- `OntologyExportPanel`

### Requirements

Current file:

- `frontend/src/pages/RequirementsPage.js`

Split into:

- `RequirementList`
- `RequirementDetail`
- `TraceLinkPanel`
- `ImpactAnalysisPanel`
- `ReqIFImportReviewPanel`

### Graph Explorer

Current files:

- `frontend/src/pages/GraphExplorerPage.js`
- `frontend/src/Components/GraphExplorerToolbar.js`
- `frontend/src/Components/GraphHEB.js`

Split into:

- `GraphCanvas`
- `GraphFilters`
- `GraphLegend`
- `GraphOverlayPanel`
- `GraphNeighborhoodPanel`

### Import Pipeline

Current file:

- `frontend/src/Components/DataImportPipeline.js`

Split into:

- `ImportSourceSelector`
- `ImportPreviewPanel`
- `NormalizationStagePanel`
- `BridgeSuggestionPanel`
- `PublishStagePanel`

## Priority 3: Backend Service Breakdown

### Governance

Introduce service group:

- `backend/Services/governance/`

Add services for:

- registry canonicalization,
- glossary,
- domains,
- products,
- ownership,
- approvals,
- lifecycle.

### Ontology

Introduce service group:

- `backend/Services/ontology/`

Add services for:

- ontology registry,
- dictionary generation,
- mapping,
- bridge support,
- merge,
- taxonomy,
- SWRL/inference.

### Traceability

Introduce service group:

- `backend/Services/traceability/`

Add services for:

- requirement normalization,
- trace link generation,
- impact analysis,
- bridge evidence.

### Quality

Introduce service group:

- `backend/Services/quality/`

Add services for:

- checks,
- test suites,
- incidents,
- profiler summaries,
- scoring.

### Graph

Introduce service group:

- `backend/Services/graph/`

Add services for:

- visualization payloads,
- neighborhood queries,
- overlay generation.

### GraphRAG / Agent

Introduce service group:

- `backend/Services/rag/`

Add services for:

- context bundle generation,
- retrieval prep,
- citation packaging,
- agent memory augmentation.

### Sync

Introduce service group:

- `backend/Services/sync/`

Add services for:

- source-to-canonical mapping,
- drift detection,
- publish orchestration,
- import/export reconciliation.

## Priority 4: API Surface Cleanup

Current issue:

- request helpers are concentrated in one large client file.

Target:

- one API client per domain.

Split `frontend/src/services/apiClient.js` into:

- `ontologyApi.js`
- `registryApi.js`
- `importApi.js`
- `traceabilityApi.js`
- `qualityApi.js`
- `graphApi.js`
- `agentApi.js`

## Priority 5: State and Context Cleanup

Current issue:

- shared state is not broken out by capability.

Target contexts:

- `OntologyContext`
- `RegistryContext`
- `TraceabilityContext`
- `QualityContext`
- `GraphContext`

Refactor action:

- keep the current ontology context,
- add separate contexts for registry, traceability, quality, and graph views,
- avoid page-local duplication of loading and selection state.

## Priority 6: Safe Refactor Sequence

### Phase 1

- split UI into smaller components without changing routes,
- add domain API wrappers,
- preserve current backend endpoints.
- fix the current loading and invalid-selection bugs while splitting so the user-visible behavior improves immediately.

### Phase 2

- introduce canonical metadata models,
- move traceability and quality logic into dedicated services,
- keep old endpoints as compatibility wrappers.
- move selection, provenance, and loading-state logic into the new canonical model and context layers.

### Phase 3

- split backend routes by product layer,
- add sync and drift reporting,
- add domain/product metadata.
- introduce explicit error contracts for unavailable data so the frontend can render recovery states cleanly.

### Phase 4

- optimize GraphRAG and agent context assembly,
- refine industrial workflow views for design, engineering, and manufacturing.

## Immediate Next Tickets

1. Split `OntologyMapper.js` into ontology subcomponents.
2. Split `MetadataRegistryPage.js` into registry summary and governance panels.
3. Extract a canonical metadata model from backend registry and ontology services.
4. Define the traceability service boundary.
5. Define the quality service boundary.
6. Add explicit loading and invalid-selection handling to the ontology workbench and registry flow.
7. Split `unified_data_import.py` into parser, validator, normalizer, and commit orchestration services.

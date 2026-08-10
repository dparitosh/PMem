# Component Breakdown by Folder and Service

This document maps the current repository into a target component structure for an industrial ontology platform serving design, engineering, and manufacturing.

The goal is to make the codebase easier to reason about, refactor, and scale by separating governance, ontology, traceability, quality, and GraphRAG concerns.

## Frontend Folder Breakdown

### `frontend/src/pages`

Page-level route shells only.

Recommended ownership:

- `OntologyJunctionPage.js`
  - semantic workbench shell
  - should compose ontology browser, bridge, inference, and mapping subcomponents
- `MetadataRegistryPage.js`
  - governed metadata catalog shell
  - should not contain ontology editing logic
- `RequirementsPage.js`
  - ReqIF and requirement traceability shell
- `GraphExplorerPage.js`
  - graph inspection shell
- `QualityPage.js`
  - test, incident, and observability shell
- `ReportsPage.js`
  - exported report and audit shell
- `AdminPage.js`
  - admin and system control shell
- `ImportPage.js`
  - import and normalization orchestration shell

Recommended split:

- keep page files thin,
- move business logic into `components`, `contexts`, and `services`,
- keep only route composition and page-level state in pages.

### `frontend/src/Components`

Reusable feature components.

Current ownership map:

- `OntologyMapper.js`
  - ontology browser
  - semantic bridge
  - mapping vocabulary
  - SWRL-style validation
  - inference preview
- `DataImportPipeline.js`
  - import workflow orchestration
  - file ingestion progress
  - normalization and preview
  - bridge suggestion entry point
- `MetadataRegistryPage`-related tables/forms
  - should be split into `MetadataRegistryTable`, `RegistryGovernancePanel`, `RegistryStatusCards`
- `WhereUsedView.js`
  - traceability and reverse lookup view
- `ReportsTab.js`
  - report filters and export UI
- `RecommendationsTab.js`
  - recommendation display and ranking
- `GraphHEB.js`
  - graph rendering helper
- `GraphExplorerToolbar.js`
  - graph filtering and navigation controls
- `OntologyMetadataForm.js`
  - ontology registration metadata form
- `AdminPanel.js`
  - operational controls and admin actions
- `Chatbot.js`
  - agent/chat UI surface

Recommended future component splits:

- `ontology/`
  - `OntologyBrowser`
  - `OntologyVocabularyPanel`
  - `OntologyBridgePanel`
  - `OntologyInferencePanel`
  - `OntologyRuleEditor`
- `registry/`
  - `GovernedAssetTable`
  - `DomainPanel`
  - `GlossaryPanel`
  - `LifecyclePanel`
- `traceability/`
  - `RequirementWorkbench`
  - `LineagePanel`
  - `ImpactAnalysisPanel`
- `quality/`
  - `QualitySummary`
  - `TestSuitePanel`
  - `IncidentPanel`
- `graph/`
  - `GraphCanvas`
  - `GraphLegend`
  - `GraphFilters`

### `frontend/src/contexts`

Shared data orchestration and state.

Current ownership map:

- `OntologyContext.js`
  - registered ontologies cache
  - ontology refresh/polling
  - canonical ontology list for all pages

Recommended future contexts:

- `RegistryContext`
  - governed asset state
- `GlossaryContext`
  - glossary/domain/classification state
- `QualityContext`
  - test and incident state
- `TraceabilityContext`
  - requirement and lineage state

### `frontend/src/services`

API clients and thin service facades only.

Current ownership map:

- `apiClient.js`
  - all backend request helpers
  - should be broken into domain clients eventually

Recommended split:

- `ontologyApi.js`
- `registryApi.js`
- `importApi.js`
- `traceabilityApi.js`
- `qualityApi.js`
- `graphApi.js`
- `agentApi.js`

### `frontend/src/workflows`

Workflow definitions and UX state machines.

Current ownership map:

- `workflowEngine.js`
- `importPresentation.js`

Recommended role:

- define import, normalization, and bridge workflows
- keep workflow metadata out of page components

### `frontend/src/utils`, `frontend/src/hooks`, `frontend/src/widgets`, `frontend/src/styles`

Shared utilities and presentation primitives.

Recommended role:

- keep pure helper functions here
- avoid embedding workflow logic in these folders

## Backend Folder Breakdown

### `backend/routes`

HTTP boundary only.

Current ownership map:

- `ontology_routes.py`
  - ontology registry, dictionary, taxonomy, SKOS, SWRL, mappings, pipelines
- `metadata_registry_routes.py`
  - governed metadata APIs
- `oslc_routes.py`
  - OSLC integration
- `sysml_v2_routes.py`
  - SysML v2 integration
- `threedxml_routes.py`
  - 3DXML integration
- `admin_routes.py`
  - admin operations

Recommended future route splits:

- `governance_routes.py`
  - glossary, domains, classifications, policies
- `lineage_routes.py`
  - lineage, impact, traversal
- `quality_routes.py`
  - test suites, test results, incidents, profiling
- `traceability_routes.py`
  - requirement and bridge trace APIs
- `graph_rag_routes.py`
  - retrieval, context bundles, agent-ready graph views

### `backend/Services`

Core domain logic.

Current ownership map:

- `semantic_workflow_service.py`
  - semantic bridge workflow
  - mapping export
  - ontology-to-instance linking
- `swrl_reasoning_service.py`
  - SWRL parsing, validation, execution preview
- `semantic_taxonomy_service.py`
  - SKOS / taxonomy support
- `ontology_reasoning_service.py`
  - ontology reasoning and fallback dictionary generation
- `ontology_mapper_service.py`
  - legacy seed mapper and ontology mapping support
- `ontology_mapping_service.py`
  - ontology mapping operations
- `ontology_upload_manager.py`
  - upload and projection orchestration
- `ontology_quality_guard.py`
  - ontology file quality checks
- `graph_view_service.py`
  - graph traversal and graph views
- `data_import_service.py`
  - import orchestration
- `unified_data_import.py`
  - file detection, parsing, normalization, and import
- `workflow_registry.py`
  - workflow definitions
- `workflow_artifact_service.py`
  - artifact output and persistence

Recommended service groups:

- `governance/`
  - glossary, domains, classifications, policies, approvals
- `ontology/`
  - ontology projection, reasoning, validation, SWRL, mapping
- `traceability/`
  - requirement normalization, bridge generation, lineage, impact
- `quality/`
  - test execution, profiling, incidents, scoring
- `graph/`
  - graph querying, traversal, packaging for UI and GraphRAG
- `rag/`
  - retrieval, memory, embeddings, agent context
- `sync/`
  - external metadata synchronization and drift handling

## Recommended Ownership by Capability

### Metadata Registry

Should own:

- governed asset inventory
- source system registration
- namespace and prefix tracking
- lifecycle
- ownership
- sync status
- domain and product assignment

Should not own:

- ontology authoring
- rule validation
- inference
- bridge suggestion

### Ontology Junction

Should own:

- ontology browser
- dictionary generation
- mapping vocabulary
- semantic bridge
- inference preview
- SWRL validation
- ontology merge

Should not own:

- generic registry editing
- quality management
- source system onboarding

### Requirements / Traceability

Should own:

- ReqIF ingestion review
- requirement normalization
- source-to-ontology linking
- bridge review
- impact analysis
- evidence tracking

### Quality

Should own:

- tests
- results
- incidents
- profiler summaries
- certification / trust indicators

### Graph Explorer

Should own:

- graph visualization
- traversal
- lineage overlays
- bridge overlays
- asset context exploration

## Refactor Sequence

### Step 1

- extract API clients by domain
- keep current endpoints stable
- introduce service boundaries in backend without breaking routes

### Step 2

- split `OntologyMapper.js` into smaller ontology components
- split `MetadataRegistryPage.js` into registry and governance subcomponents
- move import workflow logic out of page shells

### Step 3

- add registry/governance canonical models
- add glossary/domain/product services
- add lineage and quality services

### Step 4

- introduce OpenMetadata sync adapter
- map external metadata objects into canonical internal objects
- publish graph updates and drift reports

### Step 5

- optimize for GraphRAG and agent context packaging
- add industrial use-case specific views for design, engineering, and manufacturing

## Folder-to-Service Contract Rules

1. Pages compose, services decide.
2. Components render, contexts coordinate.
3. Services own business rules and data transforms.
4. Routes validate and delegate.
5. Shared utilities stay pure.
6. GraphRAG should consume canonical context, not page state.

## Outcome

If we follow this breakdown, the codebase can grow from a single ontology workbench into a maintainable industrial ontology platform with explicit seams for governance, semantics, traceability, quality, and agent context.

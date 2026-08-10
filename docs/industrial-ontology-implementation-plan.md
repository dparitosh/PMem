# Industrial Ontology Implementation Plan

This plan turns the current architecture and backlog into an execution sequence for the existing repository.

It is designed to:

- address pending frontend and Python API bugs,
- componentize the current capabilities,
- preserve working user flows during refactor,
- and move the platform toward a maintainable industrial ontology architecture for design, engineering, and manufacturing.

## Execution Rules

1. Preserve current routes while splitting internals.
2. Fix user-visible loading and invalid-state bugs during the same pass as the refactor.
3. Introduce compatibility wrappers before moving callers.
4. Separate UI composition, state coordination, and business logic in each phase.
5. Avoid large cross-cutting rewrites in one step.

## Phase 1: Stabilize Current User Flows

Objective:

- reduce fragile runtime behavior before deeper splits.

Frontend files to touch:

- `frontend/src/Components/OntologyMapper.js`
- `frontend/src/pages/MetadataRegistryPage.js`
- `frontend/src/Components/DataImportPipeline.js`
- `frontend/src/pages/GraphExplorerPage.js`
- `frontend/src/Components/GraphExplorerToolbar.js`
- `frontend/src/Components/GraphHEB.js`
- `frontend/src/contexts/OntologyContext.js`

Backend files to touch:

- `backend/routes/ontology_routes.py`
- `backend/routes/metadata_registry_routes.py`
- `backend/Services/graph_view_service.py`
- `backend/Services/unified_data_import.py`

Implementation actions:

- centralize active ontology validation in the ontology workbench,
- make bridge and SWRL panels resilient to missing ontology data,
- make registry empty/error/loading states explicit,
- reduce graph explorer default load pressure for large datasets,
- isolate import preview and pending metadata state from page-level orchestration where possible,
- introduce clearer API error contracts for unavailable registry and ontology responses.

Definition of done:

- ontology junction does not blank out when selection refreshes,
- registry and import views show explicit fallback states,
- graph pages fail soft on large or unavailable data.

## Phase 2: Split the Frontend by Capability

Objective:

- break monolithic React files into feature components without changing routes.

### 2.1 Ontology Junction Split

Current file:

- `frontend/src/Components/OntologyMapper.js`

Create:

- `frontend/src/Components/ontology/OntologyWorkspaceShell.js`
- `frontend/src/Components/ontology/OntologyBrowser.js`
- `frontend/src/Components/ontology/OntologyVocabularyPanel.js`
- `frontend/src/Components/ontology/OntologyBridgeWorkbench.js`
- `frontend/src/Components/ontology/OntologyInferenceWorkbench.js`
- `frontend/src/Components/ontology/OntologyRuleEditor.js`
- `frontend/src/Components/ontology/OntologyExportPanel.js`

Move:

- taxonomy browsing into `OntologyBrowser`
- vocabulary mapping into `OntologyVocabularyPanel`
- semantic bridge flows into `OntologyBridgeWorkbench`
- inference preview into `OntologyInferenceWorkbench`
- SWRL rule editing/validation into `OntologyRuleEditor`
- export links and registry metadata into `OntologyExportPanel`

Keep in shell:

- active ontology selection
- shared loading state
- top-level tab routing

### 2.2 Metadata Registry Split

Current file:

- `frontend/src/pages/MetadataRegistryPage.js`

Create:

- `frontend/src/Components/registry/RegistrySummaryCards.js`
- `frontend/src/Components/registry/RegistryAssetTable.js`
- `frontend/src/Components/registry/RegistryLifecyclePanel.js`
- `frontend/src/Components/registry/RegistryOwnershipPanel.js`
- `frontend/src/Components/registry/RegistrySyncStatusPanel.js`

Move:

- summary cards
- asset listing
- lifecycle transition UI
- create-asset form
- registry messages and sync health display

### 2.3 Requirements and Traceability Split

Current files:

- `frontend/src/pages/RequirementsPage.js`
- `frontend/src/Components/WhereUsedView.js`

Create:

- `frontend/src/Components/traceability/RequirementList.js`
- `frontend/src/Components/traceability/RequirementDetail.js`
- `frontend/src/Components/traceability/TraceLinkPanel.js`
- `frontend/src/Components/traceability/ImpactAnalysisPanel.js`
- `frontend/src/Components/traceability/ReqIFImportReviewPanel.js`

### 2.4 Import Pipeline Split

Current file:

- `frontend/src/Components/DataImportPipeline.js`

Create:

- `frontend/src/Components/import/ImportSourceSelector.js`
- `frontend/src/Components/import/ImportPreviewPanel.js`
- `frontend/src/Components/import/NormalizationStagePanel.js`
- `frontend/src/Components/import/BridgeSuggestionPanel.js`
- `frontend/src/Components/import/PublishStagePanel.js`

### 2.5 Graph Explorer Split

Current files:

- `frontend/src/pages/GraphExplorerPage.js`
- `frontend/src/Components/GraphExplorerToolbar.js`
- `frontend/src/Components/GraphHEB.js`

Create:

- `frontend/src/Components/graph/GraphCanvas.js`
- `frontend/src/Components/graph/GraphFilters.js`
- `frontend/src/Components/graph/GraphLegend.js`
- `frontend/src/Components/graph/GraphOverlayPanel.js`
- `frontend/src/Components/graph/GraphNeighborhoodPanel.js`

Definition of done:

- routes remain unchanged,
- files are smaller and capability-focused,
- shared state is only held at the smallest necessary parent.

## Phase 3: Split Frontend Services and Contexts

Objective:

- stop using a single API client and page-local state for everything.

Current file:

- `frontend/src/services/apiClient.js`

Create:

- `frontend/src/services/ontologyApi.js`
- `frontend/src/services/registryApi.js`
- `frontend/src/services/importApi.js`
- `frontend/src/services/traceabilityApi.js`
- `frontend/src/services/qualityApi.js`
- `frontend/src/services/graphApi.js`
- `frontend/src/services/agentApi.js`

Current contexts:

- `frontend/src/contexts/OntologyContext.js`

Create:

- `frontend/src/contexts/RegistryContext.js`
- `frontend/src/contexts/TraceabilityContext.js`
- `frontend/src/contexts/QualityContext.js`
- `frontend/src/contexts/GraphContext.js`

Implementation actions:

- keep `OntologyContext` as the first stabilized shared context,
- move registry asset caching into `RegistryContext`,
- move requirement and impact-analysis state into `TraceabilityContext`,
- move graph load controls and selection into `GraphContext`,
- move quality signals into `QualityContext`.

Definition of done:

- API calls are grouped by capability,
- page components no longer import one giant service surface,
- shared state is capability-scoped instead of page-scoped.

## Phase 4: Introduce Canonical Metadata Models

Objective:

- establish a clean internal contract across registry, ontology, traceability, and graph layers.

Backend files to create:

- `backend/Services/governance/canonical_metadata_service.py`
- `backend/Services/governance/metadata_identity_service.py`
- `backend/Services/governance/metadata_provenance_service.py`

Backend files to refactor:

- `backend/routes/metadata_registry_routes.py`
- `backend/routes/ontology_routes.py`
- `backend/Services/semantic_workflow_service.py`
- `backend/Services/graph_view_service.py`

Introduce canonical objects for:

- `GovernedAsset`
- `OntologyAsset`
- `RequirementAsset`
- `TraceLink`
- `QualitySignal`
- `LineageEdge`
- `ProductDomain`

Implementation actions:

- define ID and provenance rules once,
- stop reconstructing identity in page code,
- expose normalized response shapes from registry and ontology endpoints.

Definition of done:

- ontology and registry APIs return stable IDs and provenance,
- frontend selection logic does not need ad hoc fallback derivation.

## Phase 5: Split Backend Services by Product Layer

Objective:

- move away from large mixed-responsibility service modules.

### 5.1 Governance Service Group

Create:

- `backend/Services/governance/registry_service.py`
- `backend/Services/governance/ownership_service.py`
- `backend/Services/governance/lifecycle_service.py`
- `backend/Services/governance/domain_service.py`
- `backend/Services/governance/glossary_service.py`

Refactor from:

- `backend/routes/metadata_registry_routes.py`

### 5.2 Ontology Service Group

Create:

- `backend/Services/ontology/ontology_registry_service.py`
- `backend/Services/ontology/ontology_dictionary_service.py`
- `backend/Services/ontology/ontology_bridge_service.py`
- `backend/Services/ontology/ontology_inference_service.py`

Refactor from:

- `backend/Services/ontology_mapping_service.py`
- `backend/Services/ontology_mapper_service.py`
- `backend/Services/ontology_reasoning_service.py`
- `backend/Services/swrl_reasoning_service.py`

### 5.3 Traceability Service Group

Create:

- `backend/Services/traceability/requirements_service.py`
- `backend/Services/traceability/trace_link_service.py`
- `backend/Services/traceability/impact_analysis_service.py`

Refactor from:

- `backend/Services/semantic_workflow_service.py`
- `backend/Services/unified_data_import.py`
- `backend/Services/graph_view_service.py`

### 5.4 Quality Service Group

Create:

- `backend/Services/quality/quality_summary_service.py`
- `backend/Services/quality/test_suite_service.py`
- `backend/Services/quality/incident_service.py`

Refactor from:

- `backend/Services/ontology_quality_guard.py`
- `backend/Services/pipeline_stages_4_7.py`
- `backend/Services/data_import_service.py`

### 5.5 Graph and RAG Service Groups

Create:

- `backend/Services/graph/graph_overlay_service.py`
- `backend/Services/graph/graph_neighborhood_service.py`
- `backend/Services/rag/context_bundle_service.py`
- `backend/Services/rag/retrieval_context_service.py`

Refactor from:

- `backend/Services/graph_view_service.py`
- `backend/agent/chat.py`
- `backend/chains/vector.py`
- `backend/Services/agent_memory_service.py`

Definition of done:

- service files match product capabilities,
- large service files become smaller adapters or compatibility layers.

## Phase 6: Break Up `unified_data_import.py`

Objective:

- split the import monolith while preserving current file support.

Current file:

- `backend/Services/unified_data_import.py`

Create:

- `backend/Services/import/file_detection_service.py`
- `backend/Services/import/parser_router_service.py`
- `backend/Services/import/preview_builder_service.py`
- `backend/Services/import/normalization_service.py`
- `backend/Services/import/commit_orchestrator_service.py`
- `backend/Services/import/task_state_service.py`

Move responsibilities:

- file detection
- parser dispatch
- preview generation
- normalization
- Neo4j commit orchestration
- import task persistence

Definition of done:

- parser failures do not require reading one giant file,
- commit orchestration is isolated from parser logic,
- import task state is managed in one place.

## Phase 7: Split Routes by Product Layer

Objective:

- align route files with platform capabilities instead of technical history.

Create:

- `backend/routes/governance_routes.py`
- `backend/routes/traceability_routes.py`
- `backend/routes/quality_routes.py`
- `backend/routes/graph_routes.py`
- `backend/routes/rag_routes.py`

Keep temporarily:

- `backend/routes/ontology_routes.py`
- `backend/routes/metadata_registry_routes.py`

Implementation actions:

- add compatibility imports and delegating handlers first,
- migrate callers after the new services are stable,
- remove duplicate logic only after routing parity is verified.

## Phase 8: Verify and Harden

Objective:

- validate that the componentized system still supports existing industrial workflows.

Verify:

- ontology loading and export
- semantic bridge preview and add/apply flow
- SWRL validation and inference preview
- metadata registry asset creation and lifecycle transition
- ReqIF requirement browsing and trace review
- graph explorer loading behavior on medium and large datasets
- import preview, commit, and publish flow

Add tests around:

- ontology selection invalidation
- registry empty/error states
- import task lifecycle
- graph result caps and fallback behavior
- canonical metadata ID/provenance normalization

## Recommended Starting Sequence

1. Stabilize ontology junction and registry loading states.
2. Split `OntologyMapper.js`.
3. Split `MetadataRegistryPage.js`.
4. Split `apiClient.js` by capability.
5. Introduce canonical metadata services.
6. Break up `unified_data_import.py`.
7. Split backend services by product layer.
8. Split routes after service boundaries are stable.

## Deliverables

By the end of this plan, the repo should have:

- smaller feature-focused React components,
- capability-scoped contexts and API clients,
- canonical metadata services,
- dedicated governance, ontology, traceability, quality, graph, and RAG service groups,
- and a safer path for future industrial ontology features.

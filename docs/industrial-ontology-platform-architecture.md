# Industrial Ontology Platform Architecture

## Purpose

This document describes the target architecture for the current codebase only.

The goal is to industrialize and componentize the app into a maintainable ontology platform for design, engineering, and manufacturing. The focus is on:

- identifying gaps in the current repo,
- separating capabilities into clear services and UI components,
- reducing coupling between registry, ontology, traceability, quality, and graph exploration,
- and making the platform easier to extend without turning it into one large monolith.

## Current State

The repo already contains useful capabilities, but they are bundled too tightly:

- `Metadata Registry` is acting as a lightweight registry and governance boundary.
- `Ontology Junction` is doing ontology browsing, vocabulary mapping, semantic bridge, and SWRL preview all in one place.
- `Requirements` is handling ReqIF and graph requirements review.
- `Graph Explorer` is handling generic graph inspection.
- `Import` is handling ingestion and normalization.

These are good building blocks, but they need to be split into explicit platform layers.

## Core Gaps in the Current Codebase

### 1. Missing Canonical Metadata Layer

The codebase does not yet have a stable internal metadata model that cleanly separates:

- governed assets,
- ontology assets,
- requirements,
- trace links,
- lineage,
- quality,
- and product/domain concepts.

Today, these concerns are partially inferred from the same records or moved around in page logic.

### 2. Missing Governance Product Layer

The `Metadata Registry` page is not yet a full governance product. It needs:

- asset ownership,
- stewardship,
- lifecycle workflows,
- approvals,
- glossary/term management,
- domain and product grouping,
- policy linkage,
- and quality status at a glance.

### 3. Missing Semantically Clean Ontology Layer

`Ontology Junction` currently bundles several semantic responsibilities together:

- ontology browsing,
- mapping vocabulary,
- semantic bridge,
- ontology merge,
- inference preview,
- SWRL-style validation.

This should be componentized so each function is a separate feature module.

### 4. Missing Traceability Layer

ReqIF and engineering traceability are present, but the platform still lacks a distinct traceability product layer for:

- design-to-requirement mapping,
- part/function/behavior trace links,
- change impact navigation,
- bridge evidence,
- and review states.

### 5. Missing Quality Layer

Quality is not yet a first-class product area.

The codebase lacks a cohesive UI and service model for:

- test definitions,
- test suites,
- execution history,
- incidents,
- profiling,
- quality scoring,
- and certification/trust indicators.

### 6. Missing GraphRAG/Agent Layer

The repo has GraphRAG-adjacent pieces, but the context packaging layer is still distributed across several services.

It needs a single layer responsible for:

- canonical context bundles,
- retrieval context selection,
- citation-ready graph snippets,
- agent-friendly summaries,
- and memory injection.

## Target Platform Layers

### 1. Governance Layer

Owns:

- registry of governed assets,
- lifecycle,
- ownership,
- governance status,
- glossary and term linkage,
- domain/product grouping,
- approval state.

### 2. Canonical Metadata Layer

Owns:

- normalized internal metadata objects,
- consistent IDs,
- source provenance,
- source-to-canonical mapping,
- drift detection.

### 3. Ontology Layer

Owns:

- ontology browsing,
- vocabulary and synonym mapping,
- bridge suggestion,
- ontology merge,
- rule validation,
- inference preview.

### 4. Traceability Layer

Owns:

- requirement normalization,
- ReqIF review,
- engineering trace links,
- impact analysis,
- evidence-backed mapping records.

### 5. Quality Layer

Owns:

- data and ontology quality checks,
- test suites,
- incident tracking,
- profiler outputs,
- trust indicators.

### 6. Graph Layer

Owns:

- graph traversal,
- graph visualization,
- lineage navigation,
- bridge navigation,
- context overlays.

### 7. GraphRAG / Agent Layer

Owns:

- context packaging,
- retrieval tuning,
- answer grounding,
- memory augmentation,
- agent-ready summaries.

## Current Componentization Plan

### Metadata Registry

Current behavior:

- lists ontology sources and governed registry entries,
- shows prefix, namespace, lifecycle, and projection status.

Gaps:

- no dedicated domain/product model,
- no glossary UI,
- no ownership workflow,
- no version history / approval surface,
- no quality summary,
- no traceability to downstream usage.

Componentize into:

- `RegistrySummaryCards`
- `RegistryAssetTable`
- `RegistryLifecyclePanel`
- `RegistryOwnershipPanel`
- `RegistrySyncStatusPanel`

### Ontology Junction

Current behavior:

- ontology selection,
- class/property browsing,
- mapping vocabulary,
- semantic bridge,
- inference preview,
- SWRL rule validation.

Gaps:

- all semantic concerns are in one screen,
- shared selection state drives too many downstream views,
- no dedicated subcomponents for bridge review, rule editing, or inference output,
- weak separation between ontology registry data and ontology modeling behavior.

Componentize into:

- `OntologyBrowser`
- `OntologyVocabularyPanel`
- `OntologyBridgeWorkbench`
- `OntologyInferenceWorkbench`
- `OntologyRuleEditor`
- `OntologyExportPanel`

### Requirements Workbench

Current behavior:

- requirement review,
- ReqIF support,
- graph-backed requirement browsing.

Gaps:

- no structured traceability product layer,
- limited linkage to product/domain objects,
- no consistent impact-analysis workflow.

Componentize into:

- `RequirementList`
- `RequirementDetail`
- `TraceLinkPanel`
- `ImpactAnalysisPanel`
- `ReqIFImportReviewPanel`

### Graph Explorer

Current behavior:

- raw graph exploration and filtering.

Gaps:

- no strong overlays for ontology, lineage, quality, or product domains,
- still too generic for industrial workflows.

Componentize into:

- `GraphCanvas`
- `GraphFilters`
- `GraphLegend`
- `GraphOverlayPanel`
- `GraphNeighborhoodPanel`

### Import Pipeline

Current behavior:

- file ingestion,
- preview,
- normalization,
- bridge suggestion.

Gaps:

- import, normalization, semantic mapping, and publish are still too coupled,
- insufficient separation between source parsing and canonicalization.

Componentize into:

- `ImportSourceSelector`
- `ImportPreviewPanel`
- `NormalizationStagePanel`
- `BridgeSuggestionPanel`
- `PublishStagePanel`

## Backend Service Breakdown

### `backend/routes`

Current role:

- HTTP entry points for ontology, registry, OSLC, SysML v2, 3DXML, and admin flows.

Gap:

- routes are still grouped by technical area more than by product layer.

Recommended future route split:

- `governance_routes.py`
- `ontology_routes.py`
- `traceability_routes.py`
- `quality_routes.py`
- `graph_routes.py`
- `rag_routes.py`
- `sync_routes.py`

### `backend/Services`

Current role:

- business logic, import parsing, ontology reasoning, graph views, workflow handling.

Key gaps:

- ontology and governance logic are not fully separated,
- traceability logic is spread across import, semantic workflow, and graph services,
- quality is mostly utility-oriented rather than a dedicated product service,
- GraphRAG context assembly is distributed across multiple services.

Recommended service groups:

- `governance`
  - registry, ownership, glossary, lifecycle, domains, products
- `ontology`
  - ontology projection, mapping, reasoning, SWRL, SKOS
- `traceability`
  - requirements, bridges, impact, evidence
- `quality`
  - checks, tests, profiling, incidents
- `graph`
  - visualization, traversal, overlays
- `rag`
  - context bundles, retrieval prep, memory, citations
- `sync`
  - source-to-canonical synchronization, drift detection, publish

## What To Keep Stable

The following should remain stable while refactoring:

- existing routes and UI entry points,
- import file support,
- ontology export and preview paths,
- ReqIF ingestion support,
- graph traversal and search endpoints,
- current ontology registry persistence.

## What To Split First

1. Split `OntologyMapper.js` into smaller ontology components.
2. Split `MetadataRegistryPage.js` into registry summary, lifecycle, ownership, and sync panels.
3. Split `DataImportPipeline.js` into import, normalization, bridge, and publish subcomponents.
4. Introduce a real canonical metadata model in backend services.
5. Separate traceability and quality into dedicated services and UI surfaces.

## Recommended File/Folder Direction

### Frontend

- `frontend/src/pages`
  - route shells only
- `frontend/src/Components/ontology`
  - ontology browser and bridge workbench
- `frontend/src/Components/registry`
  - metadata registry components
- `frontend/src/Components/traceability`
  - requirements and trace links
- `frontend/src/Components/quality`
  - quality and incidents
- `frontend/src/services`
  - domain API clients
- `frontend/src/contexts`
  - shared state by capability

### Backend

- `backend/routes`
  - route handlers only
- `backend/Services/governance`
  - registry and governance logic
- `backend/Services/ontology`
  - ontology logic
- `backend/Services/traceability`
  - trace and impact logic
- `backend/Services/quality`
  - quality logic
- `backend/Services/graph`
  - graph view logic
- `backend/Services/rag`
  - retrieval and agent context
- `backend/Services/sync`
  - canonicalization and sync

## Success Criteria

The refactor is on track when:

- metadata registry, ontology junction, requirements, graph, and quality each own a clear responsibility,
- no single page owns too many unrelated workflows,
- backend services map cleanly to product layers,
- and the platform can grow without adding more coupling.


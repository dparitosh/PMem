# OSLC Gap Audit

Date: 2026-06-27

## Scope

This audit compares the current `D:\Depo_Onto_Engine` application against the older DEPO_RR OSLC capability set and identifies what is still pending for standards-based interoperability.

## Executive Summary

The current application is strong in:
- Neo4j-backed graph APIs
- ontology upload, taxonomy, reasoning, and merge workflows
- Semantic Bridge and workflow artifacts
- Owlready2 / RDFLib / SHACL processing

The current application is weak or incomplete in:
- OSLC service provider exposure
- OSLC Query 3.0 support
- TRS 3.0 change tracking
- OSLC resource shape exposure
- external OSLC client interoperability

This means the app is suitable as an internal semantic graph platform, but not yet a complete OSLC-compliant integration surface.

## Current Repo Findings

### Present in current repo

1. General FastAPI API surface in [backend/main.py](D:/Depo_Onto_Engine/backend/main.py)
   - graph view
   - ontology
   - taxonomy
   - reasoning
   - import
   - workflows
   - chat
   - recommendations

2. Ontology router in [backend/routes/ontology_routes.py](D:/Depo_Onto_Engine/backend/routes/ontology_routes.py)
   - generic data dictionary
   - generic mappings
   - AP239/AP242 handlers
   - live Neo4j-driven schema and mapping views

3. OSLC vocabulary emission inside [backend/Services/owl_xsd_engine.py](D:/Depo_Onto_Engine/backend/Services/owl_xsd_engine.py)
   - binds `oslc` namespace
   - emits OSLC property descriptors during XSD-to-OWL generation

### Not present as active runtime capability

1. No `/oslc/*` endpoint family in current FastAPI app.
2. No active Service Provider Catalog or Service Provider documents.
3. No active OSLC Query 3.0 endpoint with:
   - `oslc.where`
   - `oslc.select`
   - `oslc.orderBy`
   - `oslc.searchTerms`
   - OSLC paging
4. No active TRS 3.0 endpoint set:
   - tracked resource set
   - base
   - changelog
   - change events
5. No resource shape publication endpoint for clients.
6. No event publication from import, merge, semantic bridge, or admin mutations into a TRS change log.
7. No clear OSLC client integration contract for Teamcenter / ALM / MBSE tools.

## Older DEPO_RR capability identified

### 1. TRS 3.0 service

Old source:
- `D:\Download\DEPO_RR\requirements\src\services\oslc_service.py`

What it provided:
- tracked resource set descriptor
- base and changelog resources
- change event publishing
- optional Neo4j persistence for change history
- configuration guardrails for `OSLC_ENABLED` and `OSLC_BASE_URL`

Status in current repo:
- missing

### 2. OSLC Query 3.0 parser/service

Old source:
- `D:\Download\DEPO_RR\requirements\src\services\oslc_query_service.py`

What it provided:
- parse `oslc.where`
- parse `oslc.select`
- parse `oslc.orderBy`
- parse `oslc.searchTerms`
- parse paging parameters
- translate query intent toward Neo4j-backed execution

Status in current repo:
- missing

## Pending OSLC backlog

### Priority 1: Read-only OSLC interoperability

Implement a minimal read-only OSLC surface:
- `/oslc/catalog`
- `/oslc/providers/{provider_id}`
- `/oslc/query/{resource_type}`
- `/oslc/shapes/{shape_id}`

Purpose:
- allow external clients to discover DEPO resources
- allow standards-based query over graph-backed semantic resources

### Priority 2: OSLC Query 3.0 over existing graph APIs

Create a dedicated service that maps OSLC parameters to safe Neo4j-backed filtering:
- `oslc.where`
- `oslc.select`
- `oslc.orderBy`
- `oslc.searchTerms`
- page size / page number

Best integration point:
- build on current generic ontology and graph query services rather than duplicating traversal logic

### Priority 3: TRS 3.0 change feed

Add change publication for:
- ontology upload
- ontology merge
- semantic bridge approvals / mappings
- import commit
- admin destructive operations

Best integration point:
- emit events from current mutation surfaces in:
  - [backend/Services/unified_import_router.py](D:/Depo_Onto_Engine/backend/Services/unified_import_router.py)
  - [backend/Services/semantic_workflow_service.py](D:/Depo_Onto_Engine/backend/Services/semantic_workflow_service.py)
  - [backend/routes/admin_routes.py](D:/Depo_Onto_Engine/backend/routes/admin_routes.py)

### Priority 4: Resource shapes from ontology / SHACL

Map current ontology + SHACL assets into OSLC-facing resource shape documents.

Best integration point:
- reuse current SHACL and ontology services instead of inventing a separate schema model

## Recommended target architecture

### Backend modules to add

Suggested files:
- `backend/routes/oslc_routes.py`
- `backend/Services/oslc_service.py`
- `backend/Services/oslc_query_service.py`
- `backend/Services/oslc_trs_service.py`
- `backend/Services/oslc_shape_service.py`

### Data sources to reuse

Reuse existing sources:
- Neo4j graph data
- ontology registry metadata
- workflow artifacts
- Owlready2 / RDFLib exports
- SHACL validation metadata

### Config to add

Suggested environment variables:
- `OSLC_ENABLED=false`
- `OSLC_BASE_URL=`
- `OSLC_PROVIDER_ID=depo`
- `OSLC_PROVIDER_TITLE=DEPO Semantic Platform`
- `OSLC_TRS_ENABLED=true`
- `OSLC_MAX_PAGE_SIZE=200`

## Package assessment

No major new package family is required.

Existing stack is sufficient:
- `fastapi`
- `rdflib`
- `neo4j`
- `requests`
- current ontology / SHACL stack

Optional only:
- none required for the first OSLC recovery phase

## Current implementation status

A first recovery slice is now implemented in the current repo:
- read-only `/oslc/catalog`
- read-only `/oslc/providers/{provider_id}`
- read-only `/oslc/shapes`
- read-only `/oslc/shapes/resources`
- ontology-aware `/oslc/shapes/{ontology_id}` using Owlready2 semantics with taxonomy fallback and SHACL file detection
- read-only `/oslc/query/{resource_type}`
- read-only `/oslc/resources/{element_id}`
- read-only `/oslc/dictionaries/{prefix}` backed directly by the official Neo4j driver
- read-only `/oslc/taxonomies`
- read-only `/oslc/taxonomies/{ontology_id}` reusing the Owlready2-first taxonomy service
- minimal `/oslc/trs`
- minimal `/oslc/trs/base`
- minimal `/oslc/trs/changelog`
- best-effort TRS event publication from import commit, ontology merge, semantic bridge link, and admin destructive operations

Smoke-validated in-process on 2026-06-27:
- `/oslc/catalog`
- `/oslc/providers/depo`
- `/oslc/shapes`
- `/oslc/shapes/resources`
- `/oslc/shapes/{ontology_id}`
- `/oslc/query/resources?oslc.searchTerms=REQ&pageSize=3`
- `/oslc/dictionaries/plmxml`
- `/oslc/taxonomies`
- `/oslc/taxonomies/{ontology_id}`
- `/oslc/trs`, `/oslc/trs/base`, `/oslc/trs/changelog`

This is intentionally a minimal interoperability surface. It does not yet provide full TRS 3.0 persistence semantics, OSLC resource shapes from SHACL, or a full OSLC Query 3.0 expression engine.

## Release impact

### If customer only needs DEPO UI and internal APIs
Current OSLC gap is acceptable as a known limitation.

### If customer needs standards-based interoperability
Current OSLC gap is release-relevant and should be called out explicitly.

## Implementation order

1. Add read-only OSLC discovery and query endpoints.
2. Reuse existing graph/ontology services for response data.
3. Add TRS event publication to mutation workflows.
4. Add resource shape exposure from ontology/SHACL assets.
5. Add external integration notes and test fixtures.

## Conclusion

Pending OSLC work is significant but well-bounded.

The app does not need a new stack. It needs a focused interoperability layer built on top of the current graph, ontology, and workflow services.

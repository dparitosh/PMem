# OSLC Release Audit And Teamcenter Linked Data Registration

Date: 2026-07-14

## Executive Summary

DEPO now exposes an OSLC-aligned, read-only interoperability layer for external engineering tools. It is suitable for discovery, query, taxonomy, data dictionary, resource shape, export-link discovery, and lightweight TRS change tracking.

This is not a full OSLC certification claim. The current implementation is an OSLC service-provider facade over the existing Neo4j, Owlready2, RDFLib, SHACL, ontology registry, and workflow artifact services.

## Implemented Service Provider Capabilities

Backend modules:

- `backend/routes/oslc_routes.py`
- `backend/Services/oslc_service.py`
- `backend/Services/oslc_query_service.py`
- `backend/Services/oslc_trs_service.py`

Runtime endpoints:

- `GET /oslc/catalog`
- `GET /oslc/providers/{provider_id}`
- `GET /oslc/shapes`
- `GET /oslc/shapes/resources`
- `GET /oslc/shapes/architecture-resources`
- `GET /oslc/shapes/requirements`
- `GET /oslc/shapes/requirement-collections`
- `GET /oslc/shapes/{ontology_id}`
- `GET /oslc/query/{resource_type}`
- `GET /oslc/resources/{element_id}`
- `GET /oslc/dictionaries/{prefix}`
- `GET /oslc/taxonomies`
- `GET /oslc/taxonomies/{ontology_id}`
- `GET /oslc/trs`
- `GET /oslc/trs/base`
- `GET /oslc/trs/changelog`

The service provider document advertises:

- query capability for graph-backed resources
- resource shape links
- ontology dictionary resources
- taxonomy resources
- OSLC-facing export links for ontology artifacts where available

## AP242, OSLC AM, And OSLC RM Domain Scope

The provider now advertises three explicit domain scopes:

- `ap242`: AP242-aligned product and manufacturing information, including product structure, PMI, requirements traceability, process, and manufacturing context where available in the loaded ontology/graph.
- `oslc_am`: OSLC Architecture Management, used by engineering and MBSE tools for architecture/model elements and traceability discovery.
- `oslc_rm`: OSLC Requirements Management, used for requirements, requirement collections, and their links to architecture and product resources.

In OSLC terminology, `AM` means Architecture Management. Additive Manufacturing content can still be represented through AP242/manufacturing ontology terms, but it is not the meaning of the OSLC `am` namespace.

The TRS descriptor also advertises these domains so Teamcenter Linked Data Service Framework can classify AP242, AM, and RM resources rather than treating the feed as an untyped generic graph.

## Teamcenter Linked Data Service Framework Registration

Register DEPO as an external OSLC service provider using the Service Provider Catalog URL:

```text
http://<depo-host>:8000/oslc/catalog
```

For the current default local provider:

```text
http://<depo-host>:8000/oslc/providers/depo
```

Required environment settings before customer registration:

```env
OSLC_ENABLED=true
OSLC_TRS_ENABLED=true
OSLC_TRS_STORE=postgres
OSLC_BASE_URL=http://<depo-host>:8000
OSLC_PROVIDER_ID=depo
OSLC_PROVIDER_TITLE=DEPO Semantic Platform
OSLC_MAX_PAGE_SIZE=200
ALLOWED_ORIGINS=http://<teamcenter-awc-host>,http://<depo-ui-host>:3000
```

Use an externally reachable host/IP in `OSLC_BASE_URL`. Do not leave it as `localhost` when Teamcenter or Active Workspace runs on another machine.

## Teamcenter Integration Contract

Teamcenter or Active Workspace can use DEPO in two ways:

1. OSLC / linked-data discovery:
   - discover provider through `/oslc/catalog`
   - inspect provider through `/oslc/providers/depo`
   - inspect shapes through `/oslc/shapes`
   - query resources through `/oslc/query/resources`
   - query architecture resources through `/oslc/query/architecture-resources`
   - query requirements through `/oslc/query/requirements`
   - query requirement collections through `/oslc/query/requirement-collections`
   - retrieve a resource through `/oslc/resources/{element_id}`

2. Application APIs for AI workflows:
   - use `/recommendations/change-impact` for deterministic impact analysis
   - use `/chat/jobs` plus `GET /chat/jobs/{job_id}` for long-running GraphRAG or Ollama-backed answers
   - use `/chat` only for short synchronous assistant calls

## Example OSLC Query Calls

Search resources:

```http
GET /oslc/query/resources?oslc.searchTerms=REQ&oslc.pageSize=20
```

Query OSLC RM requirements and OSLC AM architecture resources:

```http
GET /oslc/query/requirements?oslc.searchTerms="REQ","pump"&oslc.pageSize=20
GET /oslc/query/architecture-resources?oslc.where=element_type="Interface"&oslc.pageSize=20
```

Filter resources:

```http
GET /oslc/query/resources?oslc.where=ontology_prefix="plmxml"&oslc.pageSize=50
```

Select fields:

```http
GET /oslc/query/resources?oslc.select=name,label,ontology_prefix,element_type
```

Read dictionary:

```http
GET /oslc/dictionaries/plmxml
```

Read taxonomy:

```http
GET /oslc/taxonomies/{ontology_id}
```

## 2026-07-14 Hardening Closure

The OSLC defects found in the query, shape, linking, and TRS paths were grouped and addressed as follows:

- **Query contract:** `oslc.where` is now quote-aware, rejects unsupported `or` expressions cleanly, compares numeric values numerically, and applies correct negative `rdf:type` semantics. `oslc.searchTerms` accepts comma-separated quoted terms, matches one or more terms, emits an `oslc:score`, and orders matches by descending score. Resource types are validated, structural fields remain present under `oslc.select`, type ordering is deterministic, and resource identifiers are URL-encoded.
- **Configuration and shapes:** an invalid `OSLC_MAX_PAGE_SIZE` value falls back safely. Fallback shape generation scans the complete eligible graph rather than a 250-node sample, and SHACL discovery no longer searches the process working directory when no ontology source is configured.
- **TRS integrity:** state writes are atomic, publication is protected by both thread and cross-process locks, and corrupt or counter-inconsistent state fails closed instead of being silently reset. Base membership is rebuilt from the current graph and ontology registry, retained-event gaps are exposed as requiring a rebase, and stored resource references are normalized to stable OSLC paths.
- **Linking instances:** ontology merge, Semantic Bridge instance-link, import completion, and administrative schema-change publishers now emit resolvable OSLC resource URIs. Previously stored absolute URIs are rendered through the configured current base URL when read.
- **Regression coverage:** focused contract tests now exercise parser edge cases, search scoring, filters, projection, URI encoding, configuration fallback, complete shape discovery, atomic TRS publication, corruption handling, retention gaps, host migration, and graph-backed Base membership.
- **AM/RM domain profiles:** separate AM architecture, RM requirement, and RM requirement-collection query capabilities and shapes are published. Domain resources carry their OSLC vocabulary RDF type, instance-shape and service-provider links; outgoing graph relations identify linked target domain types for AM-to-RM and RM-to-AM traceability.

## Current Compliance Status

Implemented:

- Service Provider Catalog
- Service Provider document
- conservative OSLC query subset
- resource shape publication
- ontology-aware shapes from Owlready2/taxonomy/SHACL context
- resource lookup by Neo4j element ID
- dictionaries and taxonomies as linked-data-facing resources
- TRS descriptor, base, and changelog
- TRS event publication from import commit, ontology merge, Semantic Bridge link, and administrative schema-change operations
- AP242, OSLC AM, and OSLC RM domain metadata in the Service Provider and TRS descriptor
- separate read/query profiles and shapes for AM resources, RM Requirements, and RM RequirementCollections
- inferred AM/RM RDF typing and cross-domain traceability target typing for existing graph instances

Partial:

- OSLC Query 3.0 supports a conservative subset only: simple `and` filters, select, orderBy, searchTerms, and paging.
- TRS events use the PostgreSQL control plane by default with advisory locking,
  preserving one ordered change log across service instances. Explicit
  `OSLC_TRS_STORE=file` is retained only for isolated local development/tests.
- Shapes are JSON OSLC-style payloads, not complete RDF content-negotiated shape documents.
- AM and RM are read/query discovery profiles over the existing graph; they do not yet implement every mandatory operation and representation required for a conforming full-domain server.

Not yet implemented:

- delegated creation and selection dialogs
- creation factories
- update/write OSLC resources
- ETag and conditional update semantics for OSLC resources
- OAuth/consumer-key profile for OSLC clients
- full RDF/XML/Turtle/JSON-LD content negotiation for every OSLC endpoint
- full OSLC certification coverage

## Release Recommendation

For customer release, describe the capability as:

```text
DEPO provides an OSLC-aligned read-only service provider for linked-data discovery, query, resource shapes, taxonomies, dictionaries, ontology export discovery, and TRS-style change visibility.
```

Do not describe it as:

```text
Fully OSLC certified.
```

## Validation Performed

In-process smoke validation on 2026-07-04 returned HTTP 200 for:

- `/oslc/catalog`
- `/oslc/providers/depo`
- `/oslc/shapes`
- `/oslc/trs`
- `/api/v1/ontology/registered`

Related focused tests passed:

- `backend/tests/test_oslc_services.py`
- `backend/tests/test_semantic_workflow_service.py`
- `backend/tests/test_ontology_runtime_regressions.py`
- `backend/tests/test_owl_shacl_smoke.py`

The 2026-07-14 hardening validation also covered the import, ontology upload, graph view, and GraphRAG fallback regression suites.

## Remaining Hardening

Recommended next hardening before claiming deeper OSLC coverage:

1. Add RDF content negotiation for catalog, provider, shapes, and resources.
2. Add Teamcenter LDS registration screenshots or customer-specific setup notes.
3. Add an automated OSLC smoke script that checks catalog, provider, shapes, query, resource lookup, and TRS against the deployed host URL.
4. Add auth guidance for reverse proxy, API gateway, or Teamcenter trusted network deployment.
5. Add multi-process stress and failure-injection testing for the file-backed TRS store, or replace it with shared durable storage for horizontally scaled deployments.

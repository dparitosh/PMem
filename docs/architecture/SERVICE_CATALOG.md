# Service and API catalog

Deployment inventory: [services.json](../../infra/deployment/services.json).
Each HTTP service exposes `/openapi.json`, `/docs`, `/healthz`, `/readyz`, and
`/odata/$metadata`. OpenAPI is the authoritative operation-level contract;
OData advertises capabilities, not a complete OData entity implementation.

| Service | Port | Python package | API families | Responsibility |
|---|---|---|---|---|
| Schema sets | 8010 | backend.qif | /api/v1/qif | Multi-file engineering schema processing; QIF compatibility namespace |
| Ontology | 8011 | backend.ontology_service | /api/v1/ontologies, /api/v1/modeling, /api/v1/metadata-registry, /api/v1/admin | Semantic artifacts, review lifecycle, modeling and registry |
| Agentic | 8012 | backend.agentic_service | /api/v1/agents, /api/v1/tools, /api/v1/workflows, /api/v1/chat | Tools, orchestration and graph evidence retrieval |
| Graph | 8013 | backend.graph_service | /api/v1/graph, /api/v1/graphql, /api/v1/sparql | Graph publication and query surfaces |
| Ingestion | 8014 | backend.ingestion_service | /api/v1/ingestion, /api/v1/import, /api/v1/source-profiles, /api/v1/schema-conversions | Source capture, parsing and profile normalization |
| OSLC | 8015 | backend.oslc_service | /api/v1/oslc | Engineering resource interfaces and remote providers |
| Catalog | 8016 | backend.data_catalog_service | /api/v1/catalog | Product discovery and artifact retention |
| Data products | 8017 | backend.data_product_service | /api/v1/data-products | Product manifests, packaging and catalog outbox |
| CEIM | 8018 | backend.ceim_service | /api/v1/ceim | Canonical mapping, validation and approved publication requests |
| Data pipeline | 8019 | backend.data_pipeline_service | /api/v1/pipeline | Job definitions, runs, quality evidence and event reconciliation |

The outbox worker is `backend.data_product_service.worker`; it has no HTTP port.
The React/Vite frontend is in `frontend`, with service routing in
`frontend/src/config.js`. It normally listens on 3000 during development.

## Compatibility ownership

The `/api/v1/ontology` namespace is split during migration: upload, registered
artifacts, taxonomy, reasoning, inference preview and export belong to ingestion;
semantic rules, mappings and domain workbench operations belong to ontology.
Do not route this whole namespace to one service. `backend/main.py` remains a
legacy compatibility host and is not part of the production service manifest.

## Catalogs and truth sources

- Deployment addresses/modules: `infra/deployment/services.json`.
- Callable agent tools: `backend/agentic_service/catalog.json` (a selected tool
  allowlist, not an inventory of every API).
- Full API contract: each service's generated OpenAPI.
- Operational data products: PostgreSQL catalog records.
- Pending acceptance and limitations: `docs/ACCELERATED_DELIVERY_TRACKER.md`.

These describe implemented boundaries, not production certification. Entra
service identity, publication integration and full acceptance remain subject to
the delivery tracker.

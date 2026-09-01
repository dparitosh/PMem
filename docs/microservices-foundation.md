# DEPO Microservices Foundation

This branch introduces independent service entry points without interrupting
the current UI or its existing backend API:

- `backend.ontology_service.app` (port `8011`) owns ontology artifacts and
  exposes Semantica capability status.
- `backend.qif.app` (port `8010`) owns QIF XSD workflow state and communicates
  through a publishing port.
- `backend.graph_service.app` (port `8013`) owns direct Neo4j connectivity.
- `backend.platform` provides the shared FastAPI lifecycle, CORS, and request
  correlation policy used by each service.

The design intentionally does not use Redis or Celery. QIF continues using its
bounded in-process worker while it owns a task; a deployment can later replace
that executor without changing the HTTP contracts.

## Publishing migration

QIF publication has no legacy fallback. It uses the OpenAPI ontology and graph
services, and ontology generation uses Semantica as a required dependency.
The graph service accepts a Turtle artifact through
`POST /api/v1/graph/ontologies/publish`. It upserts RDF resources and promotes
`rdfs:subClassOf`, `rdfs:domain`, and `rdfs:range` to explicit graph edges for
hierarchical exploration. It never falls back silently to legacy code.

## Semantica adoption

The ontology service exposes `GET /api/v1/ontologies/capabilities`. It reports
whether the optional `semantica` package is installed and reserves its lifecycle,
KG-to-ontology, OWL/RDF, SHACL, namespace, and evaluation responsibilities at
one boundary. The deterministic QIF XSD-to-OWL generator remains available so
QIF ingestion is not blocked by an LLM runtime.

## Retirement order

1. Start the three services and verify their `/docs` and `/health` endpoints.
2. Run a QIF workflow with `QIF_PUBLISH_MODE=services`; validate registered
   artifacts and the forthcoming graph write contract.
3. Move the main application's ontology/graph routes behind these contracts.
4. Only then delete `backend/Services/ontology_upload_manager.py` and the
   legacy graph adapter. This avoids orphaning existing ontology records.

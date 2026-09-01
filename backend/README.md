# DEPO Backend API

FastAPI backend for the DEPO application.

## What This Service Owns

- graph APIs
- ontology registry and browsing APIs
- semantic workflows
- import workflows
- admin and cleanup APIs
- chat / GraphRAG APIs
- recommendations APIs
- document upload APIs

## Primary Entry Point

- [backend/main.py](D:/Depo_Onto_Engine/backend/main.py)

## Start The Backend

From repository root:

```bat
.\start_backend.bat
```

Or directly:

```bat
cd D:\Depo_Onto_Engine
backend\.dt_venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Key URLs

- Health: `http://localhost:8000/health`
- Neo4j health: `http://localhost:8000/health/neo4j`
- Swagger: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Independent semantic services

The backend can also run as four HTTP services without Redis or Celery:

```powershell
$env:NEO4J_PASS = "<your Neo4j password>"
docker compose -f compose.services.yml up --build
```

| Service | Port | Responsibility |
| --- | ---: | --- |
| Ontology | 8011 | Semantica generation, SHACL validation, ontology catalog and alignment records |
| Graph | 8013 | Governed Neo4j ontology publication |
| Ingestion | 8014 | Source-profile normalization and explicit semantic workflow orchestration |
| OSLC | 8015 | OSLC provider, shapes, TRS, domain discovery and remote OSLC client |

Use `POST /api/v1/source-profiles/{profile_id}/workflow` on the ingestion
service to run `normalize → generate/validate → publish`. Set `publish=true`
only when the generated ontology is approved for Neo4j publication.

The ontology service also exposes Semantica quality and evolution APIs:
`POST /ontologies/quality-gate`, `POST /ontologies/versions`,
`POST /ontologies/versions/compare`, `POST /ontologies/analytics`, and
`GET /ontologies/mcp`. The MCP endpoint returns a stdio launch contract; do
not expose an unauthenticated MCP process over HTTP.

## Important Runtime Dependencies

- Neo4j must be reachable with correct credentials
- graph and ontology features depend on Neo4j health
- chat and document ingestion depend on the configured LLM / embedding stack

## Current Document Upload Status

Document endpoints are mounted under `/api/v1/documents/*`.

They now degrade honestly when the processor or embedding runtime is unavailable. That means:
- backend startup should not fail because of document pipeline imports
- health will report degraded when the embedding backend is unavailable
- upload endpoints will return a clear error instead of failing unpredictably

## Recommended Customer Validation

- `GET /health`
- `GET /health/neo4j`
- `GET /docs`
- `GET /api/v1/ontology/registered`
- `GET /chat/health`
- `GET /api/v1/documents/health`

## Optional Agent Memory

Graph-native chat and Semantic Bridge memory can be enabled with
`AGENT_MEMORY_ENABLED=true`. See
[docs/AGENT_MEMORY_AUGMENTATION.md](D:/Depo_Onto_Engine/docs/AGENT_MEMORY_AUGMENTATION.md).

Useful checks:

- `GET /api/v1/agent-memory/status`
- `GET /api/v1/agent-memory/sessions/{session_id}/context`

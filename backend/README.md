# DEPO Backend API

FastAPI backend for the DEPO application.

## Runtime architecture

The target architecture is independently deployable, OpenAPI-first semantic
services plus the agentic control plane. `backend/main.py` is retained
only as a compatibility host while the SPA is migrated; it is not the target
for new backend features. See `backend/legacy/README.md` for the safe removal
process.

## Start The Backend

For the supported service deployment, use the manifest-driven Windows launcher
from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\start-depo-services.ps1
```

For compatibility-host debugging only, start the legacy host directly:

```bat
rem From the repository root, with backend environment variables already injected:
backend\.dt_venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Key URLs

These URLs apply only to the compatibility host above. Supported services use
the `/healthz` and `/readyz` endpoints on the ports in the service inventory.

- Health: `http://localhost:8000/health`
- Neo4j health: `http://localhost:8000/health/neo4j`
- Swagger: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Independent semantic services

The target deployment runs as ten independently deployable HTTP services plus
one durable outbox worker, without Redis, Celery, or Docker:

```powershell
$env:NEO4J_PASS = "<your Neo4j password>"
# Configure PostgreSQL once (no Docker runtime):
$env:DEPO_DATABASE_URL = "postgresql://<user>:<password>@<host>:<port>/<database>"
python -m uvicorn backend.data_catalog_service.app:app --host 127.0.0.1 --port 8016
```

| Service | Port | Responsibility |
| --- | ---: | --- |
| Ontology | 8011 | Semantica generation, SHACL validation, ontology catalog and alignment records |
| Graph | 8013 | Governed Neo4j ontology publication |
| Ingestion | 8014 | Source-profile normalization and explicit semantic workflow orchestration |
| OSLC | 8015 | OSLC provider, shapes, TRS, domain discovery and remote OSLC client |
| Agentic control plane | 8012 | Manifest-driven agents, tools, workflows and MCP contracts |
| Engineering schema sets | 8010 | QIF and multi-schema-set validation and workflow boundary |
| Data Catalog | 8016 | Governed product discovery, registration and artifact retention |
| Data Products | 8017 | Immutable product packages, manifests and catalog outbox reconciliation |
| CEIM | 8018 | Canonical mapping, validation, provenance and approved publication requests |
| Data Pipeline | 8019 | Versioned Spark jobs, immutable partitions, telemetry and replay |

## Dependencies

`requirements.txt` is the single lean runtime manifest used for local
development and direct process-managed deployments. It contains only API, RDF/Semantica, Neo4j,
XML, HTTP, and pure-Python XLSX support. Optional chat, OCR, document, and
notebook integrations are not part of the supported service runtime.

For local development and testing, install `backend/requirements-dev.txt` from the
repository root; it includes the runtime requirements and pytest dependencies.

Use `POST /api/v1/source-profiles/{profile_id}/workflow` on the ingestion
service to run `normalize → generate/validate → publish`. Set `publish=true`
only when the generated ontology is approved for Neo4j publication.

Set `SEMANTIC_GRAPH_PROVIDER=neo4j` (default), `rapidminer`, or `oracle` to
make the selected graph-store profile explicit. The current tabular writer
executes Cypher against Neo4j; RapidMiner and Oracle profiles validate and
retain their connection configuration until their provider-specific canonical
graph adapters are configured.

The OSLC service can pull a configured remote query into an immutable staged
snapshot with `POST /api/v1/oslc/remote/sync/{resource_type}`. A staged
snapshot is not published automatically: map it through a source profile and
approve the normal ingestion quality/policy gates first.

The ontology service also exposes Semantica quality and evolution APIs:
`POST /ontologies/quality-gate`, `POST /ontologies/versions`,
`POST /ontologies/versions/compare`, `POST /ontologies/analytics`, and
`GET /ontologies/mcp`. The MCP endpoint returns a stdio launch contract; do
not expose an unauthenticated MCP process over HTTP.

## Production dependencies

- Neo4j must be reachable with correct credentials
- graph publication and live graph exploration depend on Neo4j health
- chat and document ingestion depend on the configured LLM / embedding stack

## Current Document Upload Status

Document endpoints are mounted under `/api/v1/documents/*`.

They now degrade honestly when the processor or embedding runtime is unavailable. That means:
- backend startup should not fail because of document pipeline imports
- health will report degraded when the embedding backend is unavailable
- upload endpoints will return a clear error instead of failing unpredictably

## Service validation

- `GET /healthz` and `GET /readyz` on every standalone service
- `GET /openapi.json` and `GET /odata/$metadata` on every standalone service
- service-specific health and dependency endpoints before enabling publication
- APIM import and policy scripts in `infra/azure-apim`

## Optional Agent Memory

Graph-native chat and Semantic Bridge memory can be enabled with
`AGENT_MEMORY_ENABLED=true`. See `docs/AGENT_MEMORY_AUGMENTATION.md`.

Useful checks:

- `GET /api/v1/agent-memory/status`
- `GET /api/v1/agent-memory/sessions/{session_id}/context`

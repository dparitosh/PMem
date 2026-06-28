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

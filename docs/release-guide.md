# DEPO Customer Release Guide

Date: 2026-06-25

## 1. Deliverables

### A. Main DEPO application

Purpose:
- Digital thread exploration
- Ontology upload and browsing
- Semantic Bridge workflows
- Graph explorer
- Recommendations, reports, chat, and import workflows

Main runtime pieces:
- Frontend: React app on port `3000`
- Backend: FastAPI app on port `8000`
- Neo4j: customer-managed graph database

### B. Standalone ontology agentic service

Location:
- `standalone/ontology_agentic_service/`

Purpose:
- ontology review
- ontology export
- semantic workflow orchestration
- DEPO backend API orchestration for ontology-centric automations

Default runtime:
- FastAPI app on port `8012`

## 2. Release Readiness Summary

### Main application

Ready to release with the following notes:
- core graph, ontology, semantic bridge, import, and chat surfaces are present
- startup scripts exist and support LAN / IP-based usage
- backend OpenAPI docs are available at `/docs` when backend is running

Residual caution:
- document upload depends on embedder runtime availability in the target environment
- graph-heavy workflows remain dependent on Neo4j health and correct environment configuration

### Standalone ontology agentic service

Ready to release as a separate companion service.

Best positioning:
- automation-facing ontology microservice
- not a replacement for the main DEPO UI

## 3. Customer Startup Instructions

### Main app startup

From repository root:

```bat
cd D:\Depo_Onto_Engine
.\start_backend.bat
.\start_frontend.bat
```

Notes:
- Use `start_backend.bat` and `start_frontend.bat` directly. There is no combined root `start.bat`.
- `start_backend.bat` binds the API to `0.0.0.0` by default and prints the LAN-facing `/docs` and `/openapi.json` URLs.
- `start_frontend.bat` injects `REACT_APP_BACKEND_URL` for the current run, which is the safest path for VM or LAN-based testing.

Useful URLs:
- Frontend UI: `http://<host>:3000`
- Backend docs: `http://<host>:8000/docs`
- Backend OpenAPI JSON: `http://<host>:8000/openapi.json`

### Standalone service startup

```bat
cd D:\Depo_Onto_Engine\standalone\ontology_agentic_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python start_service.py
```

Useful URLs:
- Standalone docs: `http://<host>:8012/docs`
- Standalone OpenAPI JSON: `http://<host>:8012/openapi.json`

## 4. Required Environment Configuration

### Main app

Backend requires:
- Neo4j URI
- Neo4j username
- Neo4j password
- Neo4j database name
- LLM / embedding configuration if chat and document ingestion are required
- `ALLOWED_ORIGINS` must include the actual frontend URL used by the customer, for example `http://<vm-ip>:3000`

Frontend requires:
- backend base URL when accessed by LAN IP / VM IP / DNS
- `REACT_APP_BACKEND_URL` should point to the backend host visible from the browser, for example `http://<vm-ip>:8000`

### Standalone service

Optional but recommended:
- `ONTOLOGY_AGENTIC_DEPO_API_BASE_URL`
- `ONTOLOGY_AGENTIC_DEPO_API_TIMEOUT_SECONDS`
- `ONTOLOGY_AGENTIC_DEPO_API_TOKEN` when applicable

## 5. Release Checklist

### Must pass before handoff
- [ ] Backend starts successfully
- [ ] Frontend starts successfully
- [ ] Neo4j health endpoint returns success
- [ ] Backend `/docs` loads
- [ ] Backend `/openapi.json` loads
- [ ] Frontend can load main pages without startup errors
- [ ] Standalone ontology service starts and `/docs` loads

### Strongly recommended before production use
- [ ] Replace any local development secrets in `backend/.env` with customer-managed secrets
- [ ] Rotate any previously committed Neo4j or API credentials
- [ ] Validate customer `.env` with real Neo4j values
- [ ] Validate CORS / LAN host settings with target hostname or IP
- [ ] Smoke test Semantic Bridge
- [ ] Smoke test graph explorer on customer data
- [ ] Smoke test chat API
- [ ] Confirm document upload only if embedder runtime is installed and reachable

## 6. Known Release Notes

### Main application
- Graph visualization depends on Neo4j connectivity and data quality.
- Document upload is now mounted in the backend and degrades honestly, but it will report unavailable if the embedding runtime is not present.

### Standalone ontology service
- Works offline for local ontology review/export.
- DEPO API orchestration features require the main backend to be reachable.

## 7. Recommended Customer Messaging

Use this wording:

- The **main DEPO application** is the primary user-facing platform.
- The **standalone ontology agentic service** is an auxiliary ontology workflow service for API-driven automation and semantic processing.
- Unstructured document processing is supported by the backend API, but operational readiness depends on the embedding runtime configured in the deployment environment.

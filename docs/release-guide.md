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
- Large XMI/import settings should be reviewed for customer data size:
  - `IMPORT_REQUEST_TIMEOUT_SECONDS=3600`
  - `NEO4J_IMPORT_QUERY_TIMEOUT=900`
  - `IMPORT_COMMIT_QUERY_TIMEOUT=900`
  - `IMPORT_WRITE_BATCH_SIZE=250`
  - `IMPORT_LINK_BATCH_SIZE=150`

Frontend requires:
- backend base URL when accessed by LAN IP / VM IP / DNS
- `REACT_APP_BACKEND_URL` should point to the backend host visible from the browser, for example `http://<vm-ip>:8000`

### Standalone service

Optional but recommended:
- `ONTOLOGY_AGENTIC_DEPO_API_BASE_URL`
- `ONTOLOGY_AGENTIC_DEPO_API_TIMEOUT_SECONDS`
- `ONTOLOGY_AGENTIC_DEPO_API_TOKEN` when applicable

### Optional SysML v2 API connector

DEPO currently supports SysML/XMI-style file ingestion through the import pipeline. SysML v2 REST readiness endpoints are available, but live repository sync/import is not part of the supported runtime surface yet.

If a customer has a SysML v2 API server, add it as an optional connector rather than replacing the XMI parser:

- `SYSML_V2_API_ENABLED=false`
- `SYSML_V2_API_BASE_URL=`
- `SYSML_V2_API_TOKEN=`
- `SYSML_V2_PROJECT_ID=`
- `SYSML_V2_BRANCH_ID=`
- `SYSML_V2_COMMIT_ID=`
- `SYSML_V2_PAGE_SIZE=500`
- `SYSML_V2_REQUEST_TIMEOUT_SECONDS=120`

See `docs/sysml-v2-api-client-audit.md` before committing to this integration in a customer scope.

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
- SysML v2 API readiness endpoints are available under `/api/v1/sysml-v2/*`; repository sync remains a planned optional connector. Current supported SysML-style ingestion remains file/import based.
- KerML has been reviewed as a SysML v2 semantic foundation, but `.kerml` parsing/import is not currently a supported runtime feature.

### Standalone ontology service
- Works offline for local ontology review/export.
- DEPO API orchestration features require the main backend to be reachable.

## 7. Recommended Customer Messaging

Use this wording:

- The **main DEPO application** is the primary user-facing platform.
- The **standalone ontology agentic service** is an auxiliary ontology workflow service for API-driven automation and semantic processing.
- Unstructured document processing is supported by the backend API, but operational readiness depends on the embedding runtime configured in the deployment environment.


## Node.js Runtime Requirement

Use Node.js 20 LTS with npm 10 for the frontend. This avoids old Node runtime failures such as `react-scripts` not being recognized and keeps the release on a stable LTS baseline.

Recommended verification:

```bat
node -v
npm -v
cd D:\Depo_Onto_Engine\frontend
npm install
npm run build
```

The frontend startup script now checks for Node.js 20 or newer before starting.

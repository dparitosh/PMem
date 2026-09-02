# DEPO Customer Release Guide

Date: 2026-06-25

## 1. Deliverables

### A. DEPO application platform

Purpose:
- Digital thread exploration
- Ontology upload and browsing
- Semantic Bridge workflows
- Graph explorer
- Recommendations, reports, chat, and import workflows

Runtime pieces:
- Frontend: React SPA
- PostgreSQL: customer-managed control-plane and durable runtime state
- Neo4j: customer-managed semantic graph database
- DEPO services: schema sets (`8010`), ontology (`8011`), agentic (`8012`),
  graph (`8013`), ingestion (`8014`), OSLC (`8015`), catalog (`8016`), and
  data products (`8017`)
- Azure API Management: the only public ingress, with TLS and Entra validation

### B. Ontology and agentic capability

Purpose:
- ontology review
- ontology export
- semantic workflow orchestration
- DEPO API orchestration for ontology-centric automations

The agentic API runs as a DEPO service on port `8012` and is not a separate
customer deployment by default.

## 2. Release Readiness Summary

### Main application

The platform is a release candidate only after the customer-specific production
preflight, API gateway registration, and target-environment smoke tests pass.

Residual caution:
- document upload depends on embedder runtime availability in the target environment
- graph-heavy workflows remain dependent on Neo4j health and correct environment configuration

The agentic capability is an automation-facing microservice, not a replacement
for the DEPO UI.

## 3. Customer Startup Instructions

### Platform startup

From repository root, after configuring the customer `.env.local`:

```powershell
cd D:\Githuv_repo\PMem
powershell -ExecutionPolicy Bypass -File .\infra\windows\test-depo-release.ps1 -Production
powershell -ExecutionPolicy Bypass -File .\infra\windows\start-depo-services.ps1 -SkipPostgres
```

Notes:
- PostgreSQL is independently managed; use `-SkipPostgres` for a customer-managed instance.
- DEPO services should bind only to a private interface. Azure API Management
  exposes approved OpenAPI/OData surfaces externally.
- Build and host the frontend with the customer API gateway URL; do not expose
  development ports directly to users.

Useful URLs:
- External UI/API URLs are the customer Azure API Management and frontend
  hostnames, not direct localhost service ports.

## 4. Required Environment Configuration

### Main app

Platform requires:
- PostgreSQL application connection URL using a least-privilege role
- Neo4j URI, username, password, and database name
- Entra authentication configuration and Azure API Management registration
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
- [ ] All eight DEPO services start successfully
- [ ] PostgreSQL `depo_schema_migrations` is current and a backup/restore has been verified
- [ ] `test-depo-release.ps1 -Production` passes
- [ ] Frontend production build and gateway-hosted UI load successfully
- [ ] Neo4j health endpoint returns success
- [ ] Backend `/docs` loads
- [ ] Backend `/openapi.json` loads
- [ ] Frontend can load main pages without startup errors
- [ ] Azure API Management validates Entra tokens and routes only approved APIs

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

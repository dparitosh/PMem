# DEPO Semantic Digital Thread

DEPO is a governed semantic integration platform for engineering data. It
connects standards, source artifacts, CEIM canonical mappings, quality rules,
data products and a Neo4j-backed knowledge graph through controlled publication.

## Supported deployment topology

The supported runtime is a React/Vite frontend, ten independently deployable
FastAPI services, one durable data-product outbox worker, PostgreSQL control
plane, artifact storage and a customer-managed graph database. The legacy
`backend/main.py` host remains only for controlled frontend migration and is
not the production deployment target.

The authoritative service inventory is
[infra/deployment/services.json](infra/deployment/services.json).

## Installation and release

Use the single maintained deployment guide:

[infra/deployment/README.md](infra/deployment/README.md)

It covers configuration generation, security profiles, service startup,
OpenAPI/OData validation, Spark opt-in, shutdown and production preflight.

## Architecture references

- [Service and API catalog](docs/architecture/SERVICE_CATALOG.md)
- [Documentation and repository map](docs/README.md)

- [Semantic Integration and Lambda Pipeline](docs/SEMANTIC_INTEGRATION_LAMBDA_PIPELINE.md)
- [Semantic Governance Contract](docs/SEMANTIC_GOVERNANCE_CONTRACT.md)
- [Delivery Tracker](docs/ACCELERATED_DELIVERY_TRACKER.md)
- [Customer Deployment Runbook](docs/DEPLOYMENT_RUNBOOK.md)

## Development notes

- Frontend: Node.js 24+ and npm 10+, run `npm ci` then `npm run build` in
  `frontend`.
- Backend: use the project Python runtime under `backend/.dt_venv`.
- No Docker, Redis or Celery runtime is required.
- Do not store customer secrets in source control. `.env.local` is gitignored.

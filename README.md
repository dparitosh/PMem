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

One installer handles backend dependencies and the frontend build:
`infra/windows/install-depo.ps1`. Run it from the project root after preparing
server and browser settings as described in the guide. `-CheckPrerequisites`
checks Python/Node/npm without installation; `-Development` includes test tools.
Python packages remain under `backend/.dt_venv`, npm packages under
`frontend/node_modules`, and the browser build under `frontend/dist`.

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
- Backend: use Python 3.11. The installer creates
  `backend/.dt_venv`; install `backend/requirements-dev.txt` for tests.
- No Docker, Redis or Celery runtime is required.
- Do not store customer secrets in source control. `.env.local` is gitignored.
- [Configuration ownership](config/README.md) explains the server, browser and
  optional Spark templates.
- [Repository maintenance](docs/REPOSITORY_MAINTENANCE.md) documents folder
  ownership, test commands, cleanup decisions and remaining release work.

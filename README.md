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

[INSTALLATION.md](INSTALLATION.md)

Run the supported one-command Windows installer after preparing PostgreSQL,
Neo4j, optional Spark, and the two `.env.local` files described in the guide:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo-windows.ps1 -EnvFile .env.local -Profile Production
```

It installs dependencies, builds the frontend, validates configuration, applies
the database schema, verifies Neo4j and optional Spark, starts all services,
and runs release preflight. Python packages remain under `backend/.dt_venv`,
npm packages under `frontend/node_modules`, and the browser build under
`frontend/dist`.

## Architecture references

- [Service and API catalog](docs/architecture/SERVICE_CATALOG.md)
- [Documentation and repository map](docs/README.md)

- [Semantic Integration and Lambda Pipeline](docs/SEMANTIC_INTEGRATION_LAMBDA_PIPELINE.md)
- [Semantic Governance Contract](docs/SEMANTIC_GOVERNANCE_CONTRACT.md)
- [Delivery Tracker](docs/ACCELERATED_DELIVERY_TRACKER.md)
- [Installation and release guide](INSTALLATION.md)

## Development notes

- Frontend: Node.js 24+ and npm 10.2+, run `npm ci` then `npm run build` in
  `frontend`.
- Backend: use Python 3.11. The installer creates
  `backend/.dt_venv`; install `backend/requirements-dev.txt` for tests.
- No Docker, Redis or Celery runtime is required.
- Do not store customer secrets in source control. `.env.local` is gitignored.
- [Configuration ownership](config/README.md) explains the server, browser and
  optional Spark templates.
- [Repository maintenance](docs/REPOSITORY_MAINTENANCE.md) documents folder
  ownership, test commands, cleanup decisions and remaining release work.

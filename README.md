# DEPO Semantic Digital Thread

DEPO is a governed semantic integration platform for engineering data. It
connects standards, source artifacts, CEIM canonical mappings, quality rules,
data products and a Neo4j-backed knowledge graph through controlled publication.

## Supported deployment topology

The supported runtime is a React/Vite frontend, ten independently deployable
FastAPI services, three durable workers (data-product outbox, data-pipeline and agentic workflow), PostgreSQL control
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
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-depo.ps1 -EnvFile .env.local -Profile Production
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
- Backend: use 64-bit CPython 3.12. The installer creates
  `backend/.dt_venv`; install `backend/requirements-dev.txt` for tests.
- No Docker, Redis or Celery runtime is required.
- Do not store customer secrets in source control. `.env.local` is gitignored.
- [Configuration ownership](config/README.md) explains the server, browser and
  optional Spark templates.
- [Repository maintenance](docs/REPOSITORY_MAINTENANCE.md) documents folder
  ownership, test commands, cleanup decisions and remaining release work.


## Current environment configuration reference

For current `.env.local` ownership, copy-and-paste update commands, central credential synchronization and Ollama REST settings, use the [environment configuration reference](deliverables/DEPO_Environment_Configuration_Reference.md#applying-environment-configuration-in-sequence). Use the selected root server file consistently; never copy its secrets into public frontend variables. The [installation guide](INSTALLATION.md) defines the complete deployment sequence.


## Imported MBSE models in Modeling

Open **Modeling → MBSE / SysML / UML**, select the retained XMI source and choose a **SysML view**. The reader uses the immutable source artifact attached to that ontology version. It preserves named diagram membership, original XMI element identities, available profile values and owned features. The canvas renders requirements, block/class definitions, use cases and available parametric elements with generated positioning; the Inspector shows retained source details. Tables/matrices expose available source records and relationships, without inventing missing vendor row/column configuration.

MagicDraw exports can reference external binary drawing streams. If those are absent, original drawing coordinates, routing and complete notation cannot be reconstructed. Views without exported members show an explicit empty-content message. This is a read-only viewer, not a complete SysML authoring tool; source files remain unchanged. The reader is bounded to 25 MB per XMI, 256 named views and 4,096 member references per view.

Select an element to ask the Companion or launch an existing read-only Graph Analyst investigation. Published graph identities are resolved against the selected ontology; unlinked XMI elements cannot masquerade as graph nodes. Original XMI IDs stay in the Inspector. The current worker/goal and scoped memory pipeline are reused; live agent planning requires an available configured LLM. No new memory store, model training or automatic approval is introduced.

This update adds a read-authorized ontology-service endpoint (`/api/v1/modeling/xmi-diagrams/{ontology_id}`) and frontend components. Deploy both and restart the ontology service using the supported lifecycle scripts before loading the new frontend. No PostgreSQL migration or graph publication is required. Existing models need a retained original XMI artifact; a TTL-only registration cannot recover missing diagram definitions.

### Engineering traceability in Inspector

Selecting an imported XMI element progressively resolves its unique published identity through `/api/v1/modeling/xmi-context/{ontology_id}?source_id=...`. Diagrams do not wait for this graph lookup. Inspector separates complete source-model relationships (paged) from the current view, and shows the first 100 recorded adjacent graph associations with an explicit truncation notice. Ambiguous or unpublished identities cannot start a scoped agent investigation.

**Engineering traceability** groups recorded web references into PLM records, CAD files, simulation datasets and other source references. Each link identifies its supporting source property or graph relationship; linked systems still enforce their own access. Ontology IRIs are not treated as engineering files. Unsafe schemes, embedded credentials and common credential-bearing query parameters are excluded. Missing associations remain explicit: the viewer does not invent CAD, PLM or simulation links, infer compatible revisions, or turn model references into approval.

Deploy `ModelTraceability.js` with the updated viewer, API client, stylesheet and ontology service. Existing Windows install/update scripts already deploy those service and frontend trees; this change needs no database migration, new credential or worker. Restart using the supported lifecycle scripts and rebuild the frontend. Malformed retained XML returns 422, missing source returns 404, unavailable source files return 409, and failed graph-context reads return 503 while the independent XMI diagram remains usable.

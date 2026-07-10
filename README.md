# DEPO Release Package

This repository contains two deliverables that can be released together to the customer:

1. **Main DEPO application**
   - React frontend in `frontend/`
   - FastAPI backend in `backend/`
   - Neo4j-backed graph, ontology, import, semantic bridge, chat, and reports workflows

2. **Standalone Ontology Agentic Service**
   - Located in `standalone/ontology_agentic_service/`
   - Separate ontology workflow microservice with its own API
   - Can orchestrate selected DEPO backend APIs without depending on the DEPO frontend

## Recommended Release Positioning

- Release the **main DEPO application** as the primary customer application.
- Release the **standalone ontology agentic service** as a companion service for ontology-centric workflows, automation, and API-driven orchestration.

## Runtime Boundary Model

The repository is intended to run as separate service boundaries, not as one monolith:

- **Frontend**: React app on port `3000`
- **Backend API**: FastAPI on port `8000`
- **Neo4j**: external graph database
- **Ollama / LLM services**: external model runtime

Use the checked-in launcher scripts to start each service with its own host/port and environment variables. That is the supported no-Docker deployment model.

For one-file deployment control, copy [`service-boundaries.env.example`](D:/Depo_Onto_Engine/service-boundaries.env.example) to `service-boundaries.env` and edit the runtime hosts, ports, and external service URIs for the target machine.

Use [`start_services.bat`](D:/Depo_Onto_Engine/start_services.bat) and [`stop_services.bat`](D:/Depo_Onto_Engine/stop_services.bat) for the normal operator workflow. Use the individual backend/frontend launchers only when debugging a single service.

## Customer-Facing Release Documents

- [Release guide](D:/Depo_Onto_Engine/docs/release-guide.md)
- [Backend semantic workflows](D:/Depo_Onto_Engine/docs/backend-semantic-workflows.md)
- [Semantic Bridge and Teamcenter notes](D:/Depo_Onto_Engine/docs/semantic-bridge-change-impact-and-teamcenter.md)
- [Standalone ontology agentic service README](D:/Depo_Onto_Engine/standalone/ontology_agentic_service/README.md)

## Quick Start

### Runtime Prerequisite

Use Node.js 20 LTS with npm 10 for the React frontend. The root `.nvmrc` / `.node-version` files and `frontend/package.json` all target Node 20. After upgrading Node.js, run `cd frontend && npm install && npm run build`.

### Main app

```bat
cd D:\Depo_Onto_Engine
.\start_services.bat
```

### Standalone ontology service

```bat
cd D:\Depo_Onto_Engine\standalone\ontology_agentic_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python start_service.py
```

## Current Release Caveat

The unstructured document pipeline is now wired into the backend API surface, but document upload remains dependent on a working embedding runtime in the customer environment.

That means:
- ontology, graph, import, semantic bridge, and API surfaces are releaseable
- document upload should be treated as environment-dependent unless the target runtime has the required LLM/embedder stack available

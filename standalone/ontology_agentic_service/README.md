# Ontology Agentic Service

Standalone modular service for ontology-focused agent workflows.

This package is intentionally isolated from the main DEPO application, but it can now orchestrate DEPO backend APIs through a thin adapter layer instead of duplicating semantic workflow logic.

It provides:

- a lightweight agent registry
- deterministic ontology workflow handlers
- prompt-spec driven agent definitions
- optional `Owlready2` / `RDFLib` based ontology inspection and export
- a DEPO API adapter for registered ontologies, workflow execution, ontology merge, and export retrieval
- a small FastAPI service for separate deployment

## Folder Layout

```text
standalone/ontology_agentic_service/
  app/
    main.py
  ontology_agentic/
    agents/
      specs/
    api_clients/
    runtime/
    tools/
    config.py
    models.py
  tests/
  requirements.txt
  start_service.py
```

## What It Does

The service exposes ontology-oriented agent workflows for:

1. ontology intake
2. ontology structure review
3. instance-to-ontology alignment planning
4. ontology export
5. orchestration of the above as a workflow
6. DEPO registered ontology discovery
7. DEPO semantic workflow execution
8. DEPO ontology merge
9. DEPO import-generated OWL export download

## What It Does Not Do

- it does not depend on the current frontend
- it does not require Neo4j locally for offline ontology review
- it does not hide missing data behind guessed outputs
- it does not require an LLM to run the default workflows

## Quick Start

```powershell
cd D:\Depo_Onto_Engine\standalone\ontology_agentic_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python start_service.py
```

The API will be available at:

- `http://localhost:8012/docs`
- `http://localhost:8012/openapi.json`

## Main Endpoints

- `GET /health`
- `GET /api/v1/agents`
- `POST /api/v1/agents/{agent_name}/run`
- `POST /api/v1/workflows/run`

## Local Workflow Example

```json
{
  "workflow_id": "ontology_review",
  "inputs": {
    "ontology_path": "D:/Download/DEPO_RR/requirements/mbse_output.owl",
    "export_formats": ["ttl", "rdfxml"]
  }
}
```

## DEPO API Workflow Examples

### 1. List registered ontologies from the current DEPO backend

```json
{
  "workflow_id": "depo_registered_ontologies",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000"
  }
}
```

### 2. Execute Semantic Bridge instance linking remotely

```json
{
  "workflow_id": "depo_semantic_workflow",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "depo_workflow_id": "instance.link",
    "payload": {
      "ontology_id": "mbseout",
      "import_artifact_manifest": {
        "task_id": "instance-import-task-id"
      },
      "apply_links": true
    }
  }
}
```

### 3. Merge two ontologies through the existing DEPO backend

```json
{
  "workflow_id": "depo_ontology_merge",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "from_ontology_id": "source_ontology",
    "to_ontology_id": "target_ontology",
    "dry_run": true
  }
}
```

### 4. Download a generated OWL export from an import task

```json
{
  "workflow_id": "depo_import_export",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "task_id": "import-task-id",
    "export_format": "ttl",
    "output_dir": "D:/Depo_Onto_Engine/standalone/ontology_agentic_service/output/depo_exports"
  }
}
```

## Agent Specs

Prompt specs are stored under:

- [ontology_agentic/agents/specs](D:/Depo_Onto_Engine/standalone/ontology_agentic_service/ontology_agentic/agents/specs)

They follow the deterministic structure from your provided prompt template:

- explicit role
- explicit objective
- explicit inputs
- exact checks
- strict output schema

## Integration Notes

This package is now a clean starting point for:

- ontology review services
- semantic bridge orchestration
- ontology export microservices
- DEPO backend workflow automation
- future LLM-backed ontology copilots

The current adapter uses the existing DEPO backend contracts directly:

- `GET /api/v1/ontology/registered`
- `POST /api/v1/workflows/execute`
- `POST /api/v1/ontology/merge`
- `GET /api/v1/import/owl/{task_id}/export`

That means the isolated package stays modular, while your production workflow semantics continue to live in the main application.

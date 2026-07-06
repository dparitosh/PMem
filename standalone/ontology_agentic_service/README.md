# Ontology Agentic Service

Standalone modular service for ontology-focused agent workflows.

This package is intentionally isolated from the main DEPO application, but it can now orchestrate DEPO backend APIs through a thin adapter layer instead of duplicating semantic workflow logic.

It provides:

- a lightweight agent registry
- deterministic ontology workflow handlers
- prompt-spec driven agent definitions
- optional `Owlready2` / `RDFLib` based ontology inspection and export
- a DEPO API adapter for registered ontologies, OSLC discovery/query/TRS, graph/context search, workflow execution, ontology merge, and export retrieval
- optional STEP/AP242 inspection and TTL export tools when the main backend modules are available
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
8. DEPO graph/context search
9. DEPO OSLC catalog/provider/query/TRS discovery
10. STEP/AP242 file inspection and TTL export
11. DEPO ontology merge
12. DEPO import-generated OWL export download

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

## Tool Coverage

The standalone package exposes these tool groups through `ontology_agentic.tools` and through workflow wrappers where appropriate.

Local ontology tools:

- `inspect_ontology_artifact`
- `review_ontology_structure`
- `plan_instance_alignment`
- `export_ontology`

STEP/AP242 tools:

- `inspect_step_file`
- `export_step_to_ttl`

DEPO backend tools:

- `depo_healthcheck`
- `depo_list_registered_ontologies`
- `depo_execute_semantic_workflow`
- `depo_merge_ontologies`
- `depo_export_import_owl`

Graph/context search tools:

- `depo_graph_search`
- `depo_graph_search_many`

OSLC linked-data tools:

- `depo_oslc_catalog`
- `depo_oslc_provider`
- `depo_oslc_shapes`
- `depo_oslc_query_resources`
- `depo_oslc_resource`
- `depo_oslc_dictionary`
- `depo_oslc_taxonomies`
- `depo_oslc_trs`

Workflow IDs available through `POST /api/v1/workflows/run`:

- `ontology_review`
- `ontology_alignment`
- `ontology_export`
- `step_inspect`
- `step_export`
- `depo_healthcheck`
- `depo_registered_ontologies`
- `depo_graph_search`
- `depo_oslc`
- `depo_semantic_workflow`
- `depo_ontology_merge`
- `depo_import_export`

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

## STEP/AP242 Workflow Examples

Inspect a STEP/STPX file and summarize AP242/PMI content:

```json
{
  "workflow_id": "step_inspect",
  "inputs": {
    "step_path": "D:/path/to/part.stp",
    "sample_size": 20
  }
}
```

Export STEP/STPX to Turtle using the AP242-aware backend converter:

```json
{
  "workflow_id": "step_export",
  "inputs": {
    "step_path": "D:/path/to/part.stp",
    "output_path": "D:/path/to/part.ttl",
    "namespace_prefix": "ap242",
    "include_pmi": true
  }
}
```

Note: STEP files contain low-level geometry, topology, placement, and reference entities. Keep raw STEP entity-reference graphs separate from business-object contextual graphs so customer users see meaningful parts, requirements, functions, PMI, and process traceability first.

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

### 2. Search ontology-backed graph data through DEPO

Single-term search uses the hardened `/graphfilter` API. Use this when an external agent wants the same node-first graph search behavior as the main application.

```json
{
  "workflow_id": "depo_graph_search",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "search": "REQ-*",
    "ontology_prefix": ""
  }
}
```

Multi-term search uses `/graphfilter-multi` and is useful for comparing requirements, parts, functions, and processes in one request.

```json
{
  "workflow_id": "depo_graph_search",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "names": ["REQ-*", "Part", "Function"]
  }
}
```

### 3. Use DEPO OSLC linked-data endpoints

The standalone service exposes DEPO's OSLC-aligned read-only facade for Teamcenter LDS-style discovery, query, resource shape, dictionary, taxonomy, and TRS inspection. This is an interoperability facade, not a full OSLC certification claim.

Service Provider Catalog:

```json
{
  "workflow_id": "depo_oslc",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "action": "catalog"
  }
}
```

OSLC query with search terms:

```json
{
  "workflow_id": "depo_oslc",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "action": "query",
    "resource_type": "resources",
    "query_params": {
      "oslc.searchTerms": "REQ",
      "oslc.pageSize": 20
    }
  }
}
```

TRS descriptor or changelog:

```json
{
  "workflow_id": "depo_oslc",
  "inputs": {
    "depo_api_base_url": "http://localhost:8000",
    "action": "trs",
    "section": "changelog",
    "limit": 50
  }
}
```

Supported OSLC actions are `catalog`, `provider`, `shapes`, `query`, `resource`, `dictionary`, `taxonomies`, and `trs`.

### 4. Execute Semantic Bridge instance linking remotely

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

### 5. Merge two ontologies through the existing DEPO backend

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

### 6. Download a generated OWL export from an import task

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
- `POST /graphfilter`
- `POST /graphfilter-multi`
- `GET /oslc/catalog`
- `GET /oslc/providers/{provider_id}`
- `GET /oslc/shapes` and `GET /oslc/shapes/{shape_id}`
- `GET /oslc/query/{resource_type}`
- `GET /oslc/resources/{element_id}`
- `GET /oslc/dictionaries/{prefix}`
- `GET /oslc/taxonomies` and `GET /oslc/taxonomies/{ontology_id}`
- `GET /oslc/trs`, `/oslc/trs/base`, and `/oslc/trs/changelog`
- `POST /api/v1/ontology/merge`
- `GET /api/v1/import/owl/{task_id}/export`

That means the isolated package stays modular, while your production workflow semantics continue to live in the main application.

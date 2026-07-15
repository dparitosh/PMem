# Standalone Ontology Agent Service

This folder contains only the ontology agents and external tools needed for
drag-and-drop IIF workflows:

- RDFLib inspection, review, alignment planning, and export over HTTP;
- optional Owlready2 loading and HermiT/Pellet reasoning over HTTP;
- optional Neo4j tool discovery through MCP;
- four independent agent YAML definitions;
- a plain-text workflow-building and testing guide.

It intentionally excludes DEPO/OSLC adapters, STEP, ReqIF, requirement
normalization, OpenAPI importing, frontend code, and an additional ontology
orchestrator. IIF's existing `workflow_orchestrator` controls canvas execution.

## Layout

```text
app/main.py                           Optional standalone HTTP API
ontology_agentic/
  config.py                          API and optional-security configuration
  security.py                        Optional bearer/path controls
  runtime/                           Four-agent local execution adapter
  tools/ontology_tools.py            RDFLib implementation
  tools/owlready2_tools.py            Optional Owlready2 implementation
iif_bundle/
  AgentsRegistry/Agents/             Four agent YAML files
  AgentsRegistry/CodedTools/         Five external HTTP FunctionTools
  AgentsRegistry/MCPTools/           Neo4j MCP factory
  HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt
```

## Install and start the external API

```powershell
cd D:\Depo_Onto_Engine\standalone\ontology_agentic_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python start_service.py
```

Default address: `http://127.0.0.1:8012`.

## Endpoints

- `GET /health`
- `GET /api/v1/agents`
- `GET /api/v1/tools`
- `POST /api/v1/agents/{agent_name}/run`
- `POST /api/v1/workflows/run`
- `POST /api/v1/ontology/owlready2`

## Agents

- `ontology_intake_agent`
- `ontology_review_agent`
- `ontology_alignment_agent`
- `ontology_export_agent`

## Standalone tools

- `ontology_inspect`
- `ontology_review`
- `ontology_alignment_plan`
- `ontology_export`
- `owlready2_analyze`

The IIF bundle exposes corresponding HTTP tool IDs plus `neo4j_mcp`. See
[HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt](D:/Depo_Onto_Engine/standalone/ontology_agentic_service/iif_bundle/HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt)
for the complete agent mapping, environment variables, drag/drop combinations,
and test procedures.

## Optional security

Security is disabled by default for local development. Enable bearer and path
controls with:

```powershell
$env:ONTOLOGY_API_SECURITY_ENABLED = 'true'
$env:ONTOLOGY_API_TOKEN = 'long-random-token'
$env:ONTOLOGY_API_ALLOWED_INPUT_ROOTS = 'D:\approved-input'
$env:ONTOLOGY_API_ALLOWED_OUTPUT_ROOTS = 'D:\approved-output'
```

Neo4j MCP filtering is independently enabled with
`NEO4J_MCP_SECURITY_ENABLED=true`.

## Validate

```powershell
python -m pytest tests -q
```

This does not start IIF.

# Agent-to-Tool Mapping Audit

Source registry: `D:\Download\Archimate31\AgentsRegistry`.

The registry should own agent specifications and workflow composition. The standalone ontology service should own callable ontology, STEP, ReqIF, OSLC, graph, and data-product tools. Agents should reference stable tool names; they should not contain implementation code or instantiate registries.

## Current Registry Mapping

| Agent | Current tools | Status |
|---|---|---|
| CSV Data Extractor | `parse_csvs`, `sample_mcp` | Wired; MCP URL is hardcoded |
| Multi Format Document Processor | `parse_pdfs`, `parse_excels`, `parse_images`, `parse_csvs` | Wired |
| PDF Content Extractor | `pdfocrextractor` | Wired |
| PDF Bookmark Identifier | `bookmarkextractorfrompdfs` | Wired |
| Engg Drawing Image Aligner | `align_images`, `pdf_to_image_extractor` | Wired |
| Image Differences Detector | `detect_differences` | Wired |
| Engg Drawing Deviation Analysis | `analyze_deviations_with_llm` | Wired; requires LLM/image dependencies |
| Engg Drawing Report Generator | `generate_report` | Wired |
| Entity Extraction | `extract_entities` | Wired |
| External API Connector | `get_api_response` | Wired; requires endpoint policy |
| RAG Content Extraction | `get_ingested_data` | Wired |
| Research Analysis | `search_arxiv` | Wired |
| Supply Chain Benchmarking | `web_search` | Wired; requires network policy |
| Response Report Generator | `result_to_docx`, `result_to_excel`, `result_to_pdf` | Wired |
| MES SDLC Code Generation | agent wrapper | Coupled to recursive registry loading |
| MES SDLC Code Documentation | agent wrapper | Coupled to recursive registry loading |
| MES SDLC Test Case Design | agent wrapper | Coupled to recursive registry loading |
| MES SDLC Test Script Automation | agent wrapper | Coupled to recursive registry loading |
| Content Summarization | None | Tool-free result interpreter |
| Human in the Loop | None | Tool-free approval boundary |
| MES Business Analyst | None | Missing analysis tool |
| MES Code Implementation | None | Missing approved mutation tool |
| MES Testcase and Document Generator | None | Missing explicit tool mapping |

## Required Ontology Agent Mapping

| Agent | Tools |
|---|---|
| Ontology Intake Agent | `inspect_ontology_artifact` |
| Ontology Structure Review Agent | `review_ontology_structure` |
| Ontology Alignment Planner | `plan_instance_alignment`, `depo_list_registered_ontologies`, `depo_graph_search` |
| Ontology Export Agent | `export_ontology`, `depo_export_import_owl` |
| Ontology Merge Agent | `depo_merge_ontologies` |
| STEP/AP242 Inspection Agent | `inspect_step_file` |
| STEP/AP242 Export Agent | `export_step_to_ttl` |
| ReqIF Inspection Agent | `inspect_reqif_file` |
| ReqIF Export Agent | `export_reqif_to_ttl` |
| Requirement Normalization Agent | `normalize_requirement_records`, `requirement_alignment_profile` |
| Requirement Alignment Export Agent | `export_requirements_alignment_ttl` |
| Graph Context Agent | `depo_graph_search`, `depo_graph_search_many`, `depo_oslc_query_resources`, `depo_oslc_resource` |
| OSLC Linked Data Agent | `depo_oslc_catalog`, `depo_oslc_provider`, `depo_oslc_shapes`, `depo_oslc_dictionary`, `depo_oslc_taxonomies`, `depo_oslc_trs` |
| Data Product Builder Agent | `build_data_product` |
| Ontology Orchestrator Agent | No domain tool directly; invokes approved agents |
| Human Approval Agent | No mutation tool; approves proposals and publication |

## Recommended YAML Contract

Current YAML references arbitrary modules and objects. The target format is name-only:

```yaml
name: Ontology Intake Agent
description: Inspect an OWL, RDF, or Turtle artifact.
tools:
  - inspect_ontology_artifact
```

An allowlisted Tool Registry resolves the name:

```yaml
inspect_ontology_artifact:
  module: ontology_agentic.tools.ontology_tools
  function: inspect_ontology_artifact
  capability: ontology.read
  mutates: false
```

Tools should be normal functions with validated input and JSON-compatible output. They should not create LLM clients, import the FastAPI application, or write Neo4j without an approved command.

```python
def inspect_ontology_artifact(request: dict, context: ToolContext) -> ToolResult:
    ...
```

Disable the current inline YAML `exec()` path for customer deployments. Arbitrary module imports must also be replaced by an allowlist.

## Ontology Workflows

```text
Ontology review:
  Intake -> Structure Review -> Human Approval

Instance alignment:
  Intake -> Graph Context -> Alignment Planner -> Human Approval

STEP/AP242 traceability:
  STEP Inspection -> Alignment Planner -> Graph Context -> Human Approval

ReqIF requirements:
  ReqIF Inspection -> Normalization -> Alignment Export -> Human Approval

Data product publication:
  Review/Alignment -> Validation -> Data Product Builder -> Human Approval
```

## Deployment Configuration

Do not deploy customer paths or endpoints from the registry files. Use environment configuration:

```env
AGENT_REGISTRY_PATH=D:/customer/AgentsRegistry
AGENT_SPEC_PATH=D:/customer/AgentsRegistry/Agents
TOOL_MANIFEST_PATH=D:/customer/AgentsRegistry/tool-manifest.yaml
MCP_CSV_URL=http://customer-mcp:3000/sse
DEPO_API_BASE_URL=http://192.168.1.4:8000
OLLAMA_BASE_URL=http://customer-ollama:11434
AGENT_DATA_DIR=D:/customer/agent-data
AGENT_OUTPUT_DIR=D:/customer/agent-output
```

## Audit Conclusion

The external registry currently contains useful generic document, image, and MES agents, but it has no explicit ontology/graph/STEP/ReqIF/OSLC mappings. Add those mappings to the registry while keeping their implementations in the standalone ontology service.

Do not copy every coded tool into the ontology service. Register only approved callable functions and their dependencies. This prevents image-processing, MES, MCP, and ontology concerns from becoming one coupled runtime.

## Low-Code / No-Code Canvas Contract

For the customer application, publish three metadata catalogs to the UI:

1. Agent catalog: `agent_id`, display name, system prompt, allowed tool IDs, input schema, output schema, and approval policy.
2. Tool catalog: `tool_id`, description, transport, HTTP method or MCP operation, capability, input schema, and mutation flag.
3. MCP catalog: server ID, endpoint, authentication environment variable, allowed operations, query limits, and timeout.

The canvas node should contain only references and mappings:

```json
{
  "id": "node-1",
  "agent_id": "semantic_bridge_planner_agent",
  "tool_ids": ["semantic.alignment.plan", "graph.context.search"],
  "input_mapping": {"ontology_path": "${input.ontology}", "instance_metadata": "${input.metadata}"},
  "approval_required": true,
  "position": {"x": 420, "y": 180}
}
```

The tool catalog should expose stable functions, not Python imports:

```json
{
  "tool_id": "graph.context.search",
  "transport": "mcp",
  "server_id": "neo4j",
  "operation": "contextual_search",
  "capability": "graph.read",
  "mutates": false,
  "input_schema": {"required": ["search"]}
}
```

Recommended Neo4j MCP configuration:

```env
AGENTIC_DEPO_API_BASE_URL=http://192.168.1.4:8000
AGENTIC_SERVICE_BASE_URL=http://192.168.1.4:8012
AGENTIC_NEO4J_MCP_URL=http://192.168.1.4:8765/sse
AGENTIC_OLLAMA_BASE_URL=http://192.168.1.4:11434
AGENTIC_MCP_AUTH_TOKEN=
```

The Neo4j MCP server should expose only bounded operations such as `contextual_search`, `expand_one_hop`, `ontology_graph`, `schema_summary`, and `graph_metrics`. Arbitrary Cypher, unrestricted writes, and database selection from the model must be disabled.

The canvas runtime should validate before execution:

- every `agent_id` exists
- every `tool_id` exists and is allowed for that agent
- every edge connects existing nodes
- input mappings satisfy the tool schema
- cycles are explicitly allowed only for bounded retry loops
- mutation tools require human approval
- MCP server health is available before the run starts

This is the deployment boundary for the customer low-code application. The external `AgentsRegistry` supplies prompts and agent metadata; the standalone ontology service supplies the callable implementation and API contracts.

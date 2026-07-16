# Ontology workflow assets for IIF

This directory contains drag-and-drop agents and tool definitions for IIF. It is an asset pack,
not a standalone FastAPI application, and it does not modify or start `D:\Download\IIF_v1`.

```text
ontology_agentic_service/
|-- AgentsRegistry/
|   |-- Agents/                 # four agent YAML definitions
|   |-- CodedTools/             # local libraries and external HTTP tools
|   `-- MCPTools/               # optional Neo4j MCP discovery
|-- FastAPIAdapter/             # optional existing-Depo-frontend API compatibility
|-- tests/                      # tool and registry contract tests
|-- HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt
|-- requirements-ontology.txt
|-- requirements-owlready2.txt
|-- requirements-neo4j-mcp.txt
|-- requirements-depo-adapter.txt
`-- requirements-test.txt
```

The key boundary is deliberate:

- `ontology_rdflib_tools.py` and `ontology_owlready2_tools.py` run locally inside IIF.
- `ontology_external_api_tools.py` contains all direct external HTTP calls.
- `neo4j_mcp.py` connects only when Neo4j MCP is enabled.

Optional dependencies are separated: install the Owlready2 or Neo4j MCP requirements only when
that capability is enabled. `AgentsRegistry` deliberately contains no package `__init__.py` files,
so merging it cannot overwrite IIF's existing registry package markers.

`FastAPIAdapter` is an optional router for an IIF-exported FastAPI package. It implements the
existing Depo frontend's agentic API contract without creating a second application.

See [HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt](HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt) for the complete
agent/tool mapping, configuration, drag-and-drop examples, and validation commands.

When configuring through the IIF UI, use `IIF_UI_CONFIGURATION.txt` for exact module/object names
and agent field values. The System Prompt field accepts prompt text only, not the complete YAML.

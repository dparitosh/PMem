# DT Requirements Design ↔ PMem integration

The external `DT_Requirements_Design` repository is an agent/workflow client of
PMem, not a second graph runtime. Its agents should call PMem only through the
OSLC gateway and PMem's governed OpenAPI capabilities.

## Interaction contract

```text
DT agent/orchestrator
        ↓ pmem_oslc_client (HTTPS gateway)
PMem OSLC catalog/provider/shapes/query/TRS
        ↓
PMem agentic catalog and workflow runs
        ↓ approval boundary
Canonical publication API → graph
```

The external `ontology_alignment` workflows map to PMem's catalog, provider,
shape, taxonomy, dictionary and bounded query endpoints. The
`IIF_DT_Design_To_Build_Enablement/workflow-manifest.yaml` sequence maps to
engineering inspection, quality telemetry and CEIM contract capabilities.

PMem now exposes:

```text
POST /api/v1/integrations/dt-requirements-design/compatibility
```

Pass the external workflow manifest as `{ "manifest": { ... } }`. The response
reports compatible tools, missing capabilities, transport and the write boundary
without importing external code or executing the workflow.

## Alignment status

| External capability | PMem interaction | Status |
| --- | --- | --- |
| `pmem_oslc_client` | OSLC catalog/provider/resource-shape/query/taxonomy/dictionary/TRS APIs | Supported |
| Ontology intake/review/alignment | OSLC evidence plus CEIM contract and graph retrieval | Supported as governed read/review flow |
| DT requirements intelligence | Engineering inspection plus GraphRAG context | Supported through compatibility mapping |
| DT quality director | Pipeline telemetry and CEIM contract | Supported when those services are configured |
| External agent runtime import | Copying or executing foreign modules inside PMem | Not supported by design |
| Direct Neo4j/MCP writes | Bypass of canonical publication | Prohibited |

Configure the external client with `PMEM_OSLC_GATEWAY_URL` ending in `/oslc`,
`PMEM_OSLC_ENABLED=true`, and deployment-managed credentials. The adapter is a
compatibility check; it does not claim that a remote OSLC provider or LLM runtime
is live until the gateway health and catalog calls succeed.

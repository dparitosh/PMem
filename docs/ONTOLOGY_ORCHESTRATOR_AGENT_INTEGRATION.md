# Ontology agent integration

The ontology orchestrator is exposed by the Agentic Control Plane at
`POST /api/v1/ontology-agents/orchestrate`. It implements the agent contracts
from the external ontology-orchestrator design set:

| Agent | Responsibility | Write access |
| --- | --- | --- |
| Ontology Intake | Parse an approved RDF/OWL artifact and count factual structures | None |
| Ontology Structure Review | Report missing classes, properties, domain/range edges, or individuals | None |
| Semantic Bridge Planner | Count entity, attribute, relationship, and metadata mapping work | None |
| Ontology Orchestrator | Run intake, review, and planning in the declared order | None |
| Ontology Export | Remains mapped to the existing approval-gated export tool | Governed service only |

Example request from an authenticated internal client:

```powershell
$body = @{
  workflow_id = 'ontology_review'
  ontology_id = '<registered-ontology-id>'
  import_task_id = '<completed-import-task-id>'
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8012/api/v1/ontology-agents/orchestrate' `
  -Headers @{ Authorization = 'Bearer <GRAPH_READ_TOKEN>' } `
  -ContentType 'application/json' `
  -Body $body
```

The service resolves `ontology_id` through the registered ontology store and
`import_task_id` through the retained import-task store. Callers do not need to
send local filesystem paths. Direct `ontology_path` input remains available for
controlled internal tooling and is restricted to `ONTOLOGY_AGENT_ALLOWED_ROOTS`,
which defaults to `data`, `ontology`, `backend/test_data`, and
`ontology_uploads`.
`ONTOLOGY_AGENT_MAX_BYTES` limits the artifact size and defaults to 25 MiB.
The LLM is disabled by default. Set `ONTOLOGY_AGENT_LLM_ENABLED=true` only
after configuring the existing `backend/core/llm.py` provider. LLM output is
bounded review guidance and is never an approval or a publication command.

The frontend can use the response to render an intake summary, structural
issues, and Semantic Bridge planning counts. Existing Bridge preview, approval,
PostgreSQL job history, and Graph Service publication remain the authoritative
write path.

The specialist tools are separately allowlisted so an intake agent cannot call
the review or planning operation by changing a prompt. Their read-only routes
are `/api/v1/ontology-agents/intake`, `/api/v1/ontology-agents/review`, and
`/api/v1/ontology-agents/bridge-plan`. The system prompts and tool bindings are
versioned in `backend/agentic_service/catalog.json`; prompt text is treated as
policy metadata, while the server-side route and approval checks remain the
enforcement mechanism.

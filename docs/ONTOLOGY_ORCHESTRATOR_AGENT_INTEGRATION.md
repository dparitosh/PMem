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
  ontology_path = 'data\customer\motor.ttl'
  instance_metadata = @{
    entities = @('Motor')
    attributes = @('weight')
    relationships = @('hasPart')
    metadata = @('sourceSystem')
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8012/api/v1/ontology-agents/orchestrate' `
  -Headers @{ Authorization = 'Bearer <GRAPH_READ_TOKEN>' } `
  -ContentType 'application/json' `
  -Body $body
```

The service only reads files under `ONTOLOGY_AGENT_ALLOWED_ROOTS`, which
defaults to `data`, `ontology`, `backend/test_data`, and `ontology_uploads`.
The LLM is disabled by default. Set `ONTOLOGY_AGENT_LLM_ENABLED=true` only
after configuring the existing `backend/core/llm.py` provider. LLM output is
bounded review guidance and is never an approval or a publication command.

The frontend can use the response to render an intake summary, structural
issues, and Semantic Bridge planning counts. Existing Bridge preview, approval,
PostgreSQL job history, and Graph Service publication remain the authoritative
write path.

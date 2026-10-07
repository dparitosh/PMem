# Agent Memory Augmentation

This app now has an optional graph-native memory layer inspired by
`neo4j-labs/agent-memory`.

It is intentionally **off by default** and is implemented as a local Neo4j
adapter so customer environments do not need a new experimental dependency.

## What It Adds

- Short-term memory: chat turns by `session_id`
- Long-term memory: approved Semantic Bridge mappings
- Reasoning memory: compact tool/workflow traces and summaries
- Provenance edges from assistant messages to graph nodes when graph context is supplied

## What It Does Not Replace

- Neo4j remains the product/ontology/instance graph store.
- Owlready2 remains the OWL semantic reasoning layer.
- RDFLib / OWL / TTL exports remain the ontology exchange path.
- Semantic Bridge remains the approval workflow for instance-to-ontology mappings.

## Enable It

Set these in root `.env.local` and restart through the deployment lifecycle launcher:

```env
AGENT_MEMORY_ENABLED=true
AGENT_MEMORY_SCOPE=customer-id:project-id
AGENT_MEMORY_QUERY_TIMEOUT=5
AGENT_MEMORY_RETENTION_DAYS=30
```

The adapter uses the existing Neo4j connection and official Neo4j driver. It
creates lightweight constraints/indexes on first use.

Memory operations are best-effort and bounded. The default memory query timeout
is 5 seconds and is clamped between 1 and 30 seconds.

`AGENT_MEMORY_SCOPE` is the isolation boundary for sessions and reusable mapping
facts. Give each customer/project deployment a unique value. If it is omitted,
the service derives the scope from `DEPO_TENANT_ID:DEPO_PROJECT_ID`.

PostgreSQL conversation history is authoritative. LangGraph does not keep a
second process-local checkpoint, so history remains consistent across restarts
and multiple service workers. Neo4j provides optional context, reasoning traces,
and approved Semantic Bridge facts.

## API Endpoints

- `GET /api/v1/agent-memory/status`
- `GET /api/v1/agent-memory/sessions/{session_id}/context?limit=6`
- `DELETE /api/v1/agent-memory/sessions/{session_id}`

The context and delete endpoints require the server-issued `X-Session-ID` value
to match the path. Delete the current conversation from PowerShell with:

```powershell
$sessionId = "paste-the-X-Session-ID-value"
Invoke-RestMethod -Method Delete `
  -Uri "http://127.0.0.1:8000/api/v1/agent-memory/sessions/$sessionId" `
  -Headers @{ "X-Session-ID" = $sessionId }
```

## Stored Graph Labels

- `AgentMemorySession`
- `AgentMemoryMessage`
- `AgentMemoryTrace`
- `AgentMemoryFact`

Relationships:

- `HAS_MESSAGE`
- `FOLLOWED_BY`
- `HAS_REASONING_TRACE`
- `TOUCHED`

## Current Hooks

### Knowledge Companion

After `/chat` or `/chat/jobs` completes, the app records:

- user question
- assistant answer
- session id
- graph nodes supplied in `graph_context`
- a reasoning trace for the chat operation

The memory write is best-effort. If Neo4j is down or memory is disabled, chat
still returns normally.

When memory is enabled, recent session memory is also injected into the
Knowledge Companion prompt as a compact continuity block. Live graph/tool
results still take priority for current facts.

### Semantic Bridge

The Semantic Bridge UI invokes Ontology Governor to create a saved recommendation
preview. Recommendations are retained in PostgreSQL (`semantic_bridge_jobs_v1`)
and displayed with evidence, validation, eligibility and the agent run ID. Users
can reload the saved preview ID or download its evidence. Manual mapping drafts
are included in the preview; the server resolves source rows and graph targets
instead of accepting browser-supplied graph identifiers.

Connect governed agent credentials in Admin and enter the steward identity before
creating a preview. Select eligible recommendations and confirm review before
publishing. A recommendation never approves itself. Changes to the selected
source, ontology or manual mappings require a new preview. Publication receipts
and saved job status support recovery after an interrupted request.

The ontology merge controls also invoke Ontology Governor. Preview two registered
ontologies with retained RDF artifacts, review conflicts, then explicitly create
the merged draft. Graph-only ingestion records are sufficient for mapping lookup
but do not replace the RDF artifacts required for ontology merge or reasoning.

After `instance.link`, the app records approved mappings as reusable facts:

- source instance term
- source type
- target ontology term
- target ontology type
- confidence
- mapping type
- import task id
- workflow task id

This supports future mapping reuse and auditability.

When memory is enabled, `instance.link` also reuses prior approved mapping facts
as an additional scorer. A remembered mapping is only used when it resolves to a
current graph-linkable ontology class or property and passes validation.

## Remaining Enhancements

1. Add a UI panel that shows “memory used” and “nodes touched”.
2. Schedule `AgentMemoryService.prune_expired_sessions()` in the customer job
   scheduler using `AGENT_MEMORY_RETENTION_DAYS`.
3. Add tenant/project scope management in Admin.
4. If the customer accepts the dependency, wrap the official
   `neo4j-agent-memory` SDK behind the same `AgentMemoryService` interface.

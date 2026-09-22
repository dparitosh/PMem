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
AGENT_MEMORY_SCOPE=project
AGENT_MEMORY_QUERY_TIMEOUT=5
```

The adapter uses the existing Neo4j connection and official Neo4j driver. It
creates lightweight constraints/indexes on first use.

Memory operations are best-effort and bounded. The default memory query timeout
is 5 seconds and is clamped between 1 and 30 seconds.

## API Endpoints

- `GET /api/v1/agent-memory/status`
- `GET /api/v1/agent-memory/sessions/{session_id}/context?limit=6`

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

## Recommended Next Enhancements

1. Add a UI panel that shows “memory used” and “nodes touched”.
2. Add admin cleanup for old memory by session, scope, or age.
3. Add tenant/project scoping controls in Admin.
4. If the customer accepts the dependency, wrap the official
   `neo4j-agent-memory` SDK behind the same `AgentMemoryService` interface.

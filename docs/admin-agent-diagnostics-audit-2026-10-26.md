# Admin model and memory diagnostics audit — 2026-10-26

Scope: AgentControlPanel.js and the agentic /llm/health, /llm/probe and /memory/status handlers, including provider adapters, authentication, timeouts and result presentation. No live provider inference was used during this audit.

| Action | Actual verification | Authorization / side effects |
| --- | --- | --- |
| Check model configuration | Selected provider settings; Ollama discovery when enabled. Cloud credentials are present/valid in shape, not authenticated by this action. | Graph read identity. No paid cloud inference. Ollama tags discovery is bounded to five seconds. |
| Verify model capabilities | Independent generation, JSON-schema validation and one fake native tool-call response. | Supervision approval. Up to three inference calls; the named fake tool is never executed. Embeddings and business-answer accuracy are not tested. |
| Check agent memory | Optional graph-memory configuration and read connectivity; cached schema/write/fact observations. | Graph read identity. Does not write a test memory, verify recall quality or check PostgreSQL workflow/read-goal scratchpads. |

## Corrections

- Invalid memory configuration no longer renders as disabled merely because enabled=false accompanies the error.
- Model configuration checks no longer cancel or erase independent memory checks/results.
- Memory refresh clears stale results and errors, prevents repeated concurrent clicks and resets on credential changes; aborts suppress late updates.
- Schema/write observations are labeled as last recorded, with separate unavailable/not_verified states.
- Configuration-only cloud endpoints are no longer labeled as checked endpoints. Ollama discovery explicitly states that generation and tools remain unverified.
- Invalid generation-route configuration with Ollama discovery disabled returns a safe configuration error instead of an unhandled health failure.
- Each capability probe has a total asynchronous deadline of at most 60 seconds, including admission and response reading. Three sequential probes therefore fit below the 210-second browser timeout. Memory reads use an independent longer timeout for the two possible database probes.
- Existing authentication gates are retained. Capability results remain independent; malformed or incomplete output cannot claim verified capability. Keys and upstream response bodies are not rendered.

## Validation and limits

Model/provider/readiness and memory regression suites passed 70 tests; two focused deadline/invalid-route tests also passed. Admin UI tests passed 15 tests. The production frontend build passed; existing large-chunk warnings remain. No provider key was changed, no model downloaded and no memory/graph data was changed. Live inference, recall-quality acceptance and remote APIM timeout/policy validation remain separate deployment checks. Current source changes require deployment/restart to affect the running app.

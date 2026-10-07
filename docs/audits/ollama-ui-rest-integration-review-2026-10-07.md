# Ollama REST and UI integration audit â€” 2026-10-07

## Scope and result

Reviewed Chatbot, AgentControlPanel, SemanticBridgeJobs, frontend API adapters,
Agentic companion/orchestration/proposal routes, Ollama REST adapters and the
LangChain client factories. This is a source and regression-test audit, not a
claim of flawless live behavior. Existing changes remain uncommitted.

## Confirmed findings

| Priority | Gap and user impact | Evidence | Recommended correction |
|---|---|---|---|
| P1 | Graph retrieval uses environment proxy settings, while Ollama and other peer calls disable them. A VM proxy can break chat retrieval even when Ollama works. | `backend/agentic_service/companion.py:32` AsyncClient has no trust_env=False. | Use the shared peer networking policy; test retrieval with proxy environment variables set. |
| P1 | Graph retrieval buffers and decodes the complete response without a response-size guard or shape validation. Invalid/oversized upstream data can consume memory or fail after a successful HTTP response. | `backend/agentic_service/companion.py:37-42` client.get/response.json. | Stream a bounded response and validate nodes/relationships before scoring. |
| P1 | Ontology review uses synchronous llm.invoke without an overall operation deadline. Transport read timeouts alone do not bound a long sequence of streamed model chunks. | `backend/agentic_service/ontology_orchestrator.py:280` and synchronous orchestration route. | Use the bounded REST generation adapter and enforce an overall review deadline; keep deterministic evidence when model generation fails. |
| P2 | LLM ontology validation questions are returned by the backend but not displayed in Semantic Bridge. Users cannot see the model recommendation they enabled. | `ontology_orchestrator.py:262` returns llm; `SemanticBridgeJobs.js:108-119` does not render it. | Display recommendation text, unavailable/disabled state and review-only status beside deterministic validation evidence. |
| P2 | Chat drops generation status and the run ID. The SSE final response omits generation, and Chatbot does not retain run_id. Users cannot distinguish model completion from fallback or correlate a response with telemetry. | `agentic_service/router.py:391-393`; `Chatbot.js:197-207`. | Include structured generation/run metadata in SSE and show it in the assistant response details. |
| P2 | Capability endpoints advertise non-incremental/completed-response streaming despite token callbacks and an incremental Ollama stream. | `agentic_service/router.py:364,374,386`; `local_llm.py:140-159`. | Describe actual supported behavior and conditional generation accurately. |
| P2 | The agent tool-proposal endpoint is not connected to a frontend API method or component. Enabling Ollama does not make catalog agents automatically propose actions through the UI. | `agentic_service/router.py:416`; no frontend caller to /agents/{agent_id}/suggest. | Add a reviewed proposal UI with allowlisted inputs, evidence and an explicit execution action. This endpoint proposes JSON; it does not prove native tool-calling support. |
| P2 | Chat disables its input while a request is active but offers no explicit Stop action. Default browser stream deadline is fifteen minutes. | `Chatbot.js:103,527`; `config.js:94`. | Offer cancel/stop with clear partial-response status and align the deadline with server/gateway budgets. |
| P2 | Browser SSE parsing has no frame/total size bound. A missing newline or abnormal upstream stream can grow its buffer until timeout. | `Chatbot.js:244-246`. | Bound frame and cumulative bytes, reject malformed completion markers, cancel oversized streams. |
| P2 | Dormant import API adapter methods still target legacy Ollama endpoints absent from the standalone ingestion service. Reusing these methods would produce 404s. | `apiClient.js:523-525`, `config.js:271-272`; routes exist only in retired backend/main.py. | Remove unused wrappers or deliberately map them to supported Agentic diagnostic/generation operations. |

## Service ownership and REST contracts

| Owner | UI/API consumers | Dependency and purpose |
|---|---|---|
| Agentic service | Chatbot: POST /api/v1/chat-stream; POST /api/v1/chat; sample queries; chat jobs | Retrieves bounded evidence from Graph service; optional Ollama summary; PostgreSQL sessions/telemetry and optional Neo4j memory. |
| Agentic service | AgentControlPanel: GET /api/v1/llm/health; workflow run inspect/control/recovery | Read-authenticated discovery/configuration diagnostic; supervisor authorization for controls. Discovery does not verify generation. |
| Agentic service | Semantic Bridge: POST /api/v1/ontology-agents/orchestrate | Ontology intake, structural review, deterministic alignment and optional LLM review questions. Retained RDF artifacts remain required. |
| Agentic service | POST /api/v1/agents/{agent_id}/suggest | Native chat JSON proposal; catalog/input preflight; no automatic tool execution. Frontend integration is missing. |
| Graph data service | GET /api/v1/graph/search; private GET /api/v1/graph/mapping-terms | Source of chat evidence and graph-backed mapping targets. UI/workflow layers should consume services, not issue graph queries directly. |
| Ontology service | Governed merge preview/apply through governor | Validated RDF merge and retained artifacts; model generation is not approval. |
| Ollama/APIM | POST /api/generate, POST /api/chat, POST /api/embed; optional GET /api/tags | Generation, chat/proposals and embeddings are distinct capabilities. The supplied APIM contract does not expose tags. Tool-call support needs its own test. |
| PostgreSQL data layer | PostgresRegistry and credential/session repositories | Durable recommendations, receipts/state, sessions and telemetry. Browser-stored key presence is not proof of authorization. |

## UX and performance verification priorities

1. Display recommendations and distinguish deterministic evidence, model summary, unavailable fallback, and publication approval.
2. Show separate configuration/discovery/generation/embedding/proposal capability status; do not equate a missing tags route with generation failure.
3. Bound response sizes and operation deadlines consistently; test gateway streaming behavior and proxy settings on the VM.
4. Add Stop and clear retry/recovery behavior; preserve user input on failures and expose the telemetry run ID.
5. Test navigation, scope changes and credential expiry during in-flight requests in light/dark modes, including narrow screens and keyboard access.
6. Measure p50/p95 time to first evidence and final response, concurrent request load and browser memory on actual deployment. These metrics were not measured here.

## Validation

- 19 frontend regression tests passed: Chatbot, AgentControlPanel and SemanticBridgeJobs.
- 19 backend Ollama regression tests passed: URL/auth routing, health flags, client selection and service behavior.
- Tests validate existing guarded behavior, including truncated chat completion rejection, scope/session resets and evidence-preserving fallback. They do not eliminate the findings above.
- No live APIM/Ollama, database or browser visual inspection was performed. Full FastAPI/httpx integration tests cannot run in the available Python runtime without additional dependencies.
- No source fixes were made in this audit turn. The remediation list is separate from earlier uncommitted fixes.

## Remediation implemented

All ten source gaps above have corresponding changes in this working tree:
bounded streaming Graph retrieval with proxy-independent peer policy and shape
validation; timed REST-based ontology model recommendations; visible Bridge model
recommendations; chat generation/run metadata; accurate capability descriptions;
a catalog-backed proposal/review/execute UI; Stop with incomplete-answer labeling;
bounded browser SSE parsing; and removal of unused legacy Ollama import wrappers.
Chat restores failed questions for retry. Proposal execution consumes the reviewed
proposal before dispatch so response loss does not leave the same execution button
active. Stopping a wait does not undo a tool write; telemetry remains the recovery
source.

Validation: 26 backend tests and 22 frontend tests passed, production frontend
build passed. Tests include bounded/invalid evidence, model timeout fallback,
explicit proposal approval, generation/run metadata and Stop behavior. Live APIM
stream buffering, model capability, deployment latency and visual layout remain
unverified; existing bundle-size/test-library warnings remain. Changes are local
and uncommitted.

## Persistence and navigation follow-up

General catalog recommendations now persist as immutable records in
PostgresRegistry namespace `agentic_recommendations_v1`. The suggestion API returns
a recommendation ID. The read-authenticated GET
`/api/v1/agent-recommendations/{recommendation_id}` verifies the existing identity
fingerprint before returning the record and never returns its owner fingerprint.
Credential-bearing model input fields are rejected before storage. Browser session
storage keeps only a recommendation ID bookmark, not the recommendation payload
or credentials. A reloaded recommendation always requires fresh review.

Execution result JSON is visible after a successful request; failed requests show
the supplied telemetry run ID for reconciliation. This does not guarantee that an
unknown downstream result can be reconstructed from telemetry. Credential rotation
or a new browser service session can change the identity fingerprint and prevent
access to an older recommendation; authorization remains enforced rather than
silently reassigning its owner. Storage failures return a service error without
executing any proposed tool.

The chat reader is released on terminal completion instead of waiting for the
connection to close. Follow-up verification passed: 29 backend tests, 23 frontend
tests, production build and syntax checks. No live API/database deployment was
performed.

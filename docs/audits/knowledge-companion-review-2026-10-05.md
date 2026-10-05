# Knowledge Companion audit — 2026-10-05

## Remediation

Read-only dispatch now preserves the verified caller key across rotation. Chat requests use bounded strict-text models; selected ontology identifiers parameterize server graph retrieval, while client node text is ignored as evidence. Chat sessions reset on read-key changes/clearing and abort pending requests. A stream requires both evidence and completion before publishing success. Chat surfaces and Clear use theme tokens. Sample data availability is unknown rather than asserted, and prompts/capabilities explicitly describe ontology search. Instance comparison and impact analysis remain unsupported; the UI no longer advertises them.

Eight focused backend tests passed, including rotated-key forwarding, strict input/context bounds and parameterized graph scope. Two frontend regression cases were added for truncated streams and key/session reset; both changed JSX files passed syntax parsing. Package validation passed. Full Vitest and live service execution remain pending; they were not run in this dependency-limited workspace.

Scope: Chatbot/LandingPage → service authentication → agentic chat, streaming and sessions → graph search and graph memory. Static trace of current release; no customer VM access.

## Findings

| Priority | Location | Finding and required correction |
| --- | --- | --- |
| P1 | backend/agentic_service/transport_auth.py:56 | Graph retrieval reads GRAPH_READ_TOKEN from process environment even when inbound authentication uses PostgreSQL credential authority. After Admin rotates the read key, the new browser key can validate while Companion sends the old key to graph and fails. For read-only dispatch, propagate the already verified caller read credential in token mode; retain endpoint allowlisting and gateway subscription handling. Never retrieve plaintext from stored digests. |
| P1 | backend/graph_service/query_repository.py:26; backend/agentic_service/companion.py:75 | Retrieval searches only OntologyResource labels/IRIs; the answer is a concatenation of labels/relationship types. Imported instance nodes, EBOM/MBOM comparison, process chains and change-impact traversal are not implemented in this path despite the offered sample prompts. Add authorized instance/context retrieval and explicit read-only handlers with evidence for each advertised operation, or restrict prompts/capabilities to ontology search until supported. |
| P2 | backend/agentic_service/router.py:294 | Chatbot submits a bounded graph_context snapshot, but chat never reads it; companion.ask receives only query and headers. Questions about the current selected ontology or visible graph are evaluated globally. Validate context identifiers and resolve/filter against server-owned graph evidence; never trust client text as evidence. |
| P2 | frontend/src/Components/Chatbot.js:352 | EOF with any accumulated text is treated as successful even without the done event. A broken stream after its text event but before evidence is accepted and sent to setChatResults. Require the completion and evidence contract; interrupted responses must be explicitly incomplete and must not publish successful results. |
| P2 | frontend/src/Components/Chatbot.js:244; backend/agentic_service/sessions.py:19 | Session IDs survive in sessionStorage and component refs while ownership is derived from the credential. Read-key replacement does not clear the session; credential clearing removes storage but Chatbot can reuse its stale ref. New credentials can therefore hit session-owner 403. Reset/abort Companion session state on read-credential changes or clearing; do not silently retry unrelated authentication failures. |
| P2 | backend/agentic_service/router.py:271 | Backend accepts arbitrary dictionary messages and coerces non-text values with str(); no server-side message length limit mirrors the frontend's 4000-character bound. Use a shared typed request model with bounded message/session/context fields across validate/chat/jobs/stream. |
| P2 | frontend/src/Components/Chatbot.js:516 | Clear uses white text and a translucent white background on the light utility bar; several chat surfaces use fixed light palettes under dark mode. Use IX theme text/surface/border tokens and verify both themes. |
| P3 | backend/agentic_service/router.py:259 | Sample queries report data_available=true without inspecting graph readiness or instance data. Return an accurate unknown/unverified state or derive availability from a bounded authorized check. |

## Confirmed behavior and limits

- Companion is evidence-grounded deterministic search, not an LLM reasoning path. Streaming emits an already completed answer, then evidence, then done; it is not incremental model generation.
- Session ownership, fixed maximum expiry and idle expiry are enforced server-side. Memory is scoped by owner/session and optional; follow-up history requires enabled graph memory.
- Shared service CORS exposes X-Session-ID and X-Session-Expires-At. CORS configuration alone does not establish successful chat POST execution.
- Current frontend tests cover expiry retry and input locking, but not truncated streams, credential rotation/session reset, context filtering, or instance analytics answers. The older test_chat_memory_limits.py targets backend.agent chat rather than this agentic Companion route.

## Validation

Four dependency-light tests passed: test_agent_io_keywords and test_credential_check. These verify the adapter keyword fix and credential probe contract, not full Companion execution. Full frontend tests/build and live PostgreSQL/Neo4j/APIM checks were not run because the workspace lacks the application dependency installation and customer infrastructure. Findings above are code-trace results; no fixes are claimed by this audit.

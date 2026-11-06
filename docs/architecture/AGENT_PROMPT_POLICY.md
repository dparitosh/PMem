# Agent prompt policy

Proposal policy `proposal-v2` selects one allowlisted tool. Native mode returns exactly one function-call proposal; structured mode returns a validated `tool_id` and `inputs` object. Neither mode grants approval or executes the proposed tool. Server credentials, lifecycle checks and explicit execution requests remain authoritative.

Catalog prompts must be nonempty text within 16,384 UTF-8 bytes. Each generated prompt snapshot includes its system-prompt SHA-256 hash as well as the configured version label. Governor and steward role instructions describe proposal and evaluation responsibilities rather than model-issued authorization or reports in proposal mode. Legacy chat uses an explicit untrusted-evidence and approval boundary.

Before inference and recommendation persistence, credential fields, known configured secret values, bearer credentials and recognizable password/token assignments are redacted. Companion input and graph evidence follow the same policy. Read access also redacts older recommendation records; this does not erase their original stored bytes. Arbitrary unlabeled secrets cannot be reliably identified, so do not enter credentials in task text or evidence. Historical persisted records require separate administrator review.

Companion summaries must cite supplied identifiers using `[evidence:IDENTIFIER]`. Missing or invented citations reject the model summary and preserve deterministic graph evidence. This validates citation membership, not whether every statement is entailed by its citation. Model streams are buffered until completion and citation checks pass; deterministic retrieval status may still stream immediately. The chat status endpoint reports buffered generation delivery.

## Shared model composition

Active agentic summaries, tool recommendations, ontology evidence reviews, and capability probes send inference through `backend.core.ollama_runnable.OllamaRestRunnable`. This LangChain Runnable preserves the configured native Ollama/APIM URL and wire contract, uses shared admission/circuit policy and operation deadlines, and checks prompt/response byte limits. It performs one inference dispatch; it does not retry generation automatically. Nonstreaming and streaming results require native completion markers. Streaming remains buffered by the Companion until citation validation passes.

System/user pairs use `ChatPromptTemplate` with policy and evidence passed as literal values. Prompt snapshots retain the actual rendered messages. Structured/native tool outputs still pass the existing allowlist and input-schema validation before a recommendation is retained; the model cannot authorize execution. Credentials remain adapter configuration rather than chain input. Existing GraphRAG message/embedding clients already use LangChain and retain their guarded provider adapters. The aggregate compatibility host is not a production agentic entry point.

LangChain composition is loaded lazily through `backend.core.llm_runtime` in a background thread, with one initializer per event loop and the caller's remaining deadline. A timed-out caller does not cancel initialization needed by another request. Health/discovery do not import the model stack. Both agentic API and workflow-worker dependency profiles already include the pinned `langchain-core` dependency; no additional package or framework upgrade is required.

PostgreSQL grants, leases, approvals, publication receipts, idempotency, graph batching, and MCP process ownership remain service responsibilities. Framework composition does not replace those guarantees.

# Agentic execution and UI audit — 8 October 2026

Scope: single-customer deployment using registered service credentials and token-based sessions. Multi-user project ownership remains deferred. This report is a code audit and targeted regression verification, not live customer deployment certification.

## Findings fixed

| Finding | Impact | Correction |
|---|---|---|
| Ollama HTTP failures inherited the transport-error branch | requests HTTPError derives from OSError; 401, 403 and 404 could open the circuit and conceal the original credential or route problem | Explicit HTTP status takes precedence; only 429 and 5xx responses count as transient HTTP failures. Regression verifies rejected credentials and missing routes do not open the circuit. |
| Completed workflows kept polling | Every terminal run generated requests indefinitely while its panel remained mounted | Automatic refresh runs only for active states; manual inspection remains available. Regression verifies completed workflow handoff does not poll. |
| Recovery notice survived credential changes | A late response could display retained state under a different credential context | Credential changes clear the notice and invalidate outstanding response sequences. Regression verifies a late response cannot restore the old notice. |

## Existing architecture reviewed

Runtime catalog extension registers 26 roles, 44 allowlisted tools and four predefined workflows. Approved single-tool mutations use persisted workflows; read-only executions remain bounded. The model proposes commands; service contracts, allowlists and authorization govern dispatch. Ontology review validates evidence citations and rejects undeclared write/approval fields. Pausing and cancelling apply between tools and cannot undo dispatched writes.

See [Agent role mapping](AGENT_TOOL_MAPPING.md) for all role responsibilities and their profiling, quality, merge, graph and publication handoffs. The current customer does not require Entra. Local DT roles do not depend on the external DT gateway enablement flag.

## Verification and remaining work

Targeted regression suite: 36 backend tests and 32 frontend tests passed. Tests use mocked transport or isolated contracts where runtime dependencies are unavailable; they do not prove live PostgreSQL, APIM, MCP or reasoner behavior.

Production acceptance still requires customer-environment checks: restart and uncertain-write recovery with PostgreSQL; generation, embedding and structured-output capability checks against the actual APIM contract; end-to-end profiling and approved product publication; and mapping accuracy evaluation on representative customer evidence. Per-process Ollama admission is not a distributed capacity limit. MCP bindings require verified deployment registration. Structural evidence is not a formal ontology consistency proof. Existing frontend bundle-size warnings remain a performance follow-up.


## Demo-path stabilization follow-up

Fixed catalog pagination to retain each product version once when pages overlap, while retaining a visible completeness warning. Fixed QIF/AP242 mapping inspection to abort in-flight requests and clear evidence and agent reports when credentials change or the session expires. Updated QIF page test setup to supply its ontology context and verify authenticated artifact downloads rather than obsolete unauthenticated links. Updated the paused-workflow timing fixture to implement the compare-and-put contract used by production control storage.

Expanded backend verification: 53 tests passed across workflow recovery, session timing, service URL validation and Ollama admission contracts. These remain isolated tests; deployed database and APIM services were not exercised.

Full frontend regression: all 42 test files and 185 tests passed. Production frontend build passed, with existing chunk-size warnings. Navigation evidence remains mocked-service browser coverage; no live customer deployment certification is implied.


## Merge safety and executable demo preflight

Fixed RDF merge blank-node scope: identifiers are remapped per source while preserving connections within a source. Duplicate accounting uses RDF term serialization, preserving literal language/datatype distinctions. A regression executes the actual remapping function with isolated RDF-term doubles; a full RDFLib integration run remains required. Merge preview exposes its validation scope and formal-reasoning status; Ontology Mapper displays these limitations.

Run `infra/windows/test-depo-demo-readiness.ps1 -EnvFile .env.local` on the application VM. It reuses deployment readiness, temporary registered-session verification and bounded Ollama generation/embedding/proposal probes. Add `-Gateway` for the session routing check through configured gateway URLs. It neither merges nor publishes customer data. Follow it with a disposable-data rehearsal of reviewed merge, mapping publication, graph inspection, catalog consistency and restart recovery. The script has been syntax checked locally; customer endpoints have not been called here.

Updated isolated backend suite: 54 tests passed. Advanced semantic conflict resolution, formal ontology reasoning, live publication/recovery certification and distributed capacity management remain pending; these are not marked fixed by this change.


## Explicit semantic merge guards

Merge preview and application now reject explicit disjoint-class membership, incompatible object/data property declarations, direct sameAs/differentFrom contradictions, self-difference and explicit owl:Nothing instances. Apply rechecks the saved RDF, including older previews, before catalog registration. Matching names and different IRIs do not create automatic equivalence. Completed historical merges are not rewritten. Checks do not cover inferred contradictions, arbitrary OWL reasoning or engineering equivalence; full reasoner/customer evaluation remains outstanding.

Expanded isolated suite: 60 backend tests passed, including legacy preview publication rejection. RDF parser and live service integration remain unverified in this runtime.


## Merge retry and approval recovery

Governed merge now persists its original approver before registration and reuses that identity throughout a retry. A retained merge version is reused by immutable merged artifact identity, preventing additional snapshots when the final merge-result save or response fails. Merge operations remain serialized by the existing operation lock; generic manual version creation keeps its existing behavior.

Verification: 63 isolated backend tests passed, including retry after version failure, original-approver preservation and reuse of a persisted version. Live PostgreSQL failure injection and RDFLib integration remain required. This fix does not add automatic semantic equivalence resolution or full formal reasoning.


## System prompt alignment

All 26 runtime roles now carry a task-specific proposal policy. Base catalog prompts describe selecting the next service tool rather than returning task counts or results. DT extension attaches policies for its twelve roles. Native and structured proposal modes retain the same role and shared trust/approval constraints; native mode no longer overwrites the role prompt. Custom catalog prompts remain supported.

Shared policy treats user tasks, documents, tool descriptions and schemas as data; forbids invented required values, credentials, approval and execution claims; and distinguishes name matches from semantic equivalence. Server-side schema checks, allowlists and authorization remain the enforcement boundary. Missing inputs fail validation; a conversational clarification interface is not implemented by this change.

Verification: 65 backend tests passed, including all-role policy coverage, custom policy preservation and the actual native proposal request retaining its role instructions. This is not an empirical Ollama instruction-following or prompt-injection benchmark; those evaluations remain pending against the customer model.


Architecture failure-boundary follow-up (2026-10-08): both execution modes reject nested credential/header fields before retaining workflow inputs; compensated runs are excluded in the bounded worker candidate query; worker grant verification is offloaded from the event loop; HTTP 503 authority failures retain the existing grant for retry within its original deadline. Ollama circuit generations prevent older successes from clearing a newer cooldown and permit one recovery probe. Regression coverage: test_architecture_failure_boundaries.py. Live PostgreSQL/APIM verification remains outstanding.

Ollama integration follow-up (2026-10-08): legacy generation now requires a complete, error-free response; legacy generation and model-list probes share bounded decoded-body readers and close responses; document processing honors the explicit provider and wraps only an actually selected Ollama client; legacy answers expose null confidence with not_calibrated status. Selected transport/health/architecture regressions passed; live APIM and full LangChain integration remain unverified.

Service-boundary follow-up (2026-10-08): product content rejects nested credential fields; package creation, hashing, product registry calls and operation-lock acquisition are offloaded; reconciliation distinguishes delivered revocations and validates integer limits; catalog reads query only the requested product; pipeline publication and receipt clients disable environment proxies. Live database concurrency and full integration tests remain outstanding; pytest-based product contract suites could not load in the bundled runtime.

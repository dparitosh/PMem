# Agentic orchestration and knowledge graph review

The findings below record the pre-fix audit baseline. See the remediation section for subsequent code changes.

Date: 2026-10-21. Scope: the four requested capabilities, the installed desktop deployment, and the corresponding source, recovery, ingestion and memory tests. This review does not change application code, credentials, memory enablement, approvals or published graphs.

## Assessment

PMem implements governed agent workflows with executable tools and durable state. The reviewed ontology/companion paths do not implement the full adaptive planning and failure-learning behavior described in the request. A successful knowledge graph publication establishes graph execution, not general agent autonomy.

| Requested capability | Observed implementation | Assessment |
| --- | --- | --- |
| Context ingestion / perception | Format-specific schema/instance parsers; PDF native text and optional OCR; Word, PowerPoint, HTML and text extraction; chunks, validated embeddings and semantic candidates | Implemented in part. Word tables are silently omitted; advertised layout analysis is not executed by this document processor. |
| Reasoning and planning | Predefined catalog workflows, deterministic ontology intake/review/mapping, optional model-generated review questions and a single allowlisted tool proposal | Fixed workflow planning and bounded recommendations exist. General goal decomposition, execution-driven replanning and learned fallback selection are missing from these paths. |
| Tool execution | Allowlisted OpenAPI/MCP contracts, schema checks, credential propagation, operation deadlines, background jobs, step bindings, publication receipts | Substantial implementation. Uncertain writes are correctly held for verification rather than blindly replayed. |
| State and memory | PostgreSQL runs, inputs, step results, pending writes, worker claims and conversation history; optional scoped Neo4j messages/traces/mapping facts | Durable execution state exists. Graph memory is disabled in this deployment. Failure traces are not retrieved into a shared planning scratchpad. |

## Findings, ordered by impact

### F1 â€” High: Word table requirements disappear before semantic processing

`backend/Services/document_processor.py:323` reads only `document.paragraphs`. Tables are not traversed. A real DOCX fixture containing a paragraph plus a requirement table extracted only `Motor requirements`: both `REQ-TABLE-001` and `Rated torque shall be 45 Nm` were absent. The returned text can still proceed to chunking, indexing and candidate generation, so downstream retrieval cannot recover this evidence.

Remediation: extract paragraphs and tables in document order, including nested tables where supported; retain table/cell source locations. Add completeness checks and a regression with requirements present only in a table. Apply similar coverage checks to PowerPoint tables/grouped shapes. The unstructured plan's `layout_analyzer` description must match implemented extraction capability or explicitly declare its limitation.

### F2 â€” High: ontology review and planning do not share one immutable snapshot

`backend/agentic_service/ontology_orchestrator.py:298` inspects the artifact for intake/review; line 302 calls `bridge_plan`, whose artifact path inspects again at line 354. The existing `test_ontology_orchestrator_reuses_one_artifact_snapshot` fails because inspection occurs twice. Optional digest inputs are not supplied by this orchestrator call. A source change between reads can produce a review and mapping plan based on different evidence. With an ontology ID, planning can also default to the graph while intake inspects the artifact; those sources must be explicitly distinguished and bound.

Remediation: pass the inspected immutable summary into planning, or require and verify an explicit artifact/publication digest across stages. Preserve source identity and scope in every result. Re-run the existing snapshot regression and a source-change test.

### F3 â€” Capability gap: fixed sequences do not provide adaptive goal planning

`router.py:572` builds workflow plans from catalog steps; execution iterates those steps at line 981. `ontology_orchestrator.py:286` sequences deterministic roles. `local_llm.py:201` produces one allowlisted tool proposal, and `router.py:526` retains it as a proposal requiring an explicit execution request. This is useful orchestration, but it does not automatically decompose an arbitrary business goal into a persisted task graph, evaluate progress, and revise the plan after tool observations.

Remediation: add a bounded goal/plan/observe/replan controller over approved tools, with explicit success criteria, step dependencies, budgets, persisted plan revisions and evidence references. Replanning must stay within the original authorization and available contracts. Generating or executing arbitrary replacement code is not necessary to meet this requirement.

### F4 â€” Capability gap: retained failure evidence is not failure-learning memory

`transport_auth.py:27` retries explicitly non-mutating tools on server errors using the same tool. `durable_workflows.py:115` can recover stale read-only execution while retaining the original deadline. `recovery.py:27` deliberately blocks uncertain mutations pending reconciliation. These are valuable recovery mechanisms; they do not select a different endpoint or learn a recovery strategy.

`AgentMemoryService.record_reasoning_trace` stores optional traces, but `recent_context` at line 367 retrieves messages only and returns an empty facts list. Mapping facts have their own reuse path and are revalidated against the current instance. The companion uses conversation history for follow-up retrieval, not a shared error/observation/plan scratchpad. The deployed companion also differs from the older `backend/agent/chat.py` LangGraph tool loop: the frontend routes to the agentic service's evidence-search companion. The legacy loop cannot be counted as proof of autonomy in that deployed path.

Remediation: retain structured failure observations with run/step/tool IDs, sanitized error category, attempted parameters, verified outcome and expiry. Retrieve relevant observations before choosing a bounded alternative from registered compatible read tools. For writes, verify the downstream receipt before retry or compensation. Add tests for transient reads, schema errors, exhausted alternatives and uncertain writes.

### F5 â€” Deployment gap: optional graph memory is disabled; cloud inference is unverified

The live memory endpoint returned HTTP 200 with `enabled=false`, `status=disabled`. `AGENTIC_EXECUTION_MODE=worker`, `USE_LLM=openai`, `ONTOLOGY_AGENT_LLM_ENABLED=true` and `COMPANION_LLM_ENABLED=true` are configured. The live LLM endpoint reported `generation_unverified` for `gpt-4.1-mini`; this is configuration evidence, not an inference success or failure. No paid inference was invoked during this audit. Historical HTTP 429 results are not evidence of the provider's current state.

PostgreSQL workflow/conversation persistence still operates independently of optional Neo4j memory. Enabling graph memory alone will not implement F3/F4. Make memory health and capability status visible to users, provision scope/constraints/retention deliberately, and verify write/read/restart/isolation behavior before claiming shared graph memory.

### F6 â€” Coverage limit: bounded evidence can omit relevant engineering terms

Artifact inspection indexes at most 500 terms of each kind (`ontology_orchestrator.py:83`). Instance metadata samples the first 1,000 rows (line 158), without returning a sampling flag from that helper. Graph planning keeps the first 2,000 terms (line 333). Term-index truncation is disclosed and holds the result for review; the bounds are therefore not themselves unsafe. However, a relevant AP242/QIF class or a rare instance type outside these prefixes can be missed, and the first-row sampling limit is not communicated in its output.

Remediation: retrieve relevant candidates by kind, namespace, label, definition and property neighborhood before bounded selection; page through source evidence where completeness is required. Return inspected/total counts and explicit sampling flags. Do not interpret unmatched sampled items as proof that no ontology concept exists.

### F7 â€” Verification/UI gap: test isolation and recovery explanations need improvement

The initial combined suite produced 89 passes and 13 failures. Isolated execution of 13 suites produced 109 passes and 5 failures. One failure demonstrates F2. Two companion tests lack PostgreSQL session fixtures and fail before exercising the intended behavior. Two data-agent tests use stale extracted-function fixtures: one lacks `_work`, another lacks `workflow_error`. Eight worker failures from the combined run disappear in isolation; the isolated durable-worker suite passes all 14 tests. These harness defects prevent treating the aggregate suite as a reliable release gate and must not be mislabeled as eight production worker failures.

`frontend/src/Components/AgentControlPanel.js:195` presents run status and completed-step counts; lines 196/202 expose detailed execution evidence as JSON. Users still need a concise view of the goal, current plan, grounded evidence, agent decision, failed attempt, retry/recovery decision and verification result. Keep execution state, inferred recommendations, approval and verified graph writes distinct.

## Knowledge graph checks

Read-only search against the newly published AP242/QIF merge returned HTTP 200 and ten `Characteristic` matches, all scoped to `merged_1792552054860_a98be4b2d41448a6`. This proves scoped retrieval on that query, not comprehensive semantic search quality. The prior independently verified publication receipt and live metrics agreed on 76,202 resources and 212,377 relationships, with 8,911 explicitly declared classes. The receipt digest matches the validated 372,068-statement artifact. Literal values are stored as properties, so RDF statement totals must not be compared directly with graph edge counts.

The companion currently calls graph search with bounded lexical evidence (`companion.py:42`), then optionally summarizes cited results. It is not, by that code alone, a multi-hop planning agent or complete formal reasoner. The merge service's SHACL/OWL-RL evidence remains separate from graph projection/retrieval.

## Evidence and limitations

Evidence directory: `outputs/enterprise-audit-2026-10-20/agent-orchestration-review/` in the workspace parent of this repository. It contains per-suite logs, isolated test results, aggregate classification, live read checks, and the DOCX fixture/reproduction result. The publication proof is retained separately as `ap242-qif-publication-verified-20261021.json`.

The seven principal audited modules were hash-compared with the installation and match. Tests use fixtures for downstream execution and memory; they do not establish every real-provider, restart, concurrency or full-document ingestion scenario. Live checks were read-only; no new graph data was ingested and no services were restarted. This audit identifies required changes; it does not claim those changes are deployed.

Recommended order: repair perception completeness and snapshot consistency first; repair the release test harness next; then implement a persisted bounded planner and failure-memory retrieval, configure/verify optional memory, and expose the resulting evidence in the UI.


## Remediation implemented after the audit

- F1: Word extraction now walks paragraphs, table rows/cells, nested tables and content controls in XML source order. PowerPoint extraction includes tables and grouped shapes. Source-location markers identify table cells. The unstructured plan explicitly discloses PDF visual-layout limitations instead of advertising an unexecuted layout analyzer.
- F2: ontology orchestration passes its inspected summary directly into bridge planning. Intake, review and planning use the same artifact snapshot and identify it as retained RDF.
- F3/F4: a separate bounded read-goal controller now persists decomposition, plan revisions, failed/successful observations and cited completion in PostgreSQL. It reuses the registered agent tools and schemas, supports failure-driven alternative read actions, preserves source scope and deadlines, fences competing/cancelled executors, and is served by the existing durable worker. HTTP authorization rejections block the goal. Writes remain excluded. This is an implemented controller with fixture-based model/transport tests, not a claim that unrestricted autonomous code repair or semantic equivalence inference has been added.
- F5: goal scratchpad persistence is independent of optional Neo4j conversation memory; UI and installation guidance identify the storage backend and selected model. Optional graph memory is not silently enabled. Live cloud inference still needs separate verification after deployment; this update does not remedy provider quota.
- F6: artifact term matching uses all inspected terms; first-1,000-row sampling has been removed. The extra first-2,000-term graph-planning slice is removed within the graph service's existing bounded lookup contract. Graph lookups above that contract still fail explicitly and require narrower scope; they do not silently claim complete coverage. LLM review prioritizes candidate evidence within its prompt budget.
- F7: companion tests now provide isolated session, result and telemetry stores; stale extracted-function fixtures were updated. Durable-worker fixtures explicitly replace the package-level router binding and goal queue dependency, preventing test-order contamination. The UI provides a read-goal plan/observation/conclusion view instead of requiring users to interpret raw trace JSON.

New routes are POST `/api/v1/agents/{agent_id}/goals`, GET `/api/v1/goals/{run_id}`, and POST `/api/v1/goals/{run_id}/cancel`. They enforce read identity and retained ownership. Schema discovery failures are retained rather than dispatched. Model provider/model/recipient and tool contract bindings are checked before continuing a retained goal. Credential rotation/revocation is verified through existing service-grant checks. The worker fairly schedules goals and workflows, with per-family queue failures isolated.

Deployment is separate from source verification: the agent's Windows CIM process query returns Access denied, so it cannot safely stop/restart the installed services. The updated combined package is intended for the existing administrator-run Setup-DEPO launcher. Published ontology data is not changed by these code changes. A live end-user investigation must be tested after deployment with an available model; fixture tests do not substitute for that live check.

Remediation validation: broad backend suite 137 passed; final read-goal boundary suite 22 passed (including two additional authorization-outage/rejection cases; 139 unique backend tests exercised across these runs). Frontend suites 24 passed. Production build passed on Node.js 24 using Vite’s runner config loader in this restricted workspace. The original DOCX reproduction now retains both REQ-TABLE-001 and 45 Nm with table-cell locations. New OpenAPI operations advertise GRAPH_READ_TOKEN without approval fields. Validation evidence is in `remediation-validation.json` and the retained JUnit XML files beside the original audit evidence. No live model inference or deployed end-user test is claimed before applying the package.

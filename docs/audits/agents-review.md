# Application agents audit — 2026-10-01

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Scope: standalone agent control-plane routing, tool manifest, transport credentials,
workflow execution, companion retrieval, ontology orchestration, graph memory and
frontend agent client. This is a code audit, not a certification of all agents or a
live customer deployment. Existing OData/OpenAPI changes remain separate.

## Remediation

A01–A08 now have code corrections: segment-constrained tool paths, validated
references, terminal workflow states, bounded execution, supported frontend
contracts, failure telemetry, offline JSON-LD contexts, scoped companion memory,
periodic retention and direct-agent observations. Companion sessions are durable,
credential-owned and expire by both idle time and fixed lifetime. Failed workflow
responses expose the run ID; post-crash reads use deadline projections without
overwriting concurrently completed records. Uncertain writes require reconciliation.

A09 is resolved through an explicit synchronous job/completed-response SSE
contract; this release does not claim progressive model generation or background
chat execution. Multipart execution additionally preserves server-verified approval
fields. No customer database/Neo4j or real LLM endpoint was exercised.

Validation: 95 backend regression tests, six frontend agent/chat tests and the
production frontend build passed. The final authorization-order adjustment was
also verified by rerunning the 46 affected lifecycle/security tests. Temporary
dependencies used the pinned FastAPI/Pydantic versions with test providers; the
complete production dependency lock and customer connectivity were not tested.
The locked frontend install initially reported 12 dependency vulnerabilities
(four moderate, eight high). A subsequent non-major lockfile update removed ten
affected packages from the advisory report. The current audit reports zero
production dependency vulnerabilities and two moderate development-only findings
in Vitest/@vitest/mocker. Their proposed fix requires a major Vitest upgrade.
The updated lockfile passed the full frontend suite (108 tests in 26 files) and
the production build. `package.json` version ranges were not changed and no
`--force` upgrade was applied. The current machine-readable advisory evidence is
saved in `frontend-dependency-audit.json` beside this report.

## Original findings (before remediation)

| ID | Priority | Location | Trigger and impact | Correction |
| --- | --- | --- | --- | --- |
| A01 | P1 | backend/agentic_service/router.py:50 | `_render` inserts input directly into URL paths. An ontology_id of `../merges/preview?ignored=` produces `/ontologies/../merges/preview?ignored=/transition`. The declared allowlisted tool no longer guarantees the downstream route; server-generated service credentials accompany the request. | Encode each path segment, reject traversal/control characters and verify the rendered path matches the declared operation. Preserve explicit path converters only where intended. |
| A02 | P2 | backend/agentic_service/router.py:399 | Input reference resolution and retry conversion happen after saving a running record but outside the per-step failure handler. An invalid reference returns 422 through the outer handler without finishing the workflow or telemetry. Unexpected failures and request cancellation also have no terminal-state handler. | Validate inputs first where possible; wrap execution in terminal-state handling, record failed/cancelled steps and finish telemetry. Durable recovery should distinguish interruptions from confirmed failures. |
| A03 | P2 | backend/agentic_service/router.py:302–314 | `$steps.0.result.id` resolves to the most recent result and `$steps.-1.result.id` resolves an earlier result through Python negative indexing. The documented whole-result form `$steps.1.result` is rejected. | Require positive one-based indices that name completed prior steps; allow the documented whole result; validate field/list access explicitly. |
| A04 | P2 | frontend/src/config.js:409–411; frontend/src/services/agenticApi.js:32–43 | Client defaults use `/openapi/import`, `/agents/{agent_name}/run` and `/workflows/run`. Those POST routes are absent from the standalone agent router. Actual execution uses `/runs` with agent_id/tool_id and `/workflow-runs`. The workflow wrapper also cannot supply approval fields or step_inputs. No current page call sites were found for these two execution helpers, so this is a latent integration defect rather than proof of a currently broken page. | Match supported routes and payloads, accept explicit approval/options and step inputs. Remove or deliberately implement OpenAPI import; never turn imported operations into executable tools without governance. |
| A05 | P2 | backend/agentic_service/router.py:213–235 | Chat telemetry starts before downstream credentials are resolved, but only RuntimeError finishes a failed record. Missing GRAPH_READ_TOKEN raises HTTPException; malformed JSON/response fields can raise ValueError/TypeError. These leave running telemetry or produce unhandled errors. | Finish observations on every failure path; validate downstream response shapes and preserve safe status/error messages. |
| A06 | P2 | backend/agentic_service/ontology_orchestrator.py:40–42 | Approved local files are passed directly to RDFLib with inferred format. JSON-LD may resolve remote contexts, extending processing outside the approved local-file boundary. `.jsonld` is accepted by the extension guard without an explicit format mapping. | Explicitly map accepted extensions to RDF formats and enforce a local/offline JSON-LD context policy. Test blocked network contexts and supported JSON-LD inputs. External fetch exploitability was not exercised in this audit. |
| A07 | P2 gap | backend/Services/agent_memory_service.py:351; backend/agentic_service/router.py:213 | Retention pruning is defined but has no production call site found. The standalone companion does not read/write AgentMemoryService; session_id is returned but not used by its retrieval. Enabling AGENT_MEMORY_ENABLED therefore does not supply conversational memory to this path. | Schedule scoped retention and explicitly integrate bounded session memory, or document this companion as stateless. Keep user/tenant authorization separate from a deployment-wide memory scope. |
| A08 | P2 gap | backend/agentic_service/router.py:335; backend/agentic_service/ontology_orchestrator.py:229 | Direct tool runs and direct ontology agent requests do not produce the workflow tool spans/agent observations. Telemetry exists for workflows and companion requests, but does not cover all agent entry points. | Instrument each public execution boundary with one observation and bounded content-free spans, preventing duplicate counting for nested workflow calls. |
| A09 | P3 gap | backend/agentic_service/router.py:238–243,265–274 | Chat jobs finish retrieval synchronously before returning 202; streaming waits for the complete response and then emits it as one token event. The names/capability flags imply asynchronous or incremental behavior that these paths do not provide. | Return an honest synchronous contract or use durable jobs and real progressive streaming, with explicit frontend timeout/cancellation behavior. |

## Reproduction evidence

Executed the actual `_lookup` and `_render` function bodies extracted through AST
with Python, without importing application dependencies or contacting services:

```text
Completed results: first, second
$steps.0.result.id  => second
$steps.-1.result.id => first
$steps.1.result    => ValueError
ontology_id='../merges/preview?ignored='
rendered path => /ontologies/../merges/preview?ignored=/transition
```

Frontend defaults were compared with the standalone router declarations. Repository
search found no runtime caller for `prune_expired_sessions`. Failure-state findings
follow the placement of initialization, persistence and exception handlers; no
live PostgreSQL failure injection was performed.

## Controls present

- Tool execution checks the agent's tool allowlist and approval requirement.
- Mutating tools require a configured downstream approval contract.
- Token-mode transport chooses server-side service credentials; caller-provided
  approval fields are replaced before dispatch.
- Uncertain mutating failures are not automatically retried.
- Ontology agents produce review plans; publication uses separate approval paths.
- Companion retrieval fails closed on HTTP retrieval failures and returns graph
  evidence rather than an unsupported generated answer.

The catalog is deterministic tool orchestration with optional review-only LLM
suggestions. It is not an autonomous self-learning agent implementation. The initial
audit installed no packages or performed live writes. Remediation was subsequently
tested with temporary dependencies and mocked persistence/transports; no live
customer writes were performed.

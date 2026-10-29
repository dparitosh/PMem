# L0–L4 execution, autonomy and memory audit

**Remediation follow-up:** see [L0–L4 fixes and storage ownership](l0-l4-remediation-2026-10-28.md). Findings below describe the audited pre-fix state and are preserved as historical evidence.

Date: 2026-10-28. Scope: the current working tree and read-only inspection of the running local installation. This is a cross-layer audit, not a claim that every code path, customer deployment or production workload has been qualified. Production code, credentials, feature flags and business data were not modified. No live LLM calls or graph publication were performed.

## Conclusion

Bounded autonomous investigation, durable workflow execution and optional approved-mapping reuse exist in code. The advertised process is not yet a complete, reliable self-learning loop. Four runtime integrity findings were reproduced, including two carried forward from the Governor/Steward review. Release preflight and test-maintenance gaps were also confirmed. Automatic semantic-publication and selected-record investigation guarantees should not be released without correcting these findings and preserving the reproductions as regressions.

## Hierarchy and traceability

| Layer | Activities / runtime ownership | Audit result |
|---|---|---|
| **L0.1 Business intent** | Import engineering sources, establish meaning, investigate decisions and reuse governed knowledge. | Recorded knowledge can support answers. No application-wide measured-outcome → validated lesson → controlled model/policy improvement loop was found. Do not describe history persistence as continuous model training. |
| **L1.1–L1.2 Acquire and prepare** | Import workflow selection, file/dependency handling, conversion, task persistence, validation and recoverable status. | Existing tests passed for engineering workflows, remote schema dependencies, schema upload APIs, snapshot retry, commit integrity and status recovery. Real customer-file ingestion and every format/size combination were not exercised in this review. |
| **L1.3 / L2.3.4–L2.3.5 Govern and connect** | Governor-labelled previews, Steward-labelled evaluations, instance linking and ontology union/application. | Tool/permission boundaries exist. GS-01 and GS-02 still allow adverse publication decisions in the isolated harness. OWL-DL execution is conditional for merge API callers, not a universal gate. |
| **L1.4 / L2.4.1–L2.4.3 Investigate** | Contextual graph, Recommendations, Where Used and Knowledge Companion. | Source identity matters independently of service availability. AL-01 and AL-02 show missing run/product context binding; ontology/node scope checks do not cover those record types. |
| **L1.5 / L2.5.1–L2.5.4 Reuse and deliver** | Data Flow outputs, product contracts/packages, approved semantic releases and catalog delivery. | Pipeline/product integrity tests passed. Dynamic read-goal selection can switch the selected run/product because its scope is not pinned. The earlier live product list contained zero published products; populated customer publication remains unqualified. |
| **L3 Activity / agent interaction** | Plan → registered read → observation → revised plan; Governor proposal → Steward assessment → authorized application; scoped conversation follow-ups and mapping-memory retrieval. | The model proposes; deterministic controller code enforces execution. The main bridge workflows are fixed catalog steps, not necessarily two LLMs conversing. Memory reuse remains review evidence and carries an explicit validation warning. |
| **L4 Execution / persistence** | UI state and API contracts, worker grants/deadlines, transport/auth/CORS, Semantica, OWLAPI/HermiT, PostgreSQL, graph transactions, receipts and release validation. | Read-only live health/auth/CORS/schema checks passed. Missing semantic helper modules can pass the code-completeness guard. Two deployment tests currently fail. JVM isolation is not a total RDF-preparation deadline or a full operating-system sandbox. |

### Concrete activity-to-code path

`L0.1 → L1.3 → L2.3.4 Instance linking → L3.B4 Steward assessment → BridgeJobs.evaluate_policy → current semantic support / deterministic validation → retained preview and policy findings → authorized BridgeJobs.publish → graph transaction and receipt`.

`L0.1 → L1.4 → L2.4.2 Investigation → L3.A2–A5 Plan/read/observe/replan → goal_routes worker → goal_runner.validate_action / drive → registered owning-service API → PostgreSQL observations → bounded completion`.

The first chain currently has the GS findings; the second has AL-01 for run/product scope. A diagram showing these chains is not evidence that their boundary checks are complete.

## Confirmed runtime findings

### AL-01 — P1: autonomous read goals do not preserve selected run/product identity

**Sources:** `backend/agentic_service/goal_runner.py:18`, `:39`, `:124`; `backend/agentic_service/context_envelope.py:27`; `backend/agentic_service/goal_routes.py:131` onward.

**Root cause:** `SCOPE_KEYS` omits `run_id` and `product_id`. `selected_scope` drops those IDs, leaving no corresponding constraint for action validation. The context envelope projects the same incomplete scope. The original context/page metadata can contain a selected ID, but the controller does not enforce it for these read inputs.

**Reproduction:** create a read-goal context selecting run `selected-A`, derive its scope, then submit `pipeline.run.evidence` for `other-B`. Repeat with a selected product and `data.catalog.product`. Both proposals are accepted. An envelope built for run A also verifies when given context for run B because both project to the same empty scope.

**Impact:** an autonomous investigation can read and discuss a different authorized run/product from the user-selected record. This is a decision-integrity/scope defect, not a demonstrated cross-user authorization bypass. The reproduction used adversarial proposals directly; a live LLM was not asked to make this choice.

**Recommended fix:** add explicit run/product identity contracts to goal scope, envelope, relevant read tools and completion binding. Bind immutable package/run revisions where available. Check resolved identifiers after reading, not just requested input strings. Test changed selections, stale resume, retries and conflicting record identities without globally preventing unscoped discovery tools.

### AL-02 — P2: Companion drops run/product selection and can inherit another record's context

**Sources:** `backend/agentic_service/chat_request.py:6`; `backend/agentic_service/context_scope.py:3`; `backend/agentic_service/companion_memory.py:6`; `frontend/src/Components/Chatbot.js:43`, `:112`, `:195`.

**Root cause:** the chat request and shared scope projection contain ontology, prefix, page and node ID only. Run/product IDs are absent from the frontend scope reset/history/request construction. Extra run/product fields supplied to `ChatContext` are ignored by its current Pydantic defaults.

**Reproduction:** parse `{page: data-flow, run_id: selected-A}` through `ChatContext`; the run ID disappears. Compare contexts for A and B; `same_companion_scope` returns true. Feed an anaphoric follow-up, “What failed in it?”, with a previous turn about run A and current context B; retrieval inherits the run-A text.

**Impact:** switching selected Data Flow runs or products does not provide the Companion with a reliable record boundary, so follow-up retrieval can concern the previous record. No cross-user data access was demonstrated.

**Recommended fix:** carry run/product IDs end to end: UI props, conversation key/reset, history filtering, typed request, retained turns, retrieval API and citations. Reject unsupported scope fields rather than silently dropping them when they express a selection. Fetch the selected owning-service record instead of using only a page-wide list.

### GS-01 — P1: an omitted unsatisfiable target passes the conflict guard

**Sources:** `infra/reasoner/src/main/java/org/depo/reasoner/Main.java:58-59`; `backend/depo_platform/semantic_support.py:26`, `:35`; `backend/agentic_service/bridge_jobs.py:99`, `:192`.

**Reconfirmed:** real HermiT identified 205 unsatisfiable classes; only 200 IRIs were returned. A candidate pointing to one of the five omitted classes passed `target_conflict`, was accepted and reached the fake publisher. Absence from a bounded sample was interpreted as absence of a target conflict. Live graph writes: zero.

**Fix:** preserve completeness metadata and perform an exact, version-bound selected-target satisfiability check whenever the returned list cannot establish membership. Hold the affected candidate pending that check; do not blanket-hold every unrelated class. Cover 199/200/201/205-class boundaries and both manual and automatic writes.

### GS-02 — P1 policy/reliability gap: an evidence outage clears an established hold

**Sources:** `backend/depo_platform/semantic_support.py:42` onward; `backend/agentic_service/bridge_jobs.py:77`, `:124`, `:192`.

**Reconfirmed:** real executed inconsistent evidence first produced a held assessment. With the same preview/source snapshot, a simulated evidence outage subsequently returned unknown. Automatic publication then reached the fake publisher. Live graph writes: zero.

**Fix:** retain established per-source/per-target holds, bound to artifact/foundation/policy revisions. An outage must not imply that a known conflict was resolved. Require a verified resolving assessment or a defined authorized/audited exception. Keep the intentional initial-unknown compatibility policy separate from loss of an established hold.

Full GS reproductions and policy qualifications: [Governor / Steward boundary review](governor-steward-boundary-review-2026-10-28.md).

## Deployment and test findings

### AL-03 — P2: code preflight accepts missing semantic integration helpers

**Source:** `backend/depo_platform/release_code_check.py:11` (`REQUIRED_MODULES`).

**Reproduction:** build a disposable fixture satisfying every required module and converter signature, without `backend/depo_platform/semantic_support.py` or `backend/ontology_service/semantic_merge.py`. `check(root)` reports `status: ok`.

**Root cause / impact:** the new helpers are not in the explicit required-module set. A fingerprint hashes present files but does not independently establish that every required lazy import is present. This confirms a guard gap; the fixture is not a complete live-startup reproduction. Missing helpers can fail semantic reads or requested union checks when those paths are invoked.

**Fix:** require the new helpers and test deletion of each before release/startup. Preserve service-specific dependency checks and complete packaging; avoid treating an internally matching fingerprint as proof of dependency closure.

### TA-01 — P2: schema release-contract test is stale

**Source:** `backend/tests/test_schema_upgrade_safety.py:78`.

The test expects 10 indexes; `EXPECTED_INDEXES` and live verification require 12. The test fails `12 != 10`. Update the independent release expectation and preferably assert the expected index identities and definitions. Do not reduce runtime requirements to satisfy the old fixture. No live database migration failure was observed.

### TA-02 — P3: release-fingerprint fixture recreates an existing directory

**Source:** `backend/tests/test_release_code_check.py:41`.

The fixture already creates `backend/ontology_service` while generating required foundation modules. The test then calls `source.mkdir()` without `exist_ok`, failing before its source-change assertion. Correct the fixture setup while preserving the assertion that application source changes alter the fingerprint. This is a test defect, not proof that runtime fingerprinting failed.

## Autonomy and learning: verified scope

- **Implemented:** bounded read-goal planning, allowed read-tool execution, retained observations, alternative-read recovery, missing-input/access/budget termination, durable worker state and authorized fixed workflows. Tests cover these controller boundaries with stubbed model proposals.
- **Implemented conditionally:** graph-backed conversation/mapping memory. Reused mappings are checked against current target identity/type and validation; memory reuse adds a warning, keeping it distinct from automatic approval (`backend/Services/semantic_workflow_service.py:725`).
- **Current local flags:** `AGENT_MEMORY_ENABLED=false`, `COMPANION_LLM_ENABLED=false`, worker execution enabled. The memory status API confirms disabled/not-verified graph memory. These settings were not changed. PostgreSQL workflow state remains available even when optional graph memory is disabled.
- **Not established:** application-wide outcome measurement, automatic validated lesson promotion, online matching-threshold optimization or model retraining. `dt_bindings.py:15` binds `self_learning_review` to read-only pipeline evidence; its name does not establish a training loop.
- **Live-model qualification:** dynamic autonomous tool selection, quality of model-generated reasoning and non-deterministic planning were not live-tested because LLM calls remain excluded. The Companion summarization flag alone does not prove every agent model is disabled or unavailable.

## Fresh executed coverage

| Evidence | Result | Boundary |
|---|---|---|
| `outputs/l0-l4-layer-audit.xml` | **354 passed**, 21 deprecation warnings | Selected backend import/dependency, persistence, worker/concurrency, memory, session, reasoning, recommendation, product/pipeline and OSLC/JSON-LD contracts. Isolated stores/providers except local real reasoning. |
| Frontend Vitest run | **101 passed**, 13 files | Import state, task polling, API sessions, access boundary, read-goal controls, recovery, TaskProgress, Recommendations, Data Products and Data Flow. React test API deprecation warnings remain. |
| `outputs/l0-l4-deployment-audit.xml` | **28 passed, 2 failed** | The two failures are TA-01 and TA-02. They were not suppressed, marked as passing or fixed during this audit. |
| `outputs/l0-l4-context-audit.json` | AL-01 / AL-02 reproduced | Pure action/envelope/request/scope functions; no HTTP, database or model calls. |
| `outputs/governor-steward-boundary-audit.json` | GS-01 / GS-02 reproduced | Executed local OWLAPI/HermiT with in-memory records and a fake graph publisher; zero live writes. |
| `outputs/l0-l4-release-preflight-probe.json` | AL-03 reproduced | Disposable workspace-only release fixture. |
| `outputs/l0-l4-live-layer-audit.json` | Local live read checks succeeded | No changed flags, LLM probes, publication or data deletion. |

The audit probes demonstrate uncovered negative cases even though the existing test groups largely pass. Counts from previous reviews overlap and must not be added to these results as unique coverage. None of the above is a full repository test run or proof of all customer behaviors.

## Live service, authorization and database observations

- Ontology, graph, pipeline and memory endpoints returned HTTP 200 with the configured reader credential. Graph-health latency in this sample was approximately 2 seconds; throughput and worst-case latency were not qualified.
- Anonymous ontology listing returned 403.
- Allowed loopback browser-origin CORS preflight returned 200 with the expected allow-origin. An untrusted origin returned 400 without an allow-origin grant.
- PostgreSQL release verification passed all 13 migration versions, 12 expected indexes and 22 expected constraints.
- Required graph index/constraint definitions verified; 6 required performance indexes passed, with 75 total indexes and 5 total constraints observed. Observed totals do not mean every index was workload-optimized.
- Remote customer/APIM routing, high-load DB/query plans, Windows antivirus/ACL behavior on the actual customer host, populated product publication and complete large-model offline import closures remain unqualified by these local checks.

## Required remediation order

1. Fix GS-01 and GS-02 before claiming reliable automated semantic-conflict protection.
2. Fix AL-01 and AL-02 end to end before claiming selected-run/product autonomous or conversational grounding.
3. Close AL-03 and repair TA-01/TA-02 so customer release checks are complete and green.
4. Add the new negative probes as durable regression cases, including source changes, restart, auth rejection, evidence truncation and outage/reconnect transitions.
5. Define visible capability readiness and business acceptance measures. If self-learning is a product requirement, implement the measured-outcome/validated-lesson/promotion loop as a separate governed capability; do not simply enable memory and relabel it training.

No production fixes, automatic memory enablement, model training or release approval are claimed in this audit.

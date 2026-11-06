# Application workflow review — 2026-10-29

Follow-up: [implemented fixes and validation](workflow-fixes-2026-10-29.md). The findings below preserve the pre-fix audit; the two expected failures have since become normal regression tests.

## Result and evidence boundary

The backend consolidation is ahead of parts of the UI. Do not treat this review as a customer release certificate. No production workflow code was changed during this audit. Added expected-failure audit probes explicitly document two unfixed defects.

Executed 123 existing frontend tests across 14 files and 118 backend tests across 10 files; all passed. Two additional `test.fails` probes reproduced the defects below. Their passing result means the desired behavior is currently broken, not fixed. Live browser review covered Import, retained job output, Data Flow and its approval/publication settings. No new customer records were imported, approved, replayed or published; no LLM calls were made. Full live execution of every branch, provider, network failure and customer deployment is not established.

## Workflow inventory and ownership

| Entry / workflow | Owner and durable output | Review conclusion |
|---|---|---|
| Instance import | Ingestion task; governed engineering inputs also create pipeline run manifests | Two execution routes still share overly generic stage descriptions; source import and semantic publication must remain distinct. |
| Create ontology | Engineering conversion, ontology catalog, publication worker | Registration, approval and graph publication remain distinct. Existing publication receipt tests pass. |
| Unstructured document pipeline | Retained documents/chunks, enrichment and retrieval evidence | Model/embedding availability and actual retrieval-index completion need provider-specific live acceptance; catalog capability labels alone are insufficient. |
| ArchiMate import | Ingestion process projection | Separate process model route exists; end-to-end re-import/traversal not rerun in this audit. |
| Instance alignment | Bridge preview/publication jobs; Governor → Steward → Governor | Existing recovery and boundary regressions pass. Retained preview, validation, authorization and publication are different states. |
| Ontology merge | Artifact comparison plus governed merge preview / registered union | Two entry paths exist. Legacy comparison report must not be mistaken for a governed union or publication. |
| Ontology validation | Retained syntax/SHACL/OWL-RL report; separate bounded OWL-DL runtime | Generic validation workflow is not the same scope as the newer OWL-DL workbench. Scope must be explicit. |
| Data dictionary | Retained report | Catalog stages say “Publish dictionary” although the handler writes a report. |
| Taxonomy generation | Retained hierarchy report | Catalog promises clustering, synonyms and rejected terms; current handler primarily exports asserted taxonomy. |
| Graph chunks | Retained chunk artifacts/manifest | Correctly identifies export rather than creation of a retrieval index. |
| Data jobs: execute/replay/schedule/approve/disable | Pipeline job definitions, durable runs and worker leases | Definition action has a synchronous lock; direct replay/publication do not. Session invalidation is incomplete. |
| Data product preview/release/catalog delivery | Product service and catalog outbox | Existing authorization and delivery boundary tests pass. Cross-page CR/CO enforcement is not implemented. |
| Recommendations / impact / similar parts / process context | Graph analysis and agent read goals | Existing UI and semantic decision-loop tests pass; live LLM quality remains untested. |
| Advisory learning | PostgreSQL feedback/outcomes/lessons with explicit review | Approval remains advisory; tests pass. No autonomous policy promotion is established. |
| Retained workflow recovery | Agent workflow registry and receipt reconciliation | Existing tests distinguish advisory read recovery from write receipt reconciliation. Recover does not imply replaying a write. |
| Central Change Control | Read-only OSLC evidence projection | Visibility only; not a central approval ledger or execution order authority. |

Registered agent workflow definitions reviewed in `backend/agentic_service/catalog.json`: `data-product-governed-publication`, `engineering-governed-publish`, `business-context-enrichment`, `ontology-review-and-bridge-plan`, `bridge-validated-automation`, `ontology-union-automation`. These overlap UI capabilities; they must not introduce a second independent approval state. Existing backend tests cover representative boundaries rather than every live agent/model/tool permutation.

## Confirmed defects

### WF-01 — P1: session replacement does not invalidate Data Flow

Location: `frontend/src/pages/DataFlowPage.js:180–198`, load sequencing at `:123`.

Root cause: listeners handle only `depo:credentials-changed` and `depo:credentials-cleared`; session replacement, expiry and successful access revalidation are omitted. Reads and selected evidence can remain from the previous session until polling. Write callbacks and approved-release loading also lack a session generation check.

Reproduce: mount and load Data Flow; dispatch the application `depo:session-replaced` event. The audit probe confirms that the runs endpoint is not called again immediately. Impact: stale workflow evidence and reviewer context after reconnect; no server authorization bypass was demonstrated.

Fix: consistent session generation ownership, clear authorization-sensitive state on invalidation, refresh after successful access verification, cancel obsolete reads, and ignore old write responses without implying that cancellation rolled back a server write.

### WF-02 — P1: rapid replay can submit duplicate work

Locations: `frontend/src/pages/DataFlowPage.js:221–240` and replay button `:356`; backend `backend/data_pipeline_service/router.py:470–493`; new run identity at `backend/data_pipeline_service/run_records.py:55–56`.

Root cause: replay uses React busy state without an immediate ref lock. Two clicks before the next render both submit. Each backend replay creates a new run; the route has no replay-intent idempotency binding. Job-definition actions already have a ref lock, but direct replay does not share it.

Reproduce: issue two Replay clicks in the same React act/render cycle with a pending API response. The probe observes two API calls instead of one. Impact: duplicate runs, worker load and potentially repeated downstream processing. This audit did not deliberately enqueue duplicate live jobs.

Fix: immediate operation lock plus a stable idempotency key for one replay intent, persisted and enforced by the backend. Legitimate later replays must still create new runs. Extend tests to retry after an ambiguous network response and cross-tab simultaneous submission.

### WF-03 — P2: workflow metadata overstates actual output

Locations: `frontend/src/workflows/workflowEngine.js:150–228`; handlers `backend/Services/semantic_workflow_service.py:996–1044` and merge comparison `:1047`.

Examples: merge outputs list a graph merge commit while `writes_to_neo4j` is false; dictionary stages say publication while the handler writes a report; taxonomy promises concept clustering/synonyms while the handler builds a forest from retained taxonomy. Runtime merging replaces labels/status but leaves these local descriptions/stages/outputs authoritative.

Reproduce: compare Advanced workflow guidance with each handler's returned artifact manifest. Impact: users cannot tell “report generated”, “registered draft”, “approved” and “published” apart.

Fix: one backend capability contract covering execution owner, actual stages, output kind, mutation scope and terminal receipt; render it consistently. Use “comparison report”, “export dictionary” and “export declared hierarchy” where appropriate.

### WF-04 — P2: Import STEP guidance sends users through the wrong mental flow

Locations: `frontend/src/features/import/ImportWorkspace.js:2848`, `frontend/src/workflows/importPresentation.js:58`; governed routing starts with `governedSourceProfile` at ImportWorkspace `:47`.

Live observation: Import says to commit the CAD graph, while governed engineering rows can finish validation with graph publication still pending in Data Flow. Impact: “Complete” and a committed graph are confused; users may attempt linking before publication.

Fix: route-specific stages and primary next action. For a governed run, say “Validation complete → Review/publish in Data Flow → Link published instances”; only call it published after a matching receipt.

### WF-05 — P2: historical implementation wording leaks into current Import UI

Locations: historical status rendering in `frontend/src/features/import/ImportWorkspace.js` and local persistence restore `:269–300`.

Live observation: retained ontology rows display “published to Neo4j”, despite current UI terminology using “knowledge graph”. Root cause: raw historical messages survive source-code label changes.

Fix: render semantic state labels from structured receipts; keep historical raw messages only in technical diagnostics. Do not blindly rewrite identifiers, source content or provenance.

## Risks requiring additional reproduction

- **P1:** Import's artifact results and ontology option cache have no direct session-event invalidation in `ImportWorkspace.js` (catalog load/cache `:121–214`, artifact execution `:1214–1230`). Old-session completion may overwrite current UI state. Other bridge/task components have better generation guards. Reproduce with deferred responses across a reconnect before calling it a confirmed cross-session data leak.
- **P1:** `loadReleases` at DataFlow `:112–119` can complete after credentials are cleared and repopulate old approved-release choices. A late replay/publication response may similarly update selected state. Backend approval checks still apply; no unauthorized write is proven.
- **P2:** direct publication at DataFlow `:285–301` lacks the immediate ref guard used for definition actions. Backend publication locks/receipt checks reduce the write risk; rapid-click concurrency still needs a dedicated reproduction.
- **P2:** Data Flow displays the generic `health.status` as the page badge at `:316`. Live badge was “Disabled” while a worker and 67 retained runs were available; service, scheduler and optional Spark states need separate labels.
- **P2:** Import, owner workflows and Change Control expose separate entry points without a common CR/CO identifier. Phase 1 visibility does not solve centralized approval, source revision binding or stale preview invalidation across the entire flow.
- **Performance:** Data Flow waits for all four initial requests via `Promise.allSettled` before applying any successful result. A slow telemetry request delays otherwise ready run evidence. Test independent partial rendering and cold-start latency.

## Prioritized remediation

1. Common session/operation ownership for Import, Data Flow and publication settings; preserve retained task IDs while invalidating obsolete selections and callbacks.
2. Replay-intent idempotency and synchronous UI operation guards; keep recovery distinct from resubmission.
3. Canonical capability/output contract; route-specific stage labels and one primary next action per result.
4. Cross-page CR/CO ledger and exact-source approval enforcement, building on OSLC CM and PostgreSQL. Do not merely hide existing buttons before replacing their enforcement.
5. Customer acceptance with slow/unavailable services, reconnect/restart, two tabs, interrupted workers and real configured model/embedding providers. A passing mocked suite alone is insufficient.

Audit probes: `frontend/src/pages/WorkflowReview.audit.test.js`. Convert expected failures into normal regression tests when implementing the fixes.

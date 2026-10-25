# Implementation progress — 24 October 2026

## Completed first increment

- Shared Companion scope projection is used by retained-history filtering and follow-up query refinement. Authorization remains with existing session and service owners.
- Mapping-memory reuse now requires a resolved ontology. Resolution failure cannot request all project mappings.
- Reusable mapping facts require explicit approved lifecycle state, no superseding reference and a current validity window. Legacy facts without lifecycle state are excluded; no automatic approval or database migration is performed.
- Both mapping-fact writers (memory adapter and atomic graph publication) initialize lifecycle metadata on creation only. Re-recording a fact cannot silently reactivate a revoked or superseded record.
- Optional conversation-memory read results distinguish unavailable storage from available-but-empty context.

Validation: 57 tests passed in 13.33 seconds across memory regressions/service, Companion page context, read-goal runner, chat prompt context and bridge workflow regressions. Mocked/isolated tests; no live database acceptance or deployment performed. `git diff --check` passed (existing unrelated CRLF notices only).

## Neo4j GenAI plugin assessment

No application calls to `genai.*` or `ai.text.*` were found in the reviewed backend/infrastructure/frontend source. Installed plugin availability was not queried; installation and application usage are different questions. Existing `backend/Services/graph_embeddings.py` uses `backend.core.llm.embeddings` to generate vectors through Python.

The optional plugin could generate embeddings near graph data through Cypher. It does not supply memory ownership, source lifecycle, approval, multi-store deletion or reliable orchestration. Keep the current provider abstraction for offline/local deployments and avoid maintaining two embedding pipelines without an explicit backend setting, model/dimension compatibility, index migration and benchmark.

Neo4j documentation: [plugin introduction](https://neo4j.com/docs/genai/plugin/current/) and [embedding APIs](https://neo4j.com/docs/genai/plugin/current/embeddings/). Current documentation distinguishes `ai.text.embed`/`embedBatch` from deprecated `genai.vector.encode` APIs. Select APIs only after inspecting the installed Neo4j/plugin version. Do not copy provider credentials into query strings or logs.

Recommendation: retain plugin-independent embedding generation by default. Evaluate a plugin-backed adapter only if a measured database-side embedding workload justifies it. No plugin installation, provider call or database configuration change was made.

## Remaining approved-plan work

This increment does not complete the entire architecture backlog. A full context envelope with revision/identity/budget adapters, mandatory receipt projections, governed semantic invalidation operations, multi-owner retention receipts, procedural promotion and measured domain evaluation remain pending. Source-revision metadata cannot be invented for legacy facts. Live rollout needs controlled integration fixtures and a deployment step; do not label this customer-release certification.

## Second increment: context binding and mandatory evidence retention

Implemented a versioned internal context envelope in `backend/agentic_service/context_envelope.py`, used by read goals, durable workflow queue records and retained Companion turns. It projects selected resource identifiers, server-established owner/run identity, deadline, byte budget and contract digest; arbitrary request metadata and secrets are not copied. Source revisions remain explicitly unverified. Public projections hide the internal owner reference.

Workers verify retained envelope ownership, scope, deadline and contract binding before execution. Existing pre-envelope runs retain their previous recovery checks. This is not a replacement for authorization, source-version validation, a tenant security boundary or live revision reconciliation.

Required PostgreSQL Companion retention now precedes optional graph-memory enrichment. An enrichment exception or unsuccessful write cannot suppress a retained answer. Conversely, required retention failure returns a failure without attempting graph enrichment. Memory writes return per-attempt success rather than relying on possibly stale health state.

Owner-service retrieval identifies `postgres_business_context` versus `owning_service_records`, marks bounded coverage and unverified source revisions, and explains that ContextGraph synchronization with Neo4j is not established. The Companion does not claim completeness from a listing.

Validation executed:

- 96 tests passed in 103.16 seconds: context envelope, goal routes/runner, graph memory regressions/service, page context, LLM interaction regressions and orchestration completion (before final workflow-envelope integration).
- 17 tests passed in 17.74 seconds: retention fault injection, envelope, page context and GraphRAG fallbacks (before final workflow-envelope integration).
- Final affected-path verification: 50 tests passed in 3.35 seconds covering retention ordering, envelope/tampering checks, read-goal routes, durable workflow worker, workflow control states and page context. Counts overlap and must not be added into a unique-test total.

The fault-injection fixture initially expected a raw RuntimeError; the real API correctly translated mandatory retention failure into HTTP 503. The fixture was corrected to assert the existing API contract; no production error handling was weakened.

Still pending: source-revision authority/reconciliation; coordinated multi-store legal-hold and deletion receipts; procedure promotion governance; domain retrieval benchmarks and live UI/deployment acceptance. These are not satisfied by the new envelope or the passing isolated tests. No new destructive cleanup API, inferred retention policy, plugin installation, database migration or production restart was introduced.

## Third increment: source authority, procedure governance and cleanup receipts

- Added a bounded authenticated ontology revision API that snapshots artifact digest and lifecycle under the existing publication lock.
- New ontology-scoped read goals retain owner-service receipts before queueing, and compare them before model planning/completion and tool execution. Missing authority prevents queueing; source changes stop stale investigations. Existing pre-receipt runs remain compatible. Instance graph revisions and cross-service write atomicity are not covered by this read-goal contract.
- Added optional versioned governance to the existing workflow catalog contract: approved procedures require deployment-review identity and an evaluation artifact digest; proposed/retired procedures cannot be planned. Existing definition snapshots/digests continue protecting execution recovery. This is deployment metadata, not a new skill store, signed attestation or automatic trace promotion.
- Existing automatic conversation cleanup now records bounded latest-run per-store receipts before and after each action. Receipt persistence failure stops subsequent cleanup. Graph outage is distinguished from zero deletions; raw exception text is not stored in receipts. Stored conversation legal holds are respected by PostgreSQL and graph retention queries. Catalog file legal holds and purge-intent evidence remain with the existing owner.
- Updated INSTALLATION.md with exact endpoints, configuration, failure handling and compatibility limits.

Validation: 66 tests passed in 18.59 seconds across revision/context, goal routes, memory maintenance/governance, memory regressions and LLM interaction tests. A later isolated suite exposed an existing fixture dependency on test import order (a fake FastAPI module lacked APIRouter). The fixture now preloads its real boundary modules. Rerun: 37 tests passed in 2.88 seconds. Final revision/goal/governance/catalog/prompt/inference subset: 43 tests plus 4 subtests passed in 4.51 seconds, before the final total revision-timeout wrapper. Counts overlap.

No production deletion, restart, credential change, plugin installation or live database integration occurred. Remaining release work includes live domain evaluation, UI acceptance, instance-source revision contracts, explicit retention/legal-hold policy administration, full multi-store deletion orchestration and customer backup/restore validation. The latest maintenance receipt must not be represented as a complete enterprise deletion ledger.

## Fourth increment: coordinated Admin cleanup and Import recovery

Fixed a preflight gap: graph reset previously preceded Import artifact-boundary validation. Full cleanup now validates the selected task storage/fence boundaries and stored task/manifest holds before graph deletion. Retry tombstones cannot replace the status of an actually listed active task.

Import deletion fences now retain per-phase artifact/snapshot/manifest progress and return sanitized task-level failure types. Individual store failures remain partial outcomes instead of hiding other store results.

Full schema cleanup persists a PostgreSQL intent before invoking the graph reset. It records graph, reconciliation, ontology metadata and Import cleanup phases in `admin_cleanup_runs_v1`, exposes authenticated receipt lookup, and includes a receipt in successful/partial responses. Initial receipt-storage failure prevents graph deletion. Later storage or Import cleanup failure cannot be reported as overall success. Automatic graph-reset replay is explicitly forbidden. Interrupted exceptions finalize running phases as outcome-unverified where possible.

Validation: 38 tests passed in 3.04 seconds across receipt fault injection, Import cleanup, Admin maintenance lifecycle and artifact retention recovery, before one additional active-retry regression was added. Tests used temporary directories and mock databases/graph cleaners. No live cleanup was executed.

This is bounded coordination of the existing Clean schema operation. It does not erase every application store or backup, establish graph-wide legal-hold administration, or certify privacy compliance. Live deployment/integration and customer release acceptance remain unverified.

Final cleanup verification: 44 backend tests passed in 3.36 seconds after extending an older AST fixture to mock the now-required receipt store. Admin UI now displays cleanup phase/receipt details and avoids recommending blind graph-reset retries; 8 AdminPanel frontend tests passed in 2.47 seconds. An initial UI edit command used the wrong relative directory and made no edit; it was corrected before the final test run.

The frontend production build passed in 15.72 seconds (existing large-chunk warnings remain). The cleanup receipt response header is exposed through the shared CORS configuration so browser clients can read it.

Shared service liveness/readiness and cleanup receipt checks: 5 tests passed in 59.60 seconds. No customer data was deleted, and no services were restarted or deployed.

## Fifth increment: domain evidence isolation and truthful acceptance evidence

Companion now independently verifies prefix-only scope and requires exact ontology IDs instead of accepting a prefix alias in the ID field. It rejects relationships whose endpoints are absent from the returned graph evidence. Added synthetic AP242, QIF, PLMXML and MBSE fixtures covering scoped identities, source publication revision, false scope matches, missing evidence and explicit non-entailment limitations. Existing mapping/page/transport tests remain in use.

Validation: 35 tests passed in 3.42 seconds. The legacy customer acceptance script was subsequently removed because it could report a customer source as loaded from an unrelated dictionary response and was excluded from normal test collection. Its stale collection exclusion was removed too.

Live acceptance is blocked: localhost shell probes timed out and the browser returned connection refused at port 3000. Backup/restore verification is awaiting a backup location and disposable target, requested from the user. See DEPO_RELEASE_ACCEPTANCE.md for exact evidence and the controlled restore drill; neither gate is claimed complete.

Final domain/search regression run: 43 tests passed in 3.49 seconds. Browser verification also failed with ERR_CONNECTION_REFUSED at localhost:3000; no live acceptance pass is claimed. Documentation command paths were checked after correcting literal tab escapes in the added PowerShell examples.

User confirmation: no backup exists yet. The backup/restore release gate is explicitly blocked; creating a coordinated backup and validating it in a disposable target remain outstanding. No production changes were made in response to this confirmation.

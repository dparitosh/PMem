# Workflow correctness audit — 2026-10-03

Reviewed commit: `77f5fdd99f923350b345a1fd53526c501a8f8a05`. This review confirms two P1 findings and seven P2 findings; it does not establish twenty P1 bugs. Related missing routes and state-update races are grouped by root cause, rather than counted individually. No application fixes were made in this review.

## P1 findings

### W01 — Standalone ingestion does not host the frontend tracked import contract

Location: `frontend/src/config.js:260`, `backend/ingestion_service/app.py`.

The frontend calls upload, status, preview, pre-commit, commit, and cancel under `/api/v1/import`. The standalone ingestion application's included routers do not define these six operations. Their implementations remain in `backend/main.py`; the deployment manifest launches the standalone service. The service advertises an import-upload capability despite lacking that route. Generic tracked imports cannot complete on the default standalone deployment. Governed-import and QIF operations are separate surfaces and do not repair this contract.

Evidence: AST inventory of all directly included ingestion routers found all six paths absent. This is static route evidence, not a live HTTP test.

Fix: extract the tracked import routes into an authenticated router hosted by ingestion; verify actual OpenAPI operations against the frontend contract and execute upload-to-commit acceptance. Do not solve this by loading the aggregate application's entire route set.

### W02 — Concurrent approval or schedule edits can undo job disable

Location: `backend/data_pipeline_service/job_definitions.py:128`, `:146`.

Approval and scheduling read a definition and replace the entire record through an unconditional put. If a disable commits after the read, the stale approval or scheduling record restores enabled/approved state. This defeats the operator's execution stop control.

Evidence: executing the actual approve/get/key functions with an interleaved disable produced `enabled=true`, `lifecycle_state=approved`; the disable state was overwritten.

Fix: serialize every definition lifecycle mutation with one shared per-definition lock, or use compare-and-update and reject stale writes. Re-read state within the protected operation. Cover approval, disable, schedule configuration, and schedule removal.

## P2 findings

| ID | Location | Trigger and consequence | Required fix |
| --- | --- | --- | --- |
| W03 | `frontend/src/Components/DataImportPipeline.js:1259`; `backend/Services/semantic_workflow_service.py:1186` | Import's Apply approved links checkbox submits `apply_links=true` to the old semantic workflow endpoint. The backend deliberately rejects every such request. The UI still describes a publication action that cannot execute. | Route users through durable Bridge preview, candidate review, and approved publication; remove the retired mutation control and misleading guidance. |
| W04 | `backend/data_pipeline_service/router.py:132` | In inline mode, the handler succeeds but output retention/completion raises. Completion is outside the exception handler, leaving a running manifest with no worker lease. The caller receives an error and the run cannot be normally reclaimed. | Record a recoverable completion failure; persist enough result evidence for safe reconciliation without blindly repeating the handler. |
| W05 | `backend/mesh_store.py:157`; `backend/data_pipeline_service/run_records.py:135` | Heartbeat matches worker ID and running state, but not attempt identity or a currently valid lease. A delayed renewal can revive an expired claim; an old attempt using a reused explicit worker ID can renew the replacement attempt. Terminal writes have stronger guards, but renewal remains weaker. | Pass the expected attempt to SQL and require attempt equality plus unexpired lease using the database clock. Mirror the contract in test doubles. |
| W06 | `frontend/src/workflows/runTracking.js:11` | A finished `quality_warning` result is mapped to convert stage, 10% progress, and no error/warning indicator. Import shows completed quality assessment work as still processing. | Define terminal execution states separately from successful quality outcomes; display a review-required warning and retained evidence. |
| W07 | `backend/data_pipeline_service/worker.py:41`; `backend/data_pipeline_service/worker_status.py:20` | Default busy renewal interval is 100 seconds for a 300-second lease, while worker status becomes stale after 60 seconds. Long valid executions therefore periodically make execution readiness report unavailable. | Renew worker telemetry on a cadence below its configured stale threshold, independent of lease renewal; validate the configuration relationship. |
| W08 | `backend/data_pipeline_service/scheduler.py:75` | The scheduler searches only the newest 1,000 runs globally for a definition's latest run. At high submission volume a recent run falls outside that window, so the definition is treated as never run and enqueued again before its interval. | Query the latest run for the exact job/version in PostgreSQL, rather than filtering a globally bounded list. |
| W09 | `backend/data_pipeline_service/router.py:357`; `backend/data_pipeline_service/run_records.py:245` | Publication idempotency checks only checkpoint state advanced. Successfully published jobs with no next checkpoint have state not_applicable and remain publishable to another ontology under the same run ID. Concurrent publication also blindly replaces the local receipt. Graph receipt identity includes ontology, so run identity alone does not bind the destination. | Lock publication per run, bind destination and payload digest on first attempt, and recognize recorded publication independently of checkpoint advancement. Reject conflicting destinations and preserve reconciled receipts. |

## Verification and limits

Dependency-light reproductions executed the actual Python functions extracted with AST for W02 and W04. W04 left the manifest running after an injected output-storage error. Node executed the actual runTracking module for W06 and returned convert/10%/error=false for quality_warning. W01 used actual route decorator inventories from included modules. W03 and W05–W09 are code-traced findings with explicit triggering conditions; concurrency, browser, PostgreSQL, Neo4j, and gateway integration tests remain necessary.

The already passing 27 regression checks do not cover these newly identified paths. No dependencies were installed, customer configuration changed, or release certification performed.


## Fix implementation

W01–W09 now have code fixes: ingestion hosts the authenticated tracked import router; definition lifecycle updates use compare-and-update; Import embeds governed Bridge jobs; inline result persistence errors record failure; heartbeats fence attempt and expiry; quality warnings are terminal review outcomes; busy heartbeat cadence stays below the stale threshold; scheduling queries the latest run for its exact job/version; and publication holds a per-run lock and retains an immutable destination/content intent independently of checkpoints. Concurrent mutations may return a conflict and require refreshing state.

Validation uses dependency-light execution of production functions and registry SQL assertions. Customer runtime browser/database/gateway acceptance is still required. PostgreSQL failure during failure recording can still prevent a terminal update; external effects must be reconciled before replay. Tracked import background work is not upgraded to a durable leased executor by this route restoration.

Final local validation: 35 Python regression checks passed, Node verified terminal quality-warning presentation, changed Python source compiled, installation package validation passed (48 PowerShell scripts, 10 APIs, 2 workers), and git diff --check passed. Full FastAPI/Vite and live integration tests were not executed because their dependencies/customer services are unavailable in this workspace. Commit and push status is recorded in Git history.

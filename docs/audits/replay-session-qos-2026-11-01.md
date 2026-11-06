# Replay session, state, persistence and logging audit

Scope: Data Flow Replay, shared API middleware, browser credential lifecycle, durable execution worker and Windows service logs. Local deployment only; no customer-environment certification or live LLM execution.

## Confirmed findings and corrections

| Severity | Finding / reproduction | Root cause / impact | Correction |
| --- | --- | --- | --- |
| High | Handled 403/409/422 and timeout requests can expose an ID without a matching service outcome entry. | RequestIdMiddleware logged only unhandled exceptions; troubleshooting could not distinguish rejected access, conflicts, validation or capacity failures. | Structured `http_request_outcome` logs include request ID, method, route template, status and time to response headers. Writes/failures/slow reads are retained; routine reads remain DEBUG. |
| High | Restart a service with a nonempty redirected error log. | Start-Process reopens fixed redirect paths, overwriting previous launch evidence. | Copy prior nonempty logs into a unique `logs/windows-services/archive/<launch>/` directory before relaunch. No automatic deletion added. |
| Medium | A durable worker handler fails. | Failure may be persisted but worker log lacked consistent run/request/attempt correlation. | Structured claimed/completed/failure events include run, job, worker, original request correlation and attempt. Error type is logged without source payload or exception message. Detailed retained failure remains in run evidence. |
| Medium | Replay accepted while filters hide the new run; queued rows still offer Replay. | No acceptance receipt/filter reset and incomplete active-state guard. | Visible receipt, filter reset, and queued/running replay guard. Verified in local browser with disposable acceptance analysis. |

Implementation locations: `backend/depo_platform/service_runtime.py`, `qos.py`, `windows_runtime.py`; `backend/data_pipeline_service/worker.py`; `infra/windows/start-depo-services.ps1`; `frontend/src/pages/DataFlowPage.js`.

## Executed evidence

- Session/timing/persistence/QoS cohort: 77 passed and 9 subtests passed. Includes capacity reservation, deadlines, pool saturation, lease ownership/expiry, replay response-loss recovery, snapshot persistence and release data preservation.
- Logging/credential/archive cohort: 38 passed and 7 subtests passed. Includes actual PowerShell log-copy execution and secret-exclusion checks for structured request/worker records.
- Frontend: 74 passed across five files, including session renewal, expired deadlines, aborted retry backoff, missing-scope behavior and Data Flow reconnect guards.
- Worker/logging cohort: 36 passed (overlapping cohort; do not add counts as unique tests).
- Prior isolated database acceptance: 7 passed, covering transaction rollback, semantic worker recovery and replay idempotency in disposable acceptance schemas.

Workspace logs: `outputs/session-qos-audit.log`, `outputs/log-session-final.log`, `outputs/session-qos-frontend.log`. Production build passed for the Replay UI change.

## Operational interpretation

Session expiry must reject a write rather than silently replay it after reconnect. Missing execution scope must not invalidate valid read scope. An ambiguous network result retains its immutable submission reference for receipt recovery; authorization does not prove job completion. A queued run requires a live worker, and a worker must hold its current lease before persisting completion. HTTP time to headers is not full streaming duration or worker execution duration.

Find HTTP failures by response `X-Request-ID` in `<service>.err.log`; correlate worker events using `correlation_id` and `run_id` in `data-pipeline-worker.err.log`. Historic launches are under the archive folder. Inspect the retained run for business failure detail and output evidence. The structured events exclude bodies, query values and authorization headers; this does not establish blanket redaction of every third-party exception logger.

## Limits

No production load SLO, customer network test, multi-tab customer acceptance or full long-running soak was established. Active redirected files are not size-rotated while running; external retention/rotation or scheduled maintenance remains operational work. Archived logs need a deliberate retention policy. These checks do not resolve an unseen customer request error solely from its generic UI message.

## Live post-deployment verification

Managed updater completed with backups and unchanged environment hashes. Ten service browser-session checks and both ontology read checks passed. Controlled invalid authorization requests returned 403 with matching request IDs in the real pipeline log; the marker token was absent. A disposable `acceptance-semantic-dataset-analysis` replay completed, was read back through the API, and produced claimed/completed worker events with the original HTTP correlation ID. Evidence: workspace `outputs/live-correlated-logging.json`, `outputs/live-worker-logging.json`, `outputs/browser-session-logging-final.log`, `outputs/correlated-logging-deploy.log`. Previous redirected logs were archived before relaunch. No customer job was replayed or data product published.

## Bounded local concurrency follow-up — 2026-11-02

Two temporary read-only sessions exercised 40 reads with concurrency four across pipeline run listing, ontology health and access verification. All returned 200 with their supplied request IDs. Both sessions renewed successfully. Disconnecting one yielded the expected 401 expired/reconnect response; the other continued returning 200. Temporary sessions were disconnected in cleanup.

Observed client latency in this small sample: median 10.3 ms, nearest-rank p95 52.58 ms, maximum 61.2 ms. Pipeline QoS reported no rejected requests and zero active work requests at inspection; its one active control request was the metrics read itself. This is not saturation testing, a soak test, browser multi-tab certification or a production SLO. It does not validate customer networking or heavy graph/materialization latency.

Evidence: workspace `outputs/session-concurrency-2026-11-02.json`. No runtime code/configuration changes, customer replay or publication occurred during this follow-up. Source/documentation changes from the preceding fixes remain uncommitted.

The 2026-11-02 frontend/runtime refactor supersedes the active-file rotation limitation above: application streams now have bounded rotation and separate bootstrap diagnostics. See `frontend-navigation-session-2026-11-02.md` for final tests, deployment recovery and browser checks. Archived launches still require an explicit retention policy.

# Run ID lifecycle audit — 2026-10-02

Scope: pipeline registry/worker, governed imports, SysML import UI, agent tool and
workflow execution, telemetry, Data Flow navigation/replay and persisted import monitors.

## Confirmed findings

1. **P2 — Missing governed run ID accepted by import UI.** DataImportPipeline reads
   run_manifest.run_id without validating it and still reports completion. Require
   a non-empty string ID before accepting the response; the SysML tab already has
   a missing-ID check, but this older governed branch does not.
2. **P2 — Queued run displayed as completed.** The same branch sets completed/100%
   even when the durable worker returns queued. Preserve the actual run state and
   poll the pipeline run endpoint using dataJobRunId, separate from legacy taskId.
3. **P2 — Workflow and telemetry IDs cannot be joined by run ID.** Agent workflow
   storage generates run-UUID while telemetry independently generates agent-...;
   neither returned workflow record nor telemetry stores an explicit ID link.
   Preserve distinct IDs with explicit workflow_run_id/telemetry_run_id linkage.
4. **P2 — Agent tool run ID omitted from responses.** POST /api/v1/runs creates
   telemetry but returns only dispatched tool output. Errors also omit a stable
   tool telemetry ID. Return the ID and expose it on error responses for recovery.
5. **P2 — SysML success link loses the run ID.** Its Data Flow link uses only
   #/data-flow, so the specific imported run is not selected. Include the encoded
   durable run ID in the supported run route segment.
6. **P2 — Requested historical run silently replaced.** Data Flow searches only
   fetched recent runs then falls back to the current/first row. Fetch a requested
   run directly; missing/inaccessible runs should show an explicit error rather
   than another run as the selected result.
7. **P2 — Replay response ID discarded.** Data Flow awaits replay but ignores the
   returned run_manifest, reloads and can continue selecting the original run.
   Select the newly created run and display its replay_of lineage.
8. **P2 — Error recovery ID not consumed by UI.** Workflow failures supply
   X-DEPO-Run-ID and shared CORS exposes it, but no frontend consumption was found.
   Show an encoded link to the retained workflow record with reconciliation status.

## Correct behavior retained

Pipeline run IDs use UUID4 and are distinct from job definition IDs and versions.
Replay creates a new ID and records replay_of through replay_payload/start.
Worker reclaims retain the existing run ID and increment attempt; fenced lease
transitions prevent an old worker from overwriting a newer attempt. Pipeline
publication uses the run ID as its stable publication ID for receipt recovery.
Import task IDs, document task IDs, source artifact IDs, Bridge job IDs, request
correlation IDs and workflow IDs identify different records and must not be
interchanged or globally reformatted. No UUID-generation collision defect was
identified in this review.

## Verification and limits

Findings are based on source tracing; application code was not changed in this
audit. Prior worker/registry regression tests passed, but this review does not
certify live PostgreSQL worker recovery, concurrent publication or customer API
responses. Required fixes should have focused tests for queued/missing IDs,
historical lookup, replay selection and agent telemetry linkage before release.


## Fix implementation

All eight findings have code fixes: required manifests, accurate worker state and polling, linked workflow/telemetry IDs, tool response/error IDs and retained lookup, exact SysML links, direct historical lookup, replay selection/lineage, and an agent recovery notice that consumes error headers. Recovery requests use a sequence guard so stale responses cannot replace newer run state. Both agentic and shared API clients report agent recovery headers.

Validation: 33 focused Python regressions and the dependency-free run-tracking JavaScript checks passed. Customer PostgreSQL concurrency, downstream write reconciliation and live gateway behavior are not certified by these tests.

Frontend verification: 19 focused Vitest tests passed across Data Flow, SysML imports, import routing, API access and agentic API. Vite production build passed (3334 modules); existing large-chunk warnings remain. Five dependency-free frontend contract checks passed, and git diff whitespace validation passed. Temporary frontend dependencies were removed after validation.

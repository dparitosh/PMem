# Import cleanup bug review — 2026-10-21

Scope: the newly deployed Admin Clear Import Workflows action, its interaction with Import persistence, schema-set tasks and Full Schema Cleanup, and the deployment launcher. This is not certification of every application feature.

The user reported deployment success. The live browser loaded the new Clear Import Workflows control and authenticated with the previously authorized maintenance scope. Read-only inventory found ten completed instance imports and one completed schema-set task. The deletion confirmation was opened, then canceled during this audit; none of these eleven workflows was deleted.

## Findings fixed in source and the updated deployment package

1. **Interrupted deletion could strand data.** The original receipt was marked cleared before deletion finished. A process crash could leave files or a PostgreSQL manifest behind while the next run ignored the receipt. Receipt JSON could also be truncated. Receipts now use atomic, flushed writes, distinguish deleting from cleared, and reconcile interrupted/corrupt receipts and remaining files/manifests on retry. They become cleared only after deletion verification.
2. **Some persistence paths were outside maintenance exclusion.** Cancellation, task snapshot persistence and schema-set direct state writes could race cleanup even though the major parsing/commit workers were guarded. These writers now acquire the same shared maintenance guard; cleanup holds its exclusive counterpart.
3. **A secondary receipt-write failure could hide a partial cleanup.** Failure to record cleanup_failed could replace the primary error with a generic exception. It now logs the secondary failure, returns the failed task IDs and preserves the earlier deletion fence for reconciliation.

## Verification

- 66 backend tests and 16 subtests passed, including corrupt/incomplete receipts, remaining artifacts behind an old cleared receipt, locked folders, failed recovery writes, active/uncertain task protection, database manifest verification and stale worker fences.
- Existing frontend checks previously passed: 28 tests and production build. This audit revision changes backend files only.
- The nine-file package validates successfully. The launcher passes isolated tests for backend-only deployment, changed-frontend rebuild, and restoration/restart after a simulated startup failure. Unchanged frontend files now skip frontend stop/build/start.
- The live deployment has the first cleanup implementation. The audit corrections require running the updated Apply-PMem-Import-Cleanup.cmd again. Live deletion and post-delete verification remain pending; do not report the Import page or PostgreSQL history as cleared yet.

Evidence: task outputs import-cleanup-launcher-audit.json and import-cleanup-audit-paused.png. Earlier maintenance findings still apply: log/history purge controls are absent, governed/shared artifacts are retained, and an empty ontology registry is incorrectly labeled unavailable.

# Admin maintenance end-user test — 2026-10-21

Tested the running application at http://127.0.0.1:3000 through its browser UI. The user explicitly confirmed enabling maintenance and deleting current test data before destructive actions. No direct database-delete or filesystem-delete commands were used for the live cleanup.

## Results

| UI action | Observed result | Verdict |
| --- | --- | --- |
| Verify current read session | All ten listed service read scopes verified; header became Online | Pass |
| Enable Admin maintenance and connect registered services | Maintenance controls became available | Pass |
| Clear Cache | UI confirmed graph, ontology-list, configuration and shared-generation invalidation; graph counts unchanged | Pass |
| Delete Old XSD Schemas | UI reported no eligible old ingested XSD schemas | Empty-case pass; actual old-XSD file deletion not exercised live |
| Reset Graph Only | Typed RESET GRAPH and confirmed. Nodes 526,083 → 0; relationships 2,941,005 → 0; indexes 102 → 17; constraints 5 → 4 | Pass |
| Full Schema Cleanup | Typed CLEAN NEO4J and confirmed. UI reported 18 metadata entries cleared; nodes, relationships, indexes and constraints all 0 | Pass for its documented scope |
| Dismiss old execution warnings | Two reviewed warning banners disappeared and remained absent after refresh | Pass; this does not delete PostgreSQL agent records |
| Clear log files | No control exists in the current Admin UI | Missing feature; logs were not cleared |
| Purge retained failed-agent runs | No purge control exists; 17 runs, 7 failures and 6 tool failures remained after cleanup and refresh | Missing feature; retained history was not deleted |

## Filesystem verification

Read-only filesystem checks supplemented the UI test:

- ontology_uploads was already empty before this test and remained empty. Therefore removal of populated legacy upload directories was not exercised live.
- data/ontology_service had 18 directories before full cleanup. Afterward it still had 18 directories and 18 retained artifact files, but zero metadata.json files.
- This is not a complete artifact-directory purge. The catalog cleanup implementation intentionally deletes active PostgreSQL catalog registrations and metadata mirrors while retaining artifacts. A user expecting every XSD/TTL artifact folder to disappear will not get that behavior from the current control.
- Service and installation logs remain on disk. The UI provides no log inventory, log preview or clear-log action.

## Error capture and recovery limits

The service access log recorded successful POST requests for cache clear and graph reset. Current service log scanning found 28 log files and no ERROR/CRITICAL/traceback markers; that does not establish whether previous failed agent runs were ever written to these particular log files. No live server exception was deliberately induced. Do not describe live runtime exception capture or log clearing as passed.

Supporting isolated backend checks passed: 43 tests and four subtests covering maintenance authorization, cleanup reconciliation, partial failure handling, directory boundaries and audit error capture/redaction. These tests use fixtures; they do not replace the browser results above.

Full Schema Cleanup leaves Neo4j with no publication constraints or indexes. The UI directs operators to restore them with the supported Neo4j bootstrap procedure before publishing again. That bootstrap was not run in this test, so the final graph remains empty with schema removed as requested.

## UX findings

1. During the large graph reset the page showed only Refreshing and stale counts, without an operation name or useful progress indication.
2. Full cleanup reports metadata removed but cannot be interpreted as deleting all associated artifact folders. Its confirmation should explicitly name retained artifacts as well as retained governed history.
3. Historical agent failures are retained in PostgreSQL. Dismiss hides the browser warning; it is not history retention management.
4. After browser reload the maintenance session was no longer enabled, while read access and schema statistics recovered. Delete Old XSD Schemas remained enabled although other cleanup controls were disabled. This difference in authorization scope needs clear labeling and review.
5. Log viewing/clearing and terminal-agent-history retention controls are absent. They require separate scoped, previewable actions with active-run protection and honest partial-failure reporting before these customer requirements can pass.
6. Ontology Junction correctly showed zero terms and No ontologies loaded after cleanup, but displayed an incorrect Ontology service unavailable warning. Expanding it revealed No ontologies are registered. Import an ontology first. An empty registry is being presented as a service failure.

Evidence in the task output folder: admin-maintenance-before-test.png, admin-graph-reset-result.png, and admin-maintenance-final.png.

## Import history remediation prepared after the live test

Added a separate authenticated Clear Import Workflows maintenance action and integrated it into Full Schema Cleanup. It covers quiescent instance-import snapshots, schema-set task folders, task-owned files and matching workflow_artifact_manifests_v1 PostgreSQL records. Active tasks, queued work and uncertain publication outcomes reject cleanup before graph deletion. Shared maintenance locks exclude running import writers. Persistent deletion fences prevent stale process state and artifact writers from recreating cleared records; partial failures remain retryable. Successful browser cleanup invalidates saved Import rows across open tabs.

The existing Import-page Clear finished/failed history button remains browser-only; it does not replace the Admin action. Shared content-addressed artifacts, published ontology artifacts, governed products, separate agent history and logs remain outside this new action.

Verification: 61 backend tests, 16 subtests, 28 frontend tests and the Node.js 24 production build passed. The nine-file deployment package and PowerShell launcher were syntax/hash checked. The agent session cannot pass Windows CIM process-inspection checks (Access denied), so installed services were not restarted and live Import history has not been cleared by this remediation. Apply-PMem-Import-Cleanup.cmd in the task output folder installs with backup/rollback; it does not itself delete history. A live UI verification is still required after deployment.

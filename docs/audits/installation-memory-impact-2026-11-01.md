# Installation, documentation and memory-change impact audit

Date: 1 November 2026. Baseline: `0805ce9`. Scope: tracked modifications and new source/test/documentation/migration files in the working tree. This is a targeted cross-layer audit, not certification of every application feature or customer deployment.

## Findings and disposition

| ID | Severity | Evidence / root cause | Reproduction and impact | Disposition |
| --- | --- | --- | --- | --- |
| IM1 | High | backend/depo_platform/release_code_check.py:11 lacked newly required connector worker and memory modules. Offline package validation and startup validation had different mandatory-file coverage. | A partial customer copy missing connector_semantics.py could pass the backend mandatory-file check, then fail when worker imports execute. | Added explicit startup requirements for connector_semantics, speed_path, speed_router and companion_memory. Missing-module regression cases pass. Presence/fingerprint checks do not certify every possible semantic mismatch. |
| IM2 | Medium | backend/data_pipeline_service/speed_path.py:154 created the receipt before checking that events share one standard. | Mixed AP242/QIF selection returned validation failure but left a preparing receipt. Fault test failed before correction. | Validate the standard before creating a review. Regression verifies no pending receipt and no event-state mutation. Historical invalid preparing receipts are not deleted automatically. |
| IM3 | Medium | docs/AGENT_MEMORY_AUGMENTATION.md:19,44,85 retained Owlready2, silent timeout clamping and graph-memory prompt-injection claims inconsistent with current code. | Operators could misunderstand reasoner prerequisites, accepted configuration and what recall is actually wired. | Corrected to Semantica structural/context support, RDFLib exchange, optional OWLAPI/HermiT, rejected invalid timeout values, PostgreSQL-owned scoped follow-ups and optional graph enrichment. |
| IM4 | Medium | INSTALLATION.md grew to 488 lines and failed the existing customer-guide contract. Release additions obscured the numbered install sequence. | Customer-guide regression failed. | Guide now 292 lines. Detailed feature-specific changes moved into the linked operator reference, preserving the numbered steps and local documentation targets. |
| IM5 | Low | backend/tests/test_installation_audit_contracts.py:30 used an outdated short prerequisite fixture. | Four missing-entrypoint tests failed on the newly added first prerequisite instead of their selected missing file. | Build the fixture from the current required-file list; cover missing connector module and migration 017 too. |

## Installation and upgrade impact

- Existing root update-depo.ps1 remains the supported updater. It performs preflight, stops application processes, and delegates migrations/build/startup to the shared installer. No alternate migration engine was added.
- Migration 017_speed_event_pagination.sql is an additive captured-event paging index. Existing migration checksums/order are preserved; every previous migration-history prefix is exercised by the upgrade tests. Index availability is not proof of customer workload latency.
- Connector normalization uses existing worker and CEIM contracts. Approval and publication remain separate. No new worker, broker, Python dependency or credential profile is required by this change set.
- Companion resolved_query fields and graph context_json properties need no SQL schema recreation. Older turns fall back to the original question. Optional graph memory remains disabled unless explicitly configured, and cannot replace mandatory PostgreSQL evidence retention.
- GET speed-source/event/review inspection now requires existing graph-read authorization. Integrations that formerly read those endpoints anonymously must supply the existing read credential; no credential should be embedded in frontend bundles.
- Deploy matching API, worker and rebuilt frontend files together. Do not use SkipFrontend for the new Event reviews UI. Retain environment files, uploads, event artifacts, publications and database history.
- Release ZIP generation intentionally refuses a dirty working tree. The current changes remain uncommitted and undeployed; no customer ZIP or fresh installation is certified by these tests.

## Executed validation

- Offline package validator: PASS; 84 PowerShell scripts parsed, 38 documented command paths, ten API services, three workers, 190 locked Python distributions and 18 migration files.
- Broad installation/release/migration/semantic/memory regression cohort: 113 passed, 21 subtests passed; one Bash-dependent preflight test skipped because Bash is unavailable.
- Frontend cohort: 42 passed across Companion, Data Flow, Event reviews, API surface and governed learning UI.
- Final focused cohort after the mixed-standard fix: 48 passed, including negative packaging tests, release preflight, migration/documentation entrypoints and event recovery tests. Counts overlap; do not sum them as unique coverage.
- Changed/new Python files parsed successfully; git diff --check passed. No new frontend edit followed the previously successful production build.
- Evidence logs: outputs/installation-memory-final.log, installation-memory-last.log, installation-memory-frontend.log, installation-memory-package-final.log and mixed-standard-red.log (workspace outputs, not customer runtime inputs).

## Open acceptance boundaries

1. Local source is not deployed. Existing running services cannot demonstrate new source behavior until the normal upgrade is completed.
2. The preceding live browser rehearsal observed intermittent ingestion/graph timeouts and an empty Home conversation after return navigation. Root cause of the navigation gap is not established; no fix or customer acceptance is claimed here.
3. Optional graph memory is disabled in the running installation. The selected AP242 learning scope has no approved hint. Long-term recall is therefore not demonstrated, despite passing code-level governed-learning tests.
4. No live LLM, customer-origin/network test, production load/restore test, current fresh-install test or application-database mutation was performed in this pass. Previous isolated PostgreSQL transaction tests are separate evidence, not a rerun during this audit.
5. Continuous offset-managed streaming, customer effectivity/BOM semantics and executable parent CR/CO orchestration remain broader architecture work; this release must not advertise them as completed.

Release assessment: the identified installer/documentation regressions are corrected in source and tested. Customer release readiness remains conditional on deploying the complete reviewed change set and closing the stated live acceptance gaps.


## Subsequent replay authorization remediation

Data Flow now resolves the execution identity from the existing authenticated endpoint before POST replay (including Run now). It no longer depends on an empty manually entered reviewer to construct replay authorization. A per-connection rejection latch blocks repeated rejected writes; existing generation and idempotency guards remain. Ontology health/list use the read credential across incomplete OpenAPI metadata and anonymous requests are rejected in the client. Real invalid credentials remain rejected by the server.

The local deployment returned 200 for both read-only credential checks. Frontend regression cohort: 54 passed. Backend replay/authorization/service-contract/data-pipeline cohort passed; see workspace replay-auth-backend.log for exact count. No customer job was replayed by credential diagnostics.

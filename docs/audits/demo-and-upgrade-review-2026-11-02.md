# Demo content and customer upgrade review — 2 November 2026

## Deliverables

- Current walkthrough: `docs/DEMO-USER-GUIDE.md` with local sample selections, user actions, expected evidence, Companion/memory examples and recovery.
- Updated `deliverables/DEPO-Workflow-Audited.pptx`: 20 slides, including dedicated Change Control, approval decision, OSLC TRS and configuration baseline diagrams. Speaker notes link to existing code. Generation source: `scripts/presentations/build_workflow_audited.mjs`.
- Replaced the obsolete customer demo sequence with a pointer to the current guide. Updated demo indexes and Import/Ontology instructions. Historical audits and unrelated architecture decks remain historical evidence.

The deck retains the previous dimensions and navy/teal/Arial styling while replacing the text-heavy process lists with native attached arrows and elbow connectors. All slides were rendered and visually reviewed; a crowded upgrade-node label was shortened before final export. Final package: 20 slides, 67 attached connectors, 14 elbow connectors. Package/layout/import/font validation passed with no warnings. No claim of PowerPoint application testing is made.

## Code boundaries verified

Change Control aggregates owning-service records with separate authorization, execution and delivery. It is not a centralized CR/CO authoring/execution replacement. Existing OSLC CM representation/linking is distinct from this aggregate.

Analytics configuration baselines pin registered versions/artifacts in PostgreSQL. Deployment-local Configuration-Context selection is supported for the documented job types; foreign/conflicting context is rejected. These are PMem extensions, not a complete OSLC Configuration Management provider.

The source-review worker consumes a bounded local TRS page, retains a checkpoint and reconciles selected revisions/artifacts. Partial publisher coverage, feed gaps and unavailable TRS remain explicit. Notifications do not approve execution, replace graph publications or publish packages.

The deck records actual limitations: missing external offline OWL imports, no historical proof of the original three timeout causes, unavailable-model generation not tested, and business formulas/units/revision/effectivity requiring customer agreement.

## Upgrade findings and corrections

1. The maintained schema safety test still asserted the pre-business-mart schema counts. Updated it for migration 016's seven additional analytics structures (18 checked structures, 102 columns, 29 constraints and 15 indexes). Semantic dataset contracts retain their separate checks.
2. The offline update-sequencing test inadvertently required a real Node frontend tree. Stubbed that child compatibility boundary, preserving real updater sequencing tests without runtime dependencies.
3. The duplicate `test-upgrade-flow.ps1` fixture had drifted and failed on missing process-control setup. Removed the obsolete fixture, retaining the maintained `test-depo-update.ps1` and adding explicit nonzero installer-exit coverage there. The old dated audit's result remains a historical observation.
4. Updated updater help/completion guidance and installation instructions. No new production migration was necessary: existing update delegates to the root installer's checksum-verified pending migration, graph provisioning, build and service verification sequence. It operates on release files already placed by the operator; it does not download code.

The prior run-history deadline/lock-error correction and its regression tests are included in this release. It requires deployment/restart of the matching pipeline service; source tests do not change a running customer installation.

## Executed verification

| Check | Result |
|---|---|
| Upgrade preflight/history/schema safety plus run-list deadline tests | 27 passed, 24 subtests passed; one Linux-shell test skipped on this Windows setup |
| Maintained PowerShell update test | Passed: ordered stages, read-only preflight, failure before shutdown, preserved configuration, timeout idempotency and nonzero native exit |
| Real PostgreSQL upgrade and analytics tests | 8 passed in 12.83 seconds |
| Configuration/TRS/Change Control tests | 30 passed in 4.03 seconds |
| Installation package validator | Passed: 83 PowerShell scripts, 38 documented paths, 10 services, 3 workers, 18 migration files including bootstrap 000 |
| Final presentation | Passed package/layout/font/first-party import checks; 20 slides visually reviewed |

The real database test accepts only `depo_acceptance_test`. It creates a unique disposable schema at migration v11, inserts a retained registry record and synthetic credential profile, upgrades through v17, verifies retained records/credentials and old migration timestamps, reruns idempotently, then checks rollback of deliberately failing future-migration DDL/history. It removes its schema afterward. Existing semantic dataset, business analytics/mart and XML materialization tests also ran in isolated schemas. No live customer database was modified.

Local logs/previews under ignored output/build directories are excluded from Git. No customer rollout, external LLM invocation or new business approval was performed during this documentation/upgrade review.

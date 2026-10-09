# Windows backend and frontend startup audit — 2026-10-04

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Reviewed release: `4be05ec3f7a3e26de2c98c3b7b67bc2de163fb4e`. Scope: backend/frontend start and stop scripts, shared configuration loading, build receipts, and installation commands. No new P1 was confirmed. Nine P2 findings require fixes. Related frontend stop/timeout cleanup failures are grouped by root cause.

| ID | Severity | Location | Trigger and consequence | Recommended fix |
| --- | --- | --- | --- | --- |
| S01 | P2 | `infra/windows/start-depo-services.ps1:106`; `infra/windows/initialize-depo-schema.ps1:9` | Effective Spark/connector/scheduler command-line settings are applied, then schema initialization imports the environment file again. File values overwrite resolved switches before child services start. | Apply effective runtime settings after the schema import, or isolate schema initialization in a child process. Preserve all explicit switch overrides. |
| S02 | P2 | `infra/windows/start-depo-services.ps1:208` | Startup rollback stops only recorded launcher PIDs. Windows venv launchers may have base-Python descendants owning listeners, as the stop-services script already recognizes. Failure cleanup can leave child listeners while deleting PID files, preventing the next startup. | Snapshot and verify owned descendant processes, stop children before parents, and confirm ports released before deleting tracking. |
| S03 | P2 | `infra/windows/start-depo-services.ps1:147` | A process starts before PID-file persistence and before inclusion in startedServices. If PID-file writing fails, catch rollback has no record of that newly created process. Frontend startup has the same launch/write gap. | Track process identity immediately after Start-Process and protect PID writes in try/finally cleanup. |
| S04 | P2 | `infra/windows/start-depo-services.ps1:175` | The authentication probe runs before reporting readiness timeout or CORS mismatch. A dead or unready API is reported as a bad read key instead of its dependency/startup failure. | Report readiness/CORS failure first, then check authentication only for a ready service. Preserve actionable error categories. |
| S05 | P2 | `infra/windows/stop-depo-frontend.ps1:16`; `infra/windows/start-depo-frontend.ps1:91`, `:123` | Frontend stop/replacement/timeout kills only the launcher and removes its PID file. If a venv descendant owns the static server socket, it can remain serving the old process and block restart. Stop also silently reports success if process identity cannot be inspected. | Use the same verified process-tree cleanup as backend stop, verify the listener is gone, and report an unresolved owner instead of claiming success. |
| S06 | P2 | `infra/windows/start-depo-frontend.ps1:4`; `INSTALLATION.md:2340` | Frontend defaults to loopback independently of the configured application/service address. Some documented commands pass the VM address; others omit it. An operator following an omitted-host command can start a localhost-only frontend for a customer accessing the VM remotely. | Add a central explicit frontend bind setting with CLI precedence and use it consistently in the installation commands. Distinguish bind address from browser-facing address. |
| S07 | P2 | `infra/windows/start-depo-frontend.ps1:46` | Timestamp freshness rejects inputs before the content receipt is checked. Copying unchanged inputs after index.html makes a valid, hash-matching build fail startup. | Make the complete content receipt authoritative; use timestamps only as a hint when no receipt is available. |
| S08 | P2 | `infra/windows/runtime-config.ps1:172`; `infra/windows/start-depo-services.ps1:95` | Scheduling is rejected when Spark is disabled, although the scheduler supports approved non-Spark jobs and worker enqueueing. Optional Spark therefore blocks scheduling supported jobs. | Require Spark only for Spark connectors or Spark-dependent job types; allow non-Spark scheduling with execution-worker readiness. |
| S09 | P2 | `infra/windows/start-depo-services.ps1:125`; `infra/windows/start-depo-frontend.ps1:85` | Process reuse relies on any listener at a port, rather than its verified process tree and binding. Frontend reuse accepts any HTTP 200 at the requested address; it does not require the expected root/bundle. A tracked process and unrelated responder can lead to incorrect reuse/success. | Match listener ownership to the recorded process/verified descendants and requested binding, and verify service identity/frontend assets before accepting reuse. |

## Evidence

Executed the actual shared PowerShell configuration functions with a temporary environment file: Resolve-DepoSparkOptions selected true for an explicit EnableSpark override, then the schema-style Import-DepoEnvironment call reset DEPO_SPARK_ENABLED to false. This reproduces S01 without launching services or requiring Spark.

S02–S09 are code-traced findings with the triggering conditions listed above. The backend stop script explicitly handles virtual-environment descendants, while rollback and frontend cleanup do not. Process-tree and listener behavior still needs Windows customer-runtime fault injection. No claim is made that every Windows Python build produces a descendant listener.

Installation package validation passed: 48 PowerShell scripts, 22 documented paths, 10 API services, 2 workers, 202 locked Python distributions, 8 PostgreSQL migrations. Passing package checks confirms parse/path integrity, not working startup under these failure cases.

## Existing safeguards

Schema migration failure prevents new API launch. Backend startup probes dependency readiness, CORS, read-key acceptance, and pipeline worker heartbeats. Frontend checks content receipts and bundle existence. Backend stop restricts process selection to the project runtime and declared modules. These safeguards are useful but do not eliminate the findings above.

This audit did not install dependencies, launch customer services, modify customer configuration, or fix these findings. The audit file is local and uncommitted.


## Fix follow-up

S01-S09 now have implementation changes. Effective CLI switches are restored after schema initialization; process ownership, descendant cleanup, and bind/port matching use a shared helper; tracking precedes PID-file writing; readiness/CORS failures precede auth probes; frontend settings are centrally configurable and build hashes are authoritative; and installer, deployment validation, and release preflight allow non-Spark scheduling. Frontend reuse verifies its root and expected bundle reference. Installation guidance and the deployment environment template include frontend listener settings.

Offline regression checks exercise the actual process helper with mocked CIM snapshots and sockets, including descendant ownership, wrong binding, unrelated owners, and child-before-parent cleanup. Native customer Windows launch/stop fault injection remains required. Already orphaned base-Python processes whose launcher identity has been lost are deliberately not killed by guessing their port owner.

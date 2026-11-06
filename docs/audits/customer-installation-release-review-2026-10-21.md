# Customer installation release review — 2026-10-21

Decision after remediation: the identified source, test and documentation defects have been corrected in the working tree. Hold customer release until these changes are committed and a release built from that commit passes clean-machine acceptance. A successful installation on the existing workstation does not establish fresh-machine installation or failed-upgrade recovery.

## Remediation and verification

### Follow-up against the Import cleanup release

The current working-tree review added the cleanup module and coupled maintenance/import callers to the mandatory package inventory. This prevents missing runtime helpers from reaching post-shutdown service startup. A missing-cleanup-helper regression case verifies rejection.

Root update and diagnostic commands now apply process-scoped execution-policy handling before loading nested scripts and use the shared retained/redacted audit logger. Update accepts and forwards the selected Python executable and preserves the explicit environment, profile and preflight options across the logging wrapper. Successful and failing child invocations are tested with isolated fixtures.

Audit redaction now reads secrets from the selected custom environment file as well as the default root server file before environment import. Install, lifecycle, update and diagnostic wrappers pass that selection explicitly. Synthetic failure tests cover relative and absolute selected paths without leaking the marker into console output, exceptions or retained logs. The customer guide and operator reference describe this behavior and distinguish retained audit logs from data cleanup.

These corrections are source changes; they have not been applied to the running Windows installation by this review. Nine PowerShell/package checks pass. Clean-machine installation and backup/restore acceptance are still pending; the existing workstation is not a clean-machine substitute. Live Import deletion is also still pending deployment of the separate cleanup audit corrections.

- R1: guided Setup now validates before shutdown. Existing deployments reuse the advanced updater's read-only preflight, including database compatibility checks; fresh installations validate package, configuration and prerequisites. A storage write probe is cleaned up before shutdown. The selected Python executable is forwarded through the updater.
- R2: Setup-DEPO.cmd, setup-depo.ps1, install-checkpoints.ps1 and the new setup-preflight regression script are staged for Git inclusion. They are not yet committed or pushed; release assembly must use the final reviewed commit.
- R3: the package gate now requires the three guided entry-point/helper files and recognizes documented .cmd paths. Three isolated missing-file regression cases pass.
- R4: the prerequisite fixture now includes the real native command helper and isolates OS process inspection/runtime discovery. The real installer prerequisite/lock checks pass all fixture scenarios.
- R5: the guide identifies the canonical workstation procedure, scopes detailed manual/gateway credential instructions, replaces the old manual stop/update recipe with the supported updater, and separates installation, ontology review, publication and model inference acceptance.

Final checks: 30 Python tests passed; all nine PowerShell checks passed (package structure, setup configuration, dependency checkpoints, advanced upgrade flow, process identity, startup control, update behavior, prerequisite validation and guided preflight). Package validation parsed 84 PowerShell scripts. Git whitespace checks passed. Test evidence: task workspace outputs/enterprise-audit-2026-10-20/installation-fix-final.xml. No installed services or databases were changed by remediation tests.

The findings below preserve the original audit evidence; their source-level corrections are described above.

## Documentation and obsolete-script cleanup

The customer INSTALLATION.md was consolidated from over 5,300 lines to 105 lines. It now presents prerequisites, guided installation, verification, lifecycle actions, update/recovery and troubleshooting once. Detailed database, provider, Linux, gateway, optional runtime and diagnostic material is retained in docs/installation/OPERATOR_REFERENCE.md with corrected relative links. The old duplicate source-package procedure and partial XSD-repair procedure were removed.

Removed infra/windows/repair-depo-xsd-release.ps1: a historical partial-release copier superseded by complete matching release installation. Removed infra/windows/start-zeppelin.ps1: no callers or integration references were found in the repository. Supported lifecycle, dependency, migration, optional runtime and test helpers remain. No runtime data, configuration, databases or logs were deleted.

The demo runbook and architecture presentation source now name the current root installer. Package validation requires and scans both installation documents. Diagnostic prerequisite checking now forwards the selected EnvFile rather than silently using the default deployment configuration. Documentation regression checks cover the split and retired scripts. Forty Python tests passed after this cleanup; package validation reports 82 PowerShell scripts and 36 documented command paths.

Scope: INSTALLATION.md, guided Windows setup, root installation/lifecycle entry points, dependency checkpoints, native command logging, upgrade orchestration, package validation, PostgreSQL/Neo4j installation integration, and offline regression checks. This review did not stop the installed application, change credentials, apply migrations, or modify database contents.

## Findings

### R1 — High: guided upgrade stops the application before full preflight

Evidence: infra/windows/setup-depo.ps1:126–132 stops frontend and backend, then calls root install-depo.ps1. Root configuration preflight starts at install-depo.ps1:88; prerequisite validation follows at :125. Earlier setup checks Node and some inputs, but does not execute the complete deployment preflight before shutdown.

Impact: a configuration, Python prerequisite, storage, or subsequent dependency validation failure can leave a previously working application stopped. Retrying is documented, but does not prevent this avoidable interruption.

Comparison: infra/windows/update-depo-windows.ps1:39 onward validates the package, configuration, runtime prerequisites and database compatibility before shutdown at :60–61. Its offline sequence tests pass; those tests do not prove the guided launcher has the same behavior.

Required correction: share the read-only upgrade preflight with guided Setup before any stop operation. Add guided-path tests asserting no shutdown on invalid configuration, incompatible Python, incomplete release or failed database preflight. Preserve the rule that migrations run only after verified shutdown.

### R2 — High: customer entry-point files are absent from the current Git index

Evidence: git status lists Setup-DEPO.cmd, infra/windows/setup-depo.ps1 and infra/windows/install-checkpoints.ps1 as untracked. git ls-files for these three paths returns no entries. INSTALLATION.md:3 identifies Setup-DEPO.cmd as the customer entry point; infra/windows/install-depo.ps1:76 imports the checkpoint helper.

Impact: a customer release built from the current commit would omit these files even though the working directory and assembled local upgrade package contain them. This is a release assembly/version-control issue, not evidence that they are missing from the installed workstation.

Required correction: review and commit the intended release files, then produce and validate the customer artifact from the exact release commit. Review the other modified/untracked files deliberately; do not stage secrets, local logs or runtime artifacts. No commit or push was performed by this audit.

### R3 — Medium: package validation does not enforce the guided entry point

Evidence: infra/deployment/test-installation-package.ps1:7–28 omits Setup-DEPO.cmd, infra/windows/setup-depo.ps1 and infra/windows/install-checkpoints.ps1 from requiredFiles. Its documented-path matcher at :65 recognizes selected extensions but not .cmd. The current package check passes despite the Git-index gap in R2.

Impact: a structural validation pass can give false confidence about completeness of the advertised customer installation path.

Required correction: include the guided launcher and required helpers in package validation. Test an assembled artifact with each required file omitted and verify rejection before application shutdown. Run the gate against the release artifact rather than only the development working tree.

### R4 — Medium: prerequisite regression script fails before testing prerequisites

Reproduction: powershell.exe -NoProfile -ExecutionPolicy Bypass -File infra/windows/test-install-prerequisites.ps1

Observed: exit code 1. The isolated fixture copies install-depo.ps1 at test-install-prerequisites.ps1:33 but omits native-install-command.ps1, which the copied installer imports at :15. PowerShell raises CommandNotFoundException before the intended prerequisite assertions execute.

Impact: this script currently supplies no assurance that supported/unsupported Python, Node and npm inputs are handled correctly. This is a stale test fixture; it does not establish that production installation lacks the helper.

Required correction: update the fixture to include the installer's actual helper/config dependencies, keep all package installation and database operations stubbed, then rerun every prerequisite assertion.

### R5 — Medium: guide mixes guided setup and manual session instructions

Evidence: INSTALLATION.md:3–13 describes automatic workstation credentials, local browser access and a single customer launcher. Later sections prescribe manual credential import and reconnecting after fifteen minutes (notably :517 and :2582–2612). Some of these sections concern delegated central sessions, but the repeated first-install instructions do not consistently separate that deployment mode from local workstation setup.

Impact: customers can follow obsolete or wrong-mode instructions, manually reapply credentials, or interpret an expected ontology review notice as a failed installation. The guide also exposes retired internal combined-upgrade terminology at :29.

Required correction: consolidate one guided workstation procedure and one explicitly separate manual/gateway procedure. Explain session behavior by authentication mode. Separate application installation success, optional ontology draft review, publication verification and LLM inference acceptance. Keep database backup/restore requirements explicit. Check every documented command from a fresh terminal, including paths with spaces and a restricted execution policy.

## Checks and results

| Check | Result |
| --- | --- |
| Offline installation package structure | Pass: 83 PowerShell scripts, 37 documented paths, 10 APIs, 3 workers, 199 locked Python distributions, 13 PostgreSQL migrations |
| Python installation contracts, customer entry points and audit logging | 27 passed; JUnit: outputs/enterprise-audit-2026-10-20/installation-customer-review-tests.xml in the task workspace |
| test-setup-config.ps1 | Pass: configuration quoting/round trip and invalid input rejection |
| test-install-checkpoints.ps1 | Pass: resume, failed-stage isolation, changed inputs/inventory, force and Node major-version cases |
| test-upgrade-flow.ps1 | Pass: advanced updater ordering, preflight rejection, child failure handling and preserved settings |
| test-stale-tracking.ps1 | Pass: five process identity cases |
| test-startup-control.ps1 | Pass: descendants, listener ownership/binding, cleanup and unrelated-process protection |
| test-depo-update.ps1 | Pass: upgrade sequencing, timeout synchronization, idempotence and failed-stage stop |
| test-install-prerequisites.ps1 | Fail: missing native command helper in isolated fixture |

These are offline checks and isolated fixtures. They do not substitute for a clean Windows VM installation or live database upgrade certification.

## Behaviors confirmed by inspection

- Setup-DEPO.cmd invokes PowerShell with process-scoped ExecutionPolicy Bypass and propagates its exit code. Setup respects enforced organization policy rather than changing machine policy.
- Node discovery requires Node.js 24 or higher; Python prerequisites require CPython 3.12 x64.
- Guided setup documents PostgreSQL and Neo4j engines plus the application database/role as prerequisites; it does not claim to install those engines.
- Application stop/restart uses process identity guards. Do not bypass those guards to recover a stale PID record.
- Installation has successful-stage receipts and retained audit logs. Imports, configuration, migrations and readiness are still checked; frontend source is rebuilt.
- Ontology upgrade staging retains existing publications and requires lifecycle review for corrected drafts. An upgrade-review notice is not, by itself, an installation failure.

## Remaining release acceptance

After the findings are fixed, build the release from its committed source and run the customer launcher on a clean Windows machine. Verify first installation, second unchanged run, interrupted dependency installation/resume, invalid upgrade configuration without downtime, PostgreSQL migration failure recovery, Neo4j unavailability, restricted execution policy, paths containing spaces, credential retention and log redaction. Validate successful restart, browser authentication and an import-to-publication workflow using test data. Verify backup/restore against the release's schema versions before upgrading customer data.

The available workstation evidence previously showed model inference blocked by HTTP 429. Do not describe agent/LLM end-to-end acceptance as passed until a configured provider completes a real request. Linux, remote/gateway deployments, fresh database-engine installation and enterprise signing policies were not exercised end to end in this review.

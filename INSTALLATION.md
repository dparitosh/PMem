# DEPO customer installation

Use **Setup-DEPO.cmd** from the complete release folder for Windows installation, update, repair, Start, Stop and Restart. You do not need to run internal scripts individually. For Linux, gateways, remote databases and optional components, see the [operator reference](docs/installation/OPERATOR_REFERENCE.md).

## 1. Prepare the machine

| Prerequisite | Required before Setup |
| --- | --- |
| Windows access | The account can inspect processes and listeners using CIM/WMI and Get-NetTCPConnection. Use an authorized administrator session if host permissions require it. |
| Python | CPython 3.12, 64-bit. |
| Node.js | Version 24 or higher, with npm 10.2 or higher. |
| PostgreSQL | PostgreSQL 16 running, with an existing application database and role permitted to run the documented schema migrations. |
| Neo4j | A running compatible database, with its URI, database name, user and password available. |
| Release files | Extract the complete matching release into a writable application directory, for example `D:\GenAI_Projects\Apps\PMem`. |
| AI features | A reachable LLM and embedding provider. Ollama needs the selected models installed locally; hosted providers need valid credentials and available quota. |

Setup discovers PATH tools and supported adjacent portable Python312/NodeJS folders. It checks versions before installing dependencies. It does not install database engines or create database users. Provision those first using the operator reference. Dependency installation needs access to the package sources configured for your deployment.

## 2. Install

1. Open the extracted release folder and double-click **Setup-DEPO.cmd**.
2. Choose **1 — Install / update / repair**.
3. On first use, enter the PostgreSQL and Neo4j connections. Password entry is hidden. Remote Neo4j connections require verified TLS.
4. Wait for setup to finish. It validates the release, configuration, prerequisites and artifact storage before stopping application processes. Existing deployments also receive read-only database upgrade checks before shutdown.
5. Confirm **DEPO Windows installation completed successfully**, then open the frontend URL reported by the installer. The default workstation address is `http://127.0.0.1:3000/`.

First-run connection values are validated before staged configuration is promoted. Setup generates application keys and applies credentials when PostgreSQL credential storage is enabled. Ordinary updates retain existing keys.

There are two configuration files:

- Root `.env.local`: database connections, server keys and provider settings. Keep it private.
- `frontend/.env.local`: public browser routing only. Never put provider keys, database passwords or Admin keys in frontend/VITE variables.

New workstation setup enables the loopback browser broker, so users do not paste an Admin key into the browser. Existing manual/gateway authentication settings are preserved. Manual delegated sessions are explained in the operator reference; do not repeat manual credential import after successful guided setup.

Every guided action starts PowerShell with process-scoped ExecutionPolicy Bypass. Machine policy is unchanged. If organization policy requires signed software, use an approved signed release; do not disable organization policy.

## 3. Verify the application

- Open the reported frontend URL and confirm services are available.
- Select an ontology and inspect its classes and namespaces.
- Import a test schema and its dependencies, review the draft, and verify its publication job and Neo4j graph after approval.
- Test an instance import, review its ontology links, and complete its approved graph load.
- Send a small request to the configured LLM. HTTP 429 or unavailable local models means AI verification is incomplete even if installation succeeded.

An **ontology upgrade review** notice means corrected drafts require review. It is not an installation error. Review `logs/installation/ontology-upgrade-v2/plan.json` through Ontology Junction lifecycle controls. Existing publications remain until reviewed replacements are published. Setup does not automatically approve mappings, replace active publications or relink existing instances.

In Admin → Maintenance, **Clear Import Workflows** removes quiescent instance-import and schema-set task history, task-owned files and PostgreSQL artifact manifests. Full Schema Cleanup includes this operation. Running tasks and uncertain publication outcomes block cleanup. Graph Reset alone retains Import history. Published ontology artifacts, data products and separate agent audit history are retained. Small deletion receipts prevent stale workers from restoring cleared workflows.

## 4. Start, stop and restart

Open **Setup-DEPO.cmd** and choose **Start**, **Stop** or **Restart**. Application lifecycle commands leave PostgreSQL and Neo4j servers running. Rerun Install/update/repair after changing source files or dependencies.

For command-line use, run the required action individually from the release root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Restart
```

## 5. Update or repair

1. Back up PostgreSQL, Neo4j, durable artifacts and configuration. Confirm the restore procedure for the current schema version.
2. Place the complete matching release in the application directory, preserving both environment files, customer uploads and durable data. Use a maintenance window when replacing a running release.
3. Run **Setup-DEPO.cmd → Install / update / repair**. Do not manually stop services before its preflight.
4. Verify services and the browser workflow again. Review any staged ontology upgrades separately.

Dependency receipts in `logs/installation/checkpoints` let setup reuse verified installations and retry failed stages. Configuration checks, imports, migrations and readiness still run; frontend source is rebuilt. Do not delete configuration or databases to retry installation.

For dependency corruption requiring a forced reinstall:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -ForceReinstall -Action Setup
```

This preserves configuration and data. Review migration history and backups after a schema migration failure. Do not restart an older release against a newer schema without a reviewed rollback procedure.

## 6. Resolve errors

Setup retains timestamped `.log` and `.jsonl` files in `logs/installation/runs` and reports the exact log path. Dependency and service startup logs are retained under `logs/installation`; consult the reported paths. Installation logging redacts credentials; still review diagnostic bundles before sharing externally.

| Symptom | Next action |
| --- | --- |
| PowerShell blocked | Use Setup-DEPO.cmd. If signing policy overrides process bypass, obtain an approved release from the administrator. |
| Python/Node/npm rejected | Install the required version. Setup accepts `-Python` for an explicit executable; Node discovery settings are in the operator reference. |
| PostgreSQL timeout/refused | Check server availability, configured database, user, TLS and role privileges. |
| Neo4j unavailable | Check the selected database, URI, credentials and TLS. |
| Process inspection or PID identity rejected | Use an account permitted to inspect processes/listeners. Inspect the recorded process; never kill unrelated PIDs or bypass ownership checks. |
| Installation fails | Correct the first error in the audit log, then rerun the same launcher. Failed preflight leaves PMem running; failures after shutdown can leave it stopped until repaired. |
| Browser cannot connect | Check frontend/backend readiness and the configured authentication/routing mode. Run diagnostics below. |
| LLM returns 429 | Check provider quota/rate limits or configure another working supported provider. AI acceptance remains incomplete. |

Read-only diagnostics from the release root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase Package
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase All -EnvFile .\.env.local
```

`Package` validates files offline. `All` also requires configured dependencies and running services. Readiness does not establish that every business workflow passed.

Root update and diagnostic commands retain audit logs under `logs/installation/runs`, use process-scoped execution-policy handling and preserve their selected environment/Python arguments. When using a custom `-EnvFile`, early audit messages redact secrets from that file as well as the default server file. These logs are operational evidence; maintenance does not automatically erase them.

## Advanced operations and customer release

The [operator reference](docs/installation/OPERATOR_REFERENCE.md) covers manual/gateway setup, schema maintenance, service isolation, Linux, optional Spark/OCR and detailed verification. Operator entry points are root `configure-depo.ps1`, `install-depo.ps1`, `update-depo.ps1`, `manage-depo.ps1`, `diagnose-depo.ps1` and `certify-depo-release.ps1`. Scripts under `infra` implement supported stages and optional features.

Build releases from the reviewed commit and validate the actual artifact. Before customer rollout, test a clean Windows machine, paths with spaces, execution policy, first install, unchanged rerun, interrupted installation/resume, rejected upgrade without shutdown, credential retention, backup/restore, restart and import-to-publication. Record separate database, browser and LLM acceptance evidence. Local regression tests alone do not certify a customer release.

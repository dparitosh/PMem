# DEPO customer installation

Follow this runbook in order. Commands use `E:\App\PMem` as the example release root; replace that directory with your installation location. Use **Setup-DEPO.cmd** for Windows installation, update, repair, Start, Stop and Restart. Linux, gateways, remote databases and optional components have separate procedures in the [operator reference](docs/installation/OPERATOR_REFERENCE.md).

## 1. Prepare the machine

### 1.1 Check the complete release

Extract a complete matching release. For an existing deployment, complete section 5's backup steps before replacing files. Do not mix scripts from different releases.

| Exact relative path | Role |
| --- | --- |
| `Setup-DEPO.cmd` | Customer menu; invokes Windows PowerShell with process execution-policy handling. |
| `infra\windows\setup-depo.ps1` | Guided configuration, upgrade preflight, tracked application shutdown and complete installation. |
| `install-depo.ps1` | Root orchestrator: dependencies, migrations, application credentials, graph schema and readiness. |
| `infra\windows\install-depo.ps1` | Internal dependency helper, called automatically. Do not run it as a complete installation. |
| `infra\deployment\services.json` | API and worker runtime manifest. |
| `backend\requirements-lock.txt`, `frontend\package-lock.json` | Reviewed dependency locks; keep these files with the release. |
| `infra\postgres\migrations\` | Versioned PostgreSQL migration `.sql` files. |

The two files named `install-depo.ps1` have different purposes. Run the customer launcher once; do not run both scripts manually.

### 1.2 Install and start prerequisites

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

### 1.3 Open the correct working directory

In Windows PowerShell, run this line **before** any relative-path command:

```powershell
Set-Location -LiteralPath 'E:\App\PMem'
```

Then check the release and prerequisites:

```powershell
Test-Path -LiteralPath '.\Setup-DEPO.cmd'
py -3.12 --version
node --version
npm.cmd --version
```

Expected: `True`, Python 3.12.x, Node v24.x or newer, npm 10.2 or newer. Portable tools can use explicit paths; guided setup accepts `-Python 'C:\Path\To\Python312\python.exe'`. Setup does not install Python/Node engines or register every API as a Windows service.

## 2. Install

### 2.1 Choose the installation scenario

- **New installation:** complete section 1; have the existing PostgreSQL application database/role and running Neo4j connection ready. Setup prompts for connections and generates application keys.
- **Existing deployment:** back up and preserve root `.env.local`, `frontend\.env.local`, databases and durable artifacts as described in section 5. Keeping the original root file retains deployed application keys.

### 2.2 Launch setup

1. Open the extracted release folder and double-click **Setup-DEPO.cmd**.
2. Choose **1 — Install / update / repair**.
3. On first use, enter the PostgreSQL and Neo4j connections. Password entry is hidden. Remote Neo4j connections require verified TLS.
4. Wait for setup to finish. It validates the release, configuration, prerequisites and artifact storage before stopping application processes. Existing deployments also receive read-only database upgrade checks before shutdown.
5. Confirm **DEPO Windows installation completed successfully**, then open the frontend URL reported by the installer. The default workstation address is `http://127.0.0.1:3000/`.

From PowerShell, the equivalent setup command is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Setup
```

From Command Prompt, change both drive and directory before running the menu:

```bat
cd /d E:\App\PMem
Setup-DEPO.cmd
```

Choose one method and wait for completion. Do not run concurrent installers.

### 2.3 Review configuration and credential policy

First-run connection values are validated before staged configuration is promoted. Password prompts are hidden; remote Neo4j requires verified TLS. Existing configuration files are reused.

Guided setup defaults to `-CredentialPolicy Synchronize`. When `AUTH_MODE=token` and `DEPO_CREDENTIAL_STORE=postgres`, root `.env.local` supplies the desired application credentials. Missing profiles are created; changed keys or actor/expiry metadata are updated atomically; matching keys and omitted profiles are retained. Repeating setup with the same file does not rotate matching keys. Changed keys require dependent clients to reconnect.

To reject replacements instead, use this explicit validation command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Setup -CredentialPolicy Validate
```

The advanced root `install-depo.ps1` remains validation-only unless `-ReplaceExistingCredentials` is supplied. PostgreSQL schema migration and credential synchronization are separate stages. PostgreSQL stores salted key digests and cannot recover an old plaintext key into a lost environment file. Database passwords, Neo4j credentials and provider keys remain server configuration; they are not application credential profiles.

There are two configuration files:

- Root `.env.local`: database connections, server keys and provider settings. Keep it private.
- `frontend/.env.local`: public browser routing only. Never put provider keys, database passwords or Admin keys in frontend/VITE variables.

New workstation setup enables the loopback browser broker, so users do not paste an Admin key into the browser. Existing manual/gateway authentication settings are preserved. Manual delegated sessions are explained in the operator reference; do not repeat manual credential import after successful guided setup.

Every guided action starts PowerShell with process-scoped ExecutionPolicy Bypass. Machine policy is unchanged. If organization policy requires signed software, use an approved signed release; do not disable organization policy.

### 2.4 Follow the stages and expected results

| Order | Installer action | Expected result |
| --- | --- | --- |
| 1 | Check release, configuration, Python/Node versions and writable artifact storage; existing deployments receive database upgrade preflight checks. | Preflight passes before application shutdown. |
| 2 | Stop tracked frontend/backend processes using ownership checks. | PostgreSQL and Neo4j servers remain running. |
| 3 | Install/reuse verified Python/npm dependencies and build frontend source. | Dependency checks pass; `frontend\dist\index.html` exists. |
| 4 | Start selected PostgreSQL runtime when configured; check connectivity and deployment mode. | Database is reachable and existing/new mode is reported. |
| 5 | Run PostgreSQL schema migrations through the lifecycle scripts. | Required migrations pass; the database is not recreated. |
| 6 | Apply the selected application credential policy. | Atomic validation/synchronization passes. |
| 7 | Provision/validate Neo4j schema and start APIs/workers. | Backend readiness passes. |
| 8 | Start/verify frontend and stage ontology upgrade review where applicable. | Actual frontend URL and installation success are printed. |

Expected final messages include `DEPO Windows installation completed successfully` and `Setup finished`. Follow section 3 before treating the application workflow as accepted.

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
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Stop
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Restart
```

## 5. Update or repair

1. Back up PostgreSQL, Neo4j, durable artifacts and configuration. Confirm the restore procedure for the current schema version.
2. Place the complete matching release in the application directory, preserving root `.env.local`, `frontend\.env.local`, customer uploads and durable data. Use a maintenance window when replacing a running release. Review intentional credential changes before setup; guided synchronization applies them to PostgreSQL.
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
| PostgreSQL migration failed | Read the structured SQLSTATE/action, correct privileges or incompatible schema, then retry setup with the database/configuration retained. |
| Application key mismatch | Guided Synchronize updates supplied profiles from root `.env.local`. Validate mode and the advanced installer reject differing keys; preserve the original file or deliberately select synchronization. |
| Engineering conversion result exceeds its limit | Generated output is separate from upload size. The worker spools its result to a temporary file and checks `ENGINEERING_CONVERSION_MAX_RESULT_BYTES` before decoding. Default: 268435456 bytes (256 MiB); maximum: 1073741824 bytes (1 GiB). If necessary, set a larger integer in root `.env.local` within server memory capacity and restart the backend, or narrow the schema set. Conversion failure occurs before ontology registration. |
| Script not found | First change to the release root; verify the exact `.ps1`/`.cmd` path. Restore the complete matching release if missing. |
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

# DEPO customer installation

Lineage/projection updates include `backend/depo_platform/product_lineage.py` and `artifact_references.py`. Deploy them with the owning catalog/product/graph code through the normal `update-depo.ps1` workflow and restart services; release preflight verifies their presence. No new PostgreSQL table, credential rotation or automatic data deletion is required. Product source references now resolve through configured `ONTOLOGY_SERVICE_URL` and `DATA_PIPELINE_SERVICE_URL`. Retention refuses referenced/provenanced artifacts; do not bypass that protection by deleting files manually. See [lineage and projection qualification](docs/audits/lineage-projection-fixes-2026-10-29.md).

For ontology upgrades, follow [Ontology release versions](docs/ONTOLOGY_RELEASES.md): register a replacement, declare its family/version/predecessor, validate and review, then approve/publish separately. `update-depo.ps1` installs the code; it does not invent versions or migrate mappings automatically. Release records use the existing PostgreSQL registry table. Preserve that table, ontology files and graph receipts together in backups; see [local recovery qualification and remaining gates](docs/audits/recovery-qualification-2026-10-29.md).

For a destructive test-environment reset, use [Reset to vanilla state](docs/VANILLA_RESET.md). This separately confirmed Admin operation clears application records, agent/workflow history and retained uploads while preserving credentials and the embedded foundation. Installation and update never perform this reset automatically.

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

Choose one method and wait for completion; do not run concurrent installers. From PowerShell, the equivalent setup command is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Setup
```

From Command Prompt, change both drive and directory before running the menu:

```bat
cd /d E:\App\PMem
Setup-DEPO.cmd
```

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

### Public access through APIM or a reverse proxy

Follow the [ordered gateway configuration and application-VM examples](docs/installation/OPERATOR_REFERENCE.md#public-access-through-apim-or-a-reverse-proxy). They separate public browser routing from private service addresses and include verification before restart.

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

For model-assisted investigations, set `AGENTIC_MODEL_CONTEXT_TOKENS` in the repository-root `.env.local`
to the selected provider/model's verified usable context window before restarting services. The example
value is `32768`; this is a configuration limit, not automatic detection of the model's capacity.
Requests use a conservative UTF-8 token upper bound, reserving the requested completion and 2,048 tokens
for framing. Oversized prompts stop before inference; narrow the evidence/tool selection rather than
raising the limit above the model's supported window. Goal memory retains observation identities and
prioritizes recent results; omitted or partial results are explicitly marked. A `needs input` outcome
asks for missing source fields and performs no write. Supply them and start a new investigation.
Model summaries remain advisory: valid evidence references do not independently verify every claim.
Shared service credentials represent one principal; use individual identities for person-specific history.

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
4. Verify services and the browser workflow again. Review ontology upgrades and `logs/installation/ceim-upgrade-review/plan.json` separately. For `update-depo.ps1` commands, index updates and PMI regeneration, follow the [existing-customer procedure](docs/installation/OPERATOR_REFERENCE.md#existing-customer-update-indexes-and-pmi-rules).

Dependency receipts in `logs/installation/checkpoints` let setup reuse verified installations and retry failed stages. Configuration checks, imports, migrations and readiness still run; frontend source is rebuilt. Do not delete configuration or databases to retry installation.

For an existing customer deployment, run these commands **in sequence** from `E:\App\PMem` after placing the complete matching release:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\update-depo.ps1 -EnvFile .\.env.local -PreflightOnly
```

Continue only after preflight passes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\update-depo.ps1 -EnvFile .\.env.local
```

Use `-InstallDependencies` on the second command when dependency files changed. Do not use `-SkipFrontend` for this release's import, workflow-access or graph-display fixes. The updater validates agentic settings before shutdown, applies pending database migrations/indexes, rebuilds the UI and restarts services. It retains credentials, artifacts, workflow history and publication decisions. It does not replay failed imports or approve pending mappings.

Ontology inspection now uses `backend/Services/ontology_semantic_runtime.py`; the former optional Owlready runtime is removed. Semantica 0.6.7 is already pinned in `backend/requirements.txt`, `backend/requirements-lock.txt` and the ontology, graph and schema-sets service profiles. Do not install Owlready to resolve an ontology error. If those service environments predate the pinned profiles, run `update-depo.ps1 -EnvFile .\.env.local -InstallDependencies`. Lightweight conversion services can inspect asserted RDF with RDFLib; their result explicitly reports when Semantica validation has not run. Structural validation does not prove logical consistency. Existing SHACL, OWL-RL, lifecycle and publication checks remain separate.

OSLC read endpoints negotiate `application/json`, `text/turtle`, `application/rdf+xml` and `application/ld+json` using the `Accept` header. For example, request a built-in requirements shape with `Accept: application/ld+json` at `/oslc/shapes/requirements` under the configured OSLC service base URL. JSON-LD responses can be arrays or objects. Ontology JSON-LD input must use inline contexts: remote `@context` URLs and `@import` are rejected before parsing, including during legacy namespace detection and OSLC shape projection. Bundle the context definitions locally when preparing an offline customer deployment. This policy is separate from bounded remote XSD dependency resolution.

After success, press Ctrl+F5, choose **Revalidate access**, then check Import, Ontology Junction's Semantic Bridge, all four Graph Explorer views, Knowledge Companion and Recommendations. Confirm pending publication is distinguished from completed validation. Review a retained workflow before retrying an uncertain write. Customer acceptance requires these checks against the customer's URLs, credentials and data; an offline regression pass does not replace them.

### Customer browser errors and release acceptance

Use the [browser error and frontend-rebuild procedure](docs/installation/OPERATOR_REFERENCE.md#customer-browser-errors-after-an-update) and the [page reliability and authorization acceptance checks](docs/installation/OPERATOR_REFERENCE.md#deploying-the-page-reliability-and-authorization-fixes). Deploy the complete matching backend and frontend; do not disable authentication or clear workflow history to repair access.

For dependency corruption requiring a forced reinstall:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -ForceReinstall -Action Setup
```

This preserves configuration and data. Review migration history and backups after a schema migration failure. Do not restart an older release against a newer schema without a reviewed rollback procedure.

## 6. Resolve errors

### Browser registry, listener, CORS and reconnect failures

`No usable service response` means the browser could not expose an HTTP response. It does not prove an invalid API key. Browser JavaScript cannot distinguish a refused connection, a firewall/proxy failure and a CORS-blocked response from that error alone. A visible HTTP 401/403 is a different, authentication-related result. An HTTP 503 indicates a reachable service reporting unavailability.

Use this sequence on the deployed server; substitute the actual release directory for `E:\App\PMem`:

1. Open PowerShell and run `Set-Location 'E:\App\PMem'`. Keep the existing root `.env.local`; do not regenerate credentials to repair a network error.
2. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -EnvFile .\.env.local`. Inspect the first failed stage and its reported log path. Confirm the application listener address matches `DEPO_SERVICE_HOST`. Backend peer URLs and browser-facing gateway URLs have different reachability requirements.
3. Inspect listeners with `Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 8011,8014 } | Select-Object LocalAddress,LocalPort,OwningProcess`. A listener on `127.0.0.1` cannot receive connections addressed to the server's private network IP. Do not kill an unverified process or remove PID tracking files.
4. Set `ALLOWED_ORIGINS` to every exact browser origin in root `.env.local`, for example `http://127.0.0.1:3000,http://localhost:3000,https://portal.example.com`. Scheme, host and port must match; no paths, trailing slash or `*`. CORS does not open Windows Firewall ports and does not authorize API operations.
5. After changing backend configuration, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Restart -EnvFile .\.env.local`. This uses managed process identity checks; database servers remain running. For browser URL/build changes use the documented installer/update procedure so the frontend routing is regenerated.
6. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\test-depo-deployment.ps1 -EnvFile .\.env.local`. The current diagnostic validates service readiness and authenticated CORS preflight for **every** configured origin, including `Authorization`, `Content-Type`, `X-API-Key` and `X-Request-ID`. Preflight itself sends no credentials and executes no write.
7. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-browser-session.ps1 -EnvFile .\.env.local`. For the configured gateway add `-Gateway`. It creates and disconnects a temporary read-only session; it does not approve or publish data. Local success does not establish that a customer browser can reach the gateway.
8. From the actual customer browser, inspect DevTools → Network. Confirm the ingestion registry request `/api/v1/ontology/registered` routes to ingestion and `/api/v1/ontologies` routes to ontology. Confirm OPTIONS succeeds, the returned `Access-Control-Allow-Origin` matches the page origin, and the response request ID is visible. For a public frontend use externally reachable HTTPS gateway URLs; private `10.x.x.x` addresses and HTTP services behind an HTTPS page will fail for external users.

The local session broker is available only with loopback frontend binding and local routing. It grants only configured scopes, uses a bounded 12-second authority read timeout, and does not expose its administrator key. Public/gateway deployments use their configured authentication flow. Revalidate access preserves the last visible registry while refreshing; expiry, sign-out, identity replacement and explicit schema cleanup clear it. Failed registry reads display an error or partial-list warning and are not proof that artifacts were deleted.

### Semantic validation scope

RDFLib remains required for RDF/XML, Turtle, JSON-LD, graph operations and serialization, including paths used inside Semantica 0.6.7. Semantica provides structural checks and SHACL data validation. Neither successful parsing nor a structural/SHACL result proves full OWL-DL logical consistency. DEPO now includes a separate HermiT worker; capability `owl_dl_consistency_supported` is true only when Java 17+ and the digest-verified worker are available. Ordinary asserted inspection still returns `consistency_verified=false`; an explicit consistency check has its own executed result and artifact/foundation scope.

After an upgrade, follow [Semantic evidence in engineering work](docs/SEMANTIC_DECISION_LOOP.md) to verify the closed review loop. Deploy the complete source release, then run the normal repository-root `update-depo.ps1` path to verify the runtime, rebuild the frontend and restart services. This change requires no new SQL migration or database reset. Preserve the complete foundation bundle and verified reasoner JAR/manifest. Restart the owning services after updating code; do not copy only the frontend. Existing agent investigations pin source and semantic dependency revisions and can require a new review after an upgrade. Use the current-evidence endpoint before claiming a prior check still applies. Product and Data Flow model panels are advisory; existing approved semantic-release, instance-validation and delivery-receipt checks remain separate.

Do not remove RDFLib from requirements or relabel structural validation as a reasoner result. See [embedded foundation and OWL-DL operation](docs/EMBEDDED_SEMANTIC_FOUNDATION.md) for the bundled IDO/DEPO vocabulary, Java prerequisite, build/release sequence, offline import rules, memory/deadline bounds and agent/UI behavior. Timeouts, missing imports and unsupported inputs never become successful consistency checks. Existing customer ontologies are not automatically remapped or certified by this update.

### Schema upload configuration

For generated-output limits, see [large ontology configuration](docs/installation/OPERATOR_REFERENCE.md#large-ontology-configuration). For supplier schema URLs, offline companions, examples and network limits, see [XSD schemas with remote dependencies](docs/installation/OPERATOR_REFERENCE.md#xsd-schemas-with-remote-dependencies). Supply local companions when remote access is unavailable; do not publish an incomplete schema set.

### Installation and service error recovery

For schema update failures, follow [PostgreSQL migration error records](docs/installation/OPERATOR_REFERENCE.md#postgresql-migration-error-records). Logs retain the migration filename, SQLSTATE and available database-object identifiers; PowerShell errors retain their original source location and stack.

**Import task snapshot reports `WinError 5` / access denied:** this release uses unique temporary files, OS-managed task locks and bounded sharing retries. It retains the last committed snapshot and its matching parsed rows if replacement fails. Persistent failures are reported as a storage warning; a failure during graph loading leaves the outcome requiring review rather than automatically offering a duplicate load. Existing task snapshots and legacy parsed-row pointers remain readable; no history reset is required.

If the error persists after update, check **Modify** permission on `E:\App\PMem\uploads\.import_tasks` for the account actually running ingestion, including its existing files. Check antivirus/backup/file-viewer locks using your Windows administration tools. Do not delete task JSON or lock files to bypass an active operation, grant access to Everyone, or rerun an uncertain graph commit. OS locks release when the owning process exits; an old lock-file name alone does not indicate an active lock. Review the retained task and graph outcome after storage is repaired. Full Import cleanup still removes task-owned sidecars after its normal quiescence checks.

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
| Public frontend loads but API calls to `10.x.x.x:8011` / `:8012` time out | Browser routing still points at private services. Follow the public gateway procedure above, verify proxy routes, restart the frontend launcher and hard-refresh. Increasing request timeouts or changing database indexes does not repair unreachable routing. |
| LLM returns 429 | Check provider quota/rate limits or configure another working supported provider. AI acceptance remains incomplete. |
| STEP import validates but is absent from Neo4j | Open its **View Data Flow** link. Select an approved semantic release in **Approval & publication**, then publish the completed run. Validation is separate from graph publication; check the retained receipt before retrying a write. |
| CEIM batch exceeds its record bound | Validation and publication accept at most 50,000 entities plus relationships combined per batch. Upload byte limits are separate. Use a supported partitioned workflow or a smaller source export; do not truncate the normalized batch and claim a complete import. |
| STEP DATA section is missing ENDSEC | Check the original source ends with `ENDSEC;` and `END-ISO-10303-21;`. A truncated export requires re-export from the source application. |
| Governed source import times out before returning a run ID | Inspect retained Data Flow runs and source artifacts before retrying. Very large synchronous STEP parsing remains a scalability constraint; a timeout is not evidence of a successful or failed graph write. |

Read-only diagnostics from the release root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase Package
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase All -EnvFile .\.env.local
```

`Package` validates files offline. `All` also requires configured dependencies and running services. Readiness does not establish that every business workflow passed.

Bounded semantic-source validation can run with `DEPO_SPARK_ENABLED=false`; Spark-specific distributed jobs still require the optional Spark runtime. Canonical publications use document-specific snapshot scopes by default, so separate component files do not replace each other. Existing publication intents retain their original destination. Ontology registration/publication and linking source instances to ontology classes are separate workflows; an AP242 filename alone does not establish semantic alignment.

Root update and diagnostic commands retain audit logs under `logs/installation/runs`, use process-scoped execution-policy handling and preserve their selected environment/Python arguments. When using a custom `-EnvFile`, early audit messages redact secrets from that file as well as the default server file. These logs are operational evidence; maintenance does not automatically erase them.

## Advanced operations and customer release

The [operator reference](docs/installation/OPERATOR_REFERENCE.md) covers manual/gateway setup, schema maintenance, service isolation, Linux, optional Spark/OCR and detailed verification. Operator entry points are root `configure-depo.ps1`, `install-depo.ps1`, `update-depo.ps1`, `manage-depo.ps1`, `diagnose-depo.ps1` and `certify-depo-release.ps1`. Scripts under `infra` implement supported stages and optional features.

Build releases from the reviewed commit and validate the actual artifact. Before customer rollout, test a clean Windows machine, paths with spaces, execution policy, first install, unchanged rerun, interrupted installation/resume, rejected upgrade without shutdown, credential retention, backup/restore, restart and import-to-publication. Record separate database, browser and LLM acceptance evidence. Local regression tests alone do not certify a customer release.

## Feature-specific verification

The [governed mapping feedback workflow](docs/GOVERNED_LEARNING.md) uses the existing agentic service and PostgreSQL registry. No new migration, credential, broker or LLM provider is needed. Deploy `backend/agentic_service/learning_review.py` and `learning_router.py` together with their service/catalog/frontend changes; release preflight requires both modules. In Semantic Bridge, expand **Learning from reviewed mappings** after publication. Verify feedback → pending hint → authorized approval → revision-scoped reuse → revocation. An amended assessment must preserve the original audit record and invalidate hints based on that older assessment. Do not label review counts as model accuracy or enable model training to test this flow.

For the L0–L4 semantic/context fixes, deploy the complete release using the existing repository-root `update-depo.ps1`; no PostgreSQL schema reset or credential rotation is required. Release preflight now also requires `backend/depo_platform/semantic_support.py`, `backend/ontology_service/semantic_merge.py` and `backend/agentic_service/selected_record.py`. Keep the bundled `backend/ontology_service/resources/reasoner/depo-owl-dl.jar` and its `manifest.json` from the same release.

After restart, verify Data Flow run selection and Data Products version selection before opening the Companion. Switching the selected record must reset its conversation; a failed selected-record read must not display an unrelated record. A semantic hold surviving reconnect/restart is intentional: resolve the class/model conflict and create a new reviewed proposal. For an incomplete unsatisfiable-class list, run the ontology consistency operation with the exact `target_iri`; an absent class remains unknown. If publication reports a graph/artifact revision mismatch, review and republish the retained ontology rather than clearing credentials or deleting data. See [L0–L4 remediation and storage ownership](docs/audits/l0-l4-remediation-2026-10-28.md).

If the frontend is ready but **Existing ontology upgrade review** reports `WinError 10061`, the ontology inventory connection was refused. Frontend readiness does not establish ontology service availability. Verify that `ONTOLOGY_SERVICE_URL` in the selected `.env.local` points to the running service listener. For a backend bound specifically to `10.0.2.16`, the direct peer URL is `http://10.0.2.16:8011/api/v1`; use that example only when it matches the actual backend binding. Keep the configured gateway URL when routing through a gateway. Inspect `logs/windows-services/ontology.err.log` and `ontology.out.log`, restore the service or correct the peer URL, then rerun the same repository-root updater. Existing publications and the previous review plan are retained. The updated reviewer logs its chosen endpoint and retries transient inventory reads within a bounded budget; registration writes are not automatically retried.

For engineering similarity, change-dependency paths and decision-policy examples, follow the [engineering recommendation review](docs/recommendation-engineering-review.md). The complete release must include `backend/graph_service/recommendation_engine.py`, `backend/graph_service/engineering_comparison.py` and `backend/Services/recommendation_compat.py`; the normal updater verifies them and rebuilds the customer UI. Domain policies are reviewed configuration and are not installed automatically. Direct graph analysis can run while the configured language model is unavailable; agent investigation requires the model.

The [Recommendations customer audit](docs/recommendations-customer-audit.md) records input, browser, session, agent, evidence, process-scope and decision-policy checks plus the remaining customer acceptance procedure. Deploy the matching frontend and backend together; Process Context now applies scope before limiting neighbors and reports bounded coverage. A passed local suite does not establish customer API authorization or model availability.

After installation, use the [operator reference](docs/installation/OPERATOR_REFERENCE.md) for ontology governance, microservice checks, credentials, browser access, XMI import and PLM Companion acceptance. The [PLM response contract](docs/PLM_COMPANION_RESPONSE_CONTRACT.md) contains the implemented system instructions and evidence rules. For the optional separate AOI provider, follow [AOI adapter configuration from PMem](docs/installation/AOI_GATEWAY.md).

## Taxonomy browser performance update (29 October 2026)

Deploy the complete release through the repository-root `update-depo.ps1` with the existing customer environment file. Include `backend/ontology_service/domain/taxonomy.py`, `backend/ontology_service/domain/taxonomy_cache.py`, `backend/ingestion_service/api/ontology_browser.py`, `backend/depo_platform/release_code_check.py` and the rebuilt frontend together. Do not copy only the frontend bundle; the new browser uses taxonomy limit/offset/query parameters. Startup rejects a release missing the cache module.

Ontology Junction requests 500 terms per slice. Use Previous/Next terms or the taxonomy search field to access additional retained terms. Relationships and hierarchy describe the displayed slice, not a complete logical closure. Export remains available for the retained artifact.

The first browse builds a disposable gzip cache beside the retained ontology artifact (`.<artifact-name>.taxonomy-v1.json.gz`). Subsequent process starts validate source content digests, ontology metadata, implementation and RDFLib version before reusing it. Corrupt or mismatched caches rebuild automatically; unavailable cache writes do not prevent browsing. This cache is not a publication receipt, approval record or OWL-DL consistency result. Existing credentials, schema and graph data are preserved; no migration or new dependency is required for this change.

### Change Control visibility

The workflow follow-up patch also updates `backend/data_pipeline_service/router.py` and `frontend/src/pages/DataFlowPage.js`: access revalidation supersedes pending page reads, and retrying a retained replay reference can recover its existing status even if the original input has expired. Current authorization and actor/source/run identity checks still apply; fresh execution still requires approved job definitions and retained inputs.

Workflow reconnect/replay fixes must be deployed as a matching frontend and backend release using repository-root `update-depo.ps1`, then restart application services. This includes `backend/data_pipeline_service/router.py`, `run_records.py`, `backend/depo_platform/request_bodies.py`, and the rebuilt Import/Data Flow frontend. No schema drop, credential rotation, new dependency or migration is required. Replay requests may include `idempotency_key`; retries with the same actor, source run and key return the retained run. Clients that omit the key retain the existing new-run-per-request behavior. The UI retains an unconfirmed replay reference in same-tab session storage; after clearing browser storage or using another tab, inspect retained runs before resubmitting. Cancelling a browser request does not cancel or roll back server execution.

The OSLC service supplies the central Change Control page. Deploy `backend/oslc_service/change_control.py` with the matching OSLC app and rebuilt frontend through the normal repository-root `update-depo.ps1` process. Release preflight rejects a package missing this module. No new dependency, credential or PostgreSQL schema migration is required; existing retained records are read from their owned namespaces. The page does not grant approvals, publish data, delete history or automatically convert historical records into change orders. See `docs/architecture/OSLC_LIFECYCLE_RELEASE.md` for API scope and the remaining central CR/CO enforcement phase.
# Existing deployments: optional XML analytics permissions

The control-plane role created by `infra/postgres/create-depo-database.sql`
owns its application schema but cannot create additional analytics schemas.
Installing updated code does not change that privilege automatically.

Before enabling versioned XML analytics, have the database owner review and run:

```powershell
psql -U postgres -d depo -v depo_role=depo_app -f infra/postgres/enable-depo-analytics.sql
```

Replace `depo` and `depo_app` with the existing database and runtime role.
This grants CREATE in that database; it does not grant superuser or CREATEDB.
Customers who cannot grant database CREATE should leave materialization disabled
until a separately reviewed pre-provisioned-schema implementation is available.
Existing workflows, credentials and records must be preserved during upgrade.

For isolated acceptance testing, an administrator can run
`infra/postgres/create-depo-test-database.sql` with `-v depo_role=depo_app`.
Set `DEPO_TEST_DATABASE_URL` privately to `depo_acceptance_test`, then run
`python -m pytest backend/tests/test_xml_analytics_postgres.py -q`.
The test creates uniquely named schemas and rolls back its test objects.
Do not put the connection string or password in logs, Git, or screenshots.

### Dependency size and safe cache maintenance

The default Windows runtime uses `backend/requirements-lock.txt`. Its 190 pinned
packages exclude nine OCR-only dependencies. `-EnableOcr` adds the complete
`backend/requirements-ocr-lock.txt` overlay. All existing versions and hashes are
preserved. Do not install the development profile on a customer runtime.

`DEPO_SERVICE_RUNTIME_MODE=shared` reuses `backend/.dt_venv` across service
processes. `isolated` keeps independent per-service environments and their
reviewed locks in `backend/dependency-profiles/`. Isolation can increase total
disk usage because several services need the same semantic dependencies. Do not
use `--system-site-packages` or link writable package directories between them.

From the repository root, inspect the selected environment without changing it:

```powershell
.\backend\.dt_venv\Scripts\python.exe infra\deployment\runtime-footprint.py --output logs\installation\runtime-footprint.json
.\backend\.dt_venv\Scripts\python.exe infra\deployment\build-service-locks.py --check
```

The footprint report separates runtime, optional OCR and outside-lock packages.
Its RECORD sizes can double-count shared files and do not establish uninstall
safety. Torch, spaCy and Transformers remain dependencies of pinned Semantica.
Pytest and pytest-asyncio are for acceptance/development, not the standard lock.
Pip remains necessary for managed installation and updates.

An upgrade installs the new dependency closure but does **not** uninstall old
packages from a reused environment. Obtain the smaller footprint with a fresh,
locked environment during a planned service stop and run the normal installer
and readiness checks before resuming. Preserve the previous environment for
rollback. Do not uninstall either OpenCV distribution from an active shared
environment: optional EasyOCR and Semantica can own overlapping `cv2` files.

Preview reproducible checkout caches, then remove them after tests/builds finish:

```powershell
.\backend\.dt_venv\Scripts\python.exe infra\deployment\clean-build-caches.py
.\backend\.dt_venv\Scripts\python.exe infra\deployment\clean-build-caches.py --apply
```

This command preserves dependency environments, `node_modules`, built `dist`,
uploads, data, logs and deliverables. It skips symlinks/junctions and refuses
caches containing them. It never clears workflow history or retained artifacts.
Use the authorized Admin retention workflows for business-data cleanup.

The release packager excludes build caches and generated JSON/XML/image/HTML
captures under `docs/audits/`, while preserving authored Markdown audits,
foundation resources and mapping configuration. Keep old served frontend assets
until existing browser sessions have finished using them.

`infra/windows/build-depo-frontend.ps1` builds in a temporary staging directory,
copies new assets into `frontend/dist`, and replaces `index.html` last. A failed
compilation leaves the served release intact. It retains old hashed assets for
already-open tabs; do not manually purge `dist/assets` while users are active.

# REST source configuration

Customer source releases must be built with
`python infra/deployment/build-release-package.py --output <new-zip-path>`
from a clean, committed, reviewed checkout. The older
`tools/build_customer_release.py` command delegates to the same policy.
Without `--output`, the command only checks file selection; this is not release
certification. Commit the complete reviewed change set, including new required
modules, before building a ZIP. Generated Maven `target` outputs, legacy
`tools/import` helpers and direct graph loader scripts are development-only and
are excluded from customer releases. Use the supported Import and Data Flow
workflows for customer data loading and publication.

Admin → Data sources can register HTTP(S) sources and submit acquisition through
the existing pipeline worker. Set `DEPO_REST_ALLOWED_HOSTS` and dedicated
`DEPO_REST_SECRET_*` references in the selected server environment, then restart.
Registration and run manifests use existing PostgreSQL registry tables; no new
schema migration is required. For exact setup, key-header examples, user steps
and current limits, see [REST source setup](docs/REST-SOURCES.md).

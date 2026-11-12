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

The updater reconciles Python and frontend dependency locks automatically. Its checkpoints reuse verified unchanged dependencies; `-InstallDependencies` remains accepted for older commands. Do not use `-SkipFrontend` for this release's import, workflow-access or graph-display fixes. It validates settings and tracked process ownership before shutdown, applies pending migrations/indexes, rebuilds the UI and restarts services. Credentials, artifacts, histories and publication decisions are retained; failed imports and pending mappings are not replayed or approved.

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

## Advanced operations and release-specific checks

Use the [detailed operator reference](docs/installation/OPERATOR_REFERENCE.md#release-specific-upgrade-and-verification-notes) for dependency maintenance, connector setup and feature-specific upgrade checks. This release includes additive migration `017_speed_event_pagination.sql`; deploy the complete backend, workers and rebuilt frontend through the existing updater. Never drop the schema to install it.

See [semantic event recovery](docs/SEMANTIC-EVENT-WORKFLOW.md), [memory configuration](docs/AGENT_MEMORY_AUGMENTATION.md) and [live memory demo readiness](docs/demo-narratives/memory/DEMO.md). Optional graph memory remains off unless explicitly configured. Do not interpret stored conversations, approved hints or completed workflows as proof of current business correctness.

See [release verification notes](docs/installation/OPERATOR_REFERENCE.md#local-acceptance-fixes-2026-11-02) for the November fixes, demo steps and upgrade acceptance checks.

If Windows hides a tracked process identity, Setup requests elevation before shutdown. Run the same launcher as administrator if elevation is unavailable. ExecutionPolicy Bypass does not grant process privileges; keep PID files and credentials.

For optional model and local demo settings, see the [OpenAI demonstration profile](docs/installation/OPERATOR_REFERENCE.md#low-cost-openai-demonstration-profile).
# Embedded property vocabulary update

The foundation bundle includes PCA IDO, the NEXUS business module and the pinned DIN EN 61360 property pattern 2.0.4. Deploy the complete foundation directory, including `manifest.json`, `dinen61360-2.0.4.ttl`, `DINEN61360-LICENSE.txt` and `NOTICE.md`, through the normal update process. Runtime checks verify module and license hashes and use local imports only. No additional database migration or dependency is needed for this vocabulary addition. Existing customer data and mappings are preserved; previous reasoning evidence must be checked again against the new bundle. See [embedded foundation operation](docs/EMBEDDED_SEMANTIC_FOUNDATION.md).


### Pinned offline vocabulary imports

OWL consistency checks resolve the bundled SKOS, SHACL, Dublin Core Terms and OSLC Core vocabulary snapshots locally. The import catalog and every vocabulary are checksum verified; unknown imports remain unresolved and corrupt resources fail closed. No ontology import URL is fetched during reasoning. Deploy the complete release resources and restart the ontology service; no PostgreSQL migration or new Python dependency is required for this change. Reasoning evidence is invalidated when the catalog changes. Resolving imports does not establish that the combined ontology satisfies the OWL 2 DL profile or is logically consistent.

### OSLC functional fixes (12 November 2026)

Deploy the complete OSLC service, ontology service and existing data-product-outbox worker together, then restart with the repository lifecycle script. Native ontology publication commits its PostgreSQL receipt and OSLC notification intent together; the existing worker retries idempotent delivery. No new worker, dependency or PostgreSQL table migration is required: state uses the existing registry namespaces. Notification coverage for other graph mutations still needs qualification.

PostgreSQL TRS Base uses streamed graph results and 1,000-member retained pages. `OSLC_TRS_MAX_SNAPSHOT_RESOURCES` bounds the complete snapshot (default 1,000,000; range 1–2,000,000). The older `OSLC_TRS_MAX_BASE_RESOURCES` remains a file-mode development limit. Snapshot metadata is published only after page persistence, expires after 15 minutes, and missing pages require a rebase rather than a partial success. Readiness alone does not certify independent TRS-client conformance. Remote snapshots now retain provider URL, authenticated requester and content digest; old snapshots without these fields remain legacy evidence and must not be represented as newly verified provenance.


Remote OSLC query discovery now follows advertised query capabilities under the configured provider origin and path prefix. Set `OSLC_REMOTE_CATALOG_PATH` to a relative catalog path if it differs from `oslc/catalog`. `OSLC_REMOTE_QUERY_MODE=legacy` retains the former fixed-path convention for providers that deliberately use it; the default is capability discovery. Provider-returned continuation cursors are bounded and remain confined to that provider. No remote provider is enabled by this upgrade.

Admin → Data sources includes retained OSLC snapshot selection and an approved preparation-workflow selector. The optional **Create preparation workflow draft** action creates an `oslc-snapshot-ingest` definition only; an authorized owner must review, approve and enable it through Data Flow. Preparation uses the existing pipeline worker and produces retained `connector-records` evidence for the existing `connector-ceim-normalize` mapping workflow. It does not publish the graph. Configure explicit `syncs` lifecycle grants for the intended read and execution identities; the upgrade does not broaden grants. Incomplete or legacy snapshots lacking provider/requester/content-digest provenance must be acquired again. Retained submission references reconcile retries rather than enqueueing duplicate work.


Reporting replication: migration 018 is applied by the normal PostgreSQL upgrade. See [OSLC reporting replication](docs/architecture/OSLC_LIFECYCLE_RELEASE.md#reporting-replication) for approved feed selection, worker execution, scheduler opt-in, freshness limits and snapshot product review. Existing data does not require a reset.

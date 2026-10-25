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

### Large ontology configuration

Generated RDF can be much larger than its source. `ONTOLOGY_MAX_UPLOAD_BYTES` defaults to 25 MiB and controls downstream artifact registration/publication as well as uploads; `ENGINEERING_CONVERSION_MAX_RESULT_BYTES` defaults to 256 MiB and controls the worker's complete generated result. Raising only the latter does not raise the former. Configure root `.env.local` consistently for ingestion, ontology and graph processes, then rerun setup to restart them. A root-plus-dependency XSD bundle still has a separate 25 MiB ceiling. Merge source limits apply to the combined inputs. Do not equate these byte limits with supported server memory capacity. See the [large-ontology audit](docs/audits/extra-large-ontologies-2026-10-21.md) for measured smoke tests and unresolved scale risks.

### Error recovery

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


## Configure Governor and Steward governance

The existing `ontology-governor` prepares merge/instance-link plans and requests publication. The existing `ontology-steward` evaluates saved evidence. These are deterministic registered tools; an LLM explanation cannot override their verdicts. No additional governance agent or PostgreSQL migration is required.

1. In the repository-root `.env.local`, select `ONTOLOGY_GOVERNANCE_PROFILE=imported_standard` (default) or `ONTOLOGY_GOVERNANCE_PROFILE=enterprise_curated`. The imported-standard profile preserves source IRIs and reports missing labels/definitions as warnings. The curated profile blocks missing labels/definitions. Neither generates definitions or silently changes predicates.
2. Optionally create a UTF-8 JSON policy file outside the source schemas and set `ONTOLOGY_GOVERNANCE_POLICY_FILE` to its absolute path in `.env.local`. It must be a JSON object no larger than 64 KiB. Supported overrides are `require_definitions` (boolean), `require_batch_provenance` (boolean), `upper_class_iris` (absolute IRI array), `approved_identity_pairs` (arrays of two absolute IRIs), and `identity_context_predicates` (absolute IRI array). Leave the file setting absent to use profile defaults. An unknown field or invalid profile fails validation.
3. Foundation alignment is disabled until approved foundation IRIs are supplied. When configured, declared classes need a subclass path to an approved category. Configure only a coherent enterprise foundation; preserve the original imported standard and use reviewed bridge axioms. Cycles and multiple inheritance are review findings, not automatic OWL contradictions.
4. Identity is held for domain review unless explicitly allowlisted in the server policy. An allowlist does not override contradictory OWL declarations, failed SHACL, or configured lifecycle/viewpoint mismatches. Configured identity-context values must be present for both selected terms. Never use this list merely because labels or match scores agree.
5. After changing `.env.local`, restart using the repository-root `manage-depo.ps1 -Action Restart -EnvFile .env.local`. Use the supported launcher or a permitted PowerShell session. Existing reviewed plans bind their policy fingerprint; regenerate plans after policy or evaluator changes.
6. In Ontology Junction, generate a plan. After semantic validation completes, the UI runs the existing Steward and displays its report, policy profile, findings, validation coverage, proposed version impact and provenance. Approval remains blocked if the report fails, is incomplete, or belongs to another plan. The server reevaluates policy before creating the merged artifact.

Version impact is a conservative recommendation relative to the target, not an automatic `owl:versionIRI` rewrite or a compatibility guarantee. Audit provenance is retained separately from the original ontology. No partial ontology graph is committed when blockers exist. Instance-link policy reports classification evidence and source snapshots; it does not claim validation of every instance against all SHACL shapes. Term retirement/migration, linguistic definition quality and domain role modeling still require reviewed domain decisions. Maintenance cleanup remains a separate authorized Admin operation.

Steward graph parsing and traversal run in an isolated worker. `GOVERNANCE_AUDIT_TIMEOUT_SECONDS` defaults to 60 seconds (maximum 300), bounded by the enclosing operation deadline. A timeout terminates the worker and blocks publication; narrow the review or adjust the deadline before retrying. Both retained SHACL and OWL-RL checks must complete before approval.

## Knowledge Companion answers

See [Knowledge Companion: answers and troubleshooting](docs/KNOWLEDGE_COMPANION.md) for graph and saved mapping-review retrieval, provider configuration, HTTP 429 diagnosis, evidence limits and end-user acceptance checks. Retrieval answers remain available when optional model generation fails; historical merge reviews do not prove current Neo4j publication.

See [Shared semantic services and ontology agents](docs/SEMANTIC_AGENT_ARCHITECTURE.md) for the existing Governor/Steward responsibilities, native Semantica integrations, page-context reads and the exact obsolete helpers removed during refactoring. No new semantic engine or database migration is required.


### Configure shared decision policies after setup

1. Start the deployed application with the supported `manage-depo.ps1` launcher and connect the existing governed access in Admin. PostgreSQL must be reachable; assessments use the existing registry table and need no additional schema migration.
2. Use the authenticated Ontology service `POST /api/v1/ontologies/policies` contract (also available in its API documentation). Give each policy a stable `policy_id`, an explicit `operations` array and native `rules`. Do not paste credentials into request examples or documentation.
3. For example, a policy body for instance links is `{"policy_id":"instance-link-score","operations":["instance_bridge"],"rules":{"min_confidence":0.95,"required_outcomes":["flagged"],"required_metadata":["decision_maker","preview_digest","candidate_id"]},"active":true}`. This adds a stricter shared rule; it does not weaken the existing validated-only gate. Omitted native rule fields use the documented Semantica defaults.
4. Keep minimum-score policies scoped to decisions with actual matching evidence. Ontology unions and general recommendation advice have no established confidence; they are recorded with zero confidence and will be held by a positive minimum. For metadata-only merge policy use `min_confidence: 0` explicitly and require `artifact_sha256`, `source_ontology_ids`, and `decision_maker`. Native metadata checks verify presence, not domain correctness.
5. Review `GET /api/v1/ontologies/policies`. Policies with no `operations` field are global, including policies retained from older installations. Unknown rule fields fail validation. Do not use a confidence score as a release approval.
6. Generate a fresh saved plan and inspect **Decision policy** in Recommendations or the existing Governor/Steward review. No configured policy is reported separately from a pass. If assessment is unavailable, check PostgreSQL and service logs; writes remain held. The server reassesses current policy before new writes. Existing verified publication receipts are reconciled without writing again.

Policy evaluations retain evidence under the PostgreSQL registry namespace `semantic_decision_assessments`. Operational log messages identify evaluator/storage failure types without printing policy payloads or credentials. For full limits and scoring semantics see [Shared semantic services and ontology agents](docs/SEMANTIC_AGENT_ARCHITECTURE.md).


### Microservice deployment and verification

The authoritative inventory is `infra/deployment/services.json`. Keep its service IDs and ports consistent with the selected environment file and frontend routing; avoid starting a second copy of the same service manually.

| Service ID | Default port | Responsibility |
|---|---:|---|
| `schema-sets` | 8010 | Engineering schema tasks and retained conversion artifacts |
| `ontology` | 8011 | Ontology catalog, lifecycle, policy evaluation and publication orchestration |
| `agentic` | 8012 | Governor/Steward execution, workflows and Companion |
| `graph` | 8013 | Neo4j projections, graph queries and Recommendations |
| `ingestion` | 8014 | File/profile ingestion and cross-service conversion workflows |
| `oslc` | 8015 | OSLC server and configured remote integration |
| `catalog` | 8016 | Governed data catalog |
| `data-products` | 8017 | Data-product packages and catalog delivery |
| `ceim` | 8018 | Canonical engineering normalization and approved publication |
| `data-pipeline` | 8019 | Data jobs, schedules and speed-path reconciliation |

1. From the repository root, select the existing `.env.local`. Set `DEPO_SERVICE_RUNTIME_MODE=shared` for the shared Python environment or `isolated` for service-specific environments. Use the existing root `Setup-DEPO.cmd` installer for dependency installation; changing source does not justify deleting environments or databases. Reviewed locks are under `backend/dependency-profiles/`; do not install arbitrary newer package versions in customer environments.
2. In a permitted PowerShell session start using `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Start -EnvFile .\.env.local`. This is process-scoped policy handling; a machine signing policy may still require an administrator-approved release. The launcher also manages `data-product-outbox`, `data-pipeline-worker`, and `agentic-workflow-worker`; these workers do not expose HTTP listener ports.
3. For each configured service base, check `/healthz`, `/readyz`, `/openapi.json`, and `/odata/$metadata`. For example use `http://127.0.0.1:8011/readyz` for Ontology readiness. `/healthz` proves the listener is alive; `/readyz` tests configured dependencies and returns 503 when unavailable. Development readiness can omit unconfigured stores; production requires the declared dependency configuration. Neither endpoint proves a business dataset has been loaded or a workflow succeeded.
4. The Graph and Agentic policy adapters call `ONTOLOGY_SERVICE_URL` using the existing `ONTOLOGY_APPROVAL_TOKEN`. Keep that credential consistent with the selected central credential store. The native policy engine remains owned by Ontology. A peer/authentication/storage failure holds affected writes; do not disable authentication to make a failing call pass. Gateways require explicit service URLs and their configured subscription header. Private peer clients do not inherit operating-system HTTP proxies or follow redirects.
5. `DECISION_POLICY_TIMEOUT_SECONDS` defaults to 30 (range 1-120). `SYSML_V2_SNAPSHOT_TIMEOUT_SECONDS` defaults to 300 (range 1-3600) for an entire paginated repository snapshot; per-request phase timeouts remain separate. Configure these in the selected environment file and restart the affected services after changes. Speed-path publication uses the existing graph-publication budget and bounded response reads. A timeout can leave a committed downstream result: verify the retained publication receipt before retrying.
6. For source updates use the supported checked update/installer and then the same root launcher. Tracked-process ownership checks must succeed before shutdown; if Windows denies process inspection, use the normal Windows administrator session. Do not remove PID tracking or stop unrelated Python processes. Application restart does not stop PostgreSQL or Neo4j.

On Windows the artifact store supports extended filesystem paths, including deep customer installation paths. Artifact identities, content hashes, usage references and containment checks remain in force. These runtime changes need no new database schema migration and do not approve or publish domain data automatically.


### Guided work and retained page tasks

1. Start using the repository-root `manage-depo.ps1` or its supported launcher. Keep `AGENTIC_EXECUTION_MODE=worker`, `AUTH_MODE=token`, PostgreSQL and the existing `agentic-workflow-worker` running for durable read investigations. Configure a supported model provider and its credentials in the selected environment file. A provider quota or configuration failure is reported; it is not a successful investigation.
2. Open a page and expand **Guided work & tasks**. The compact panel explains that page's sequence and lists agent tasks created with a page tag under the current authenticated identity. On investigation pages, expand **Start a scoped investigation or reviewed action**, optionally enter the exact ontology/source ID, select the existing agent, and describe the question. The optional ID is explicit task scope; it is not inferred from a different page's selector.
3. Start a read-only investigation to see the retained plan, actions, failures, selected evidence and conclusion. Read goals cannot write or publish. Plans describe intended work; only completed observations establish tool execution. A completed action does not establish downstream publication.
4. Navigate away and return, then open the retained task. The server checks ownership on history and detail reads. If submission loses its response, use **Recover submitted investigation**; the saved submission identity returns the original goal without queueing another. Keep the same source and question when recovering. Changing the source creates a separate browser bookmark. Clearing credentials closes the task view; it does not delete server history.
5. Import, Ontology Junction, Data Flow, Catalog, Data Products, QIF, Code Network and Admin keep their existing domain forms and histories. Their task panel provides guidance and page-tagged agent history; it does not replace domain task tracking or merge all native job types into a new engine. Older runs without page tags remain in their original histories.
6. For workflow execution, only server-advertised controls appear. A failed status read removes stale controls. After an uncertain write/control result, refresh and verify the existing domain receipt before trying again. Approval holds are shown as review required. Approval, policy, lifecycle and publication controls remain in their existing domain workflows.
7. Deployment adds metadata to the existing PostgreSQL registry records; no new table or schema migration is needed. Restart Agentic and rebuild/restart the frontend through the supported installer/launcher after applying the source. Do not delete the database to expose page history. Browser bookmarks are optional convenience; PostgreSQL remains authoritative.


### Verify Explorer search and data workspaces after an update

1. Start from the repository folder using `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Start -EnvFile .\.env.local`. When Neo4j is configured, the lifecycle checks publication constraints and required performance indexes before launching services. A healthy listener alone does not establish schema readiness.
2. If that stage reports missing constraints/indexes, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-neo4j.ps1 -EnvFile .\.env.local -Bootstrap` using the configured database identity with schema privileges. Then run the same command with `-Production` instead of `-Bootstrap`. These commands use `backend/depo_platform/neo4j_setup.py` and `infra/deployment/neo4j-publication-index.cypher`; they create missing release objects idempotently and do not delete records. Incompatible definitions or duplicate data require diagnosis; do not drop constraints or reset the graph to bypass validation.
3. Open Graph Explorer, select the intended scope and search a known node ID/name, relationship type, property name or value. Relationship hits show their endpoints. Best Match/Many Matches are removed: the view retains a bounded matching set and picks a focus node automatically. Search accepts up to 500 characters; a trailing `*` is treated as the same substring search, not a Cypher/Lucene expression. Universal engineering search uses bounded substring scans and shortened property previews, so it does not promise indexed query speed for arbitrary keys. Timeout/service errors explicitly identify the loaded-view fallback as incomplete. Existing publication and maintenance barriers still apply.
4. Open Data Catalog to discover retained import sources and registered ontologies independently of product publication. Search governed product versions by name, domain, owner, status or ID, then select a row or the detail selector to inspect ownership and provenance. A source record does not establish a complete or approved graph.
5. Open Data Products to check retained packages and pending catalog delivery. Expand **Review pipeline evidence** for a completed run, or **Review structural analytics** for a retained schema draft. Inspect the structural plan and define/approve business dimensions and KPI formulas through the existing analytics workflow. Importing an ontology does not automatically populate a warehouse or publish a product. Technical records and Governor recommendations are available on demand.


Both Data Catalog and Data Products show an always-visible **Evidence products you can build** section. **Structural analytics** identifies review-only entity-table/key/relationship/SQL plans and the number of available schema drafts. **Pipeline evidence** identifies retained outputs from completed Data Flow runs. Each subtab counts only records with its corresponding product kind in the currently loaded collection; Catalog counts cataloged versions and Products counts retained packages. Loading and failed reads are shown separately from zero. Use the review action to open the matching Products tools directly. The Structural analytics and Pipeline evidence subtabs keep one workflow visible at a time. Use the arrow keys, Home or End to change tabs. These tabs do not create or approve products.


### Data lifecycle cockpit

After startup, open `http://127.0.0.1:3000/#/data-flow` (or the frontend URL printed by your launcher). The lifecycle navigator connects Import sources, Process & validate, Build products and Discover & reuse. Its highlighted step identifies the current workspace; it does not certify workflow completion.

1. **Import**: retain source inputs using the existing import workflow.
2. **Data Flow / Run monitor**: select a run, filter by status and inspect lineage, input artifacts and output evidence. The latest-run counters are bounded snapshots, not lifetime totals.
3. **Data Flow / Pipeline jobs**: review versioned definitions, approvals and schedules. Run now and Schedule require a retained input run for the same job/version. If none exists, use the matching source import or analytics workflow first. Opening a workspace never executes a job.
4. **Data Flow / Approval & publication**: configure the reviewer and approved semantic release before explicit lifecycle actions. **Quality & evidence** summarizes retained results; **Agent assistance** provides recommendations for the selected run.
5. **Data Products / Create & review**: select Structural analytics or Pipeline evidence, inspect the source draft and validate the publication contract. **Product portfolio** shows retained packages and delivery status; **Governance** holds review guidance and governor recommendations.
6. **Data Catalog / Ingested sources**: find retained imports before product publication. **Published products** shows catalog registrations; **Product opportunities** links to creation tools. A retained import, pipeline completion and published product are separate states.

Workspace tabs support Left/Right, Home and End. Switching tabs preserves local form inputs. Reads that are unavailable must not be interpreted as zero records. Approval and publication remain explicit operations. This layout update does not migrate, delete or publish graph data.


### Recommendations: agent investigation and Semantica review

1. Start or restart PMem after deploying matched frontend and backend files. Open `#/recommendations`.
2. Select **Change Impact**, **Similar Parts** or **Process Context** and enter the existing graph-object name. Verify that the graph readiness check succeeds.
3. The default **Agent investigation + Semantica review** method uses the existing `graph-analyst` and durable read-goal worker. Select **Analyse with agent**. The model plans read steps, calls the selected registered recommendation tool, reviews its graph evidence and shared Semantica policy assessment, then cites the retained observation in its conclusion.
4. Review the plan, conclusion, **Analysis method & scope** and **Decision policy** findings. The server enforces the selected analysis, object and result limit. It rejects completion that substitutes unrelated reads or lacks the selected tool's policy evidence. A policy hold, missing configuration or unavailable assessment stays visible; task completion does not grant approval.
5. Use **Guided work & tasks** to reopen retained page history. Plans and observations use the existing PostgreSQL task store. The browser keeps a task bookmark so the same submitted investigation can be recovered after a lost response. Switching the selected object hides the old task view; it does not delete or silently cancel the retained task. Use **Cancel investigation** for an active task.
6. Choose **Direct graph analysis** when an agent investigation is unnecessary. This executes the existing bounded graph endpoint and shared decision-policy adapter directly. Neither method approves, publishes or modifies application graph data. Tool execution may retain audit and assessment evidence.

The graph tool derives advice from bounded Neo4j traversal or heuristic ranking. The ontology policy service uses `semantica.ContextGraph.enforce_decision_policy`; the Graph Analyst can also investigate through its existing semantic-context and graph read tools. This does not establish calibrated probability, full engineering impact coverage or automatic learned memory. The retained goal scratchpad is PostgreSQL-backed.

The agent mode requires the matching backend `read_goal_capabilities.recommendation_evidence=1`, registered recommendation tools, configured model provider and durable workflow worker. If the page says the updated backend is pending, restart PMem using the repository-root `manage-depo.ps1 -Action Restart -EnvFile .env.local`, then retry readiness. Do not remove process-safety checks. Missing graph context and provider failures must be resolved before live inference can be accepted.


### Windows restart permissions and process visibility

Use the repository-root `manage-depo.ps1` for Start, Stop or Restart. Being signed in with an account named Admin does not guarantee that the current PowerShell process is elevated.

Before changing a running deployment, the lifecycle command checks tracked-process identity visibility. If Windows hides an executable path or command line, the command requests elevation through Windows UAC once and repeats the same action, selected environment file, profile and skip options. Accept the Windows prompt to continue. The original command waits only for the elevated lifecycle process (not its long-running service descendants); audit logs remain under `logs/installation/runs/`.

If UAC is cancelled or cannot be displayed, no lifecycle action is started by this preflight. Open PowerShell using **Run as administrator** and rerun the same command. If metadata is hidden even after elevation, investigate Windows CIM/WMI/process-access policy with the administrator. Do not delete PID files, kill arbitrary Python processes or disable ownership checks. A visible but unrelated/reused PID is still handled by the normal process-ownership guard.

Frontend diagnostics now distinguish missing metadata from an executable/module mismatch. The lifecycle preflight runs before frontend shutdown and backend shutdown, preventing partial restarts caused solely by missing process visibility. This does not change machine execution policy or stop PostgreSQL/Neo4j.


### Agent context, ontology revisions and memory maintenance

Deploy the ontology and agentic services from the same release. New ontology-scoped read goals require the authenticated owning-service endpoint `GET /api/v1/ontologies/{ontology_id}/revision`. It returns an artifact SHA-256 digest and lifecycle state under the ontology lock. The agentic service verifies those receipts before queueing and during planning/tool execution. An unavailable authority returns HTTP 503 before queueing; a changed/retired source requires a new review. Do not disable authorization or remove the source binding to resume a stale investigation. Existing retained runs without revision receipts keep their previous checks. This contract verifies ontology artifacts, not every mutable instance node in Neo4j.

Revision reads share the bounded `COMPANION_RETRIEVAL_TIMEOUT_SECONDS` budget (default 15 seconds, maximum 120) for the complete selected ontology set, up to ten distinct IDs. Ensure the configured ontology URL and gateway permit that route; do not increase a provider timeout to work around a rejected local service request.

When optional conversation memory is enabled, `AGENT_MEMORY_RETENTION_DAYS` controls existing conversation cleanup. Completed Companion records and expired graph conversations respect stored legal holds. `GET /api/v1/memory/maintenance` on the agentic service returns the latest operational receipt, including per-store status and counts. `partial`, `unavailable`, or `disabled` is not proof that all stores were cleared. The receipt is bounded latest-run state, not a permanent business audit ledger. It does not purge ontology facts, workflow approvals, source files or backups. Existing artifact retention remains owned by the Catalog service.

Optional workflow `governance` metadata in the configured agent catalog must contain `version` (for example `1.0.0`) and `status` (`proposed`, `approved`, or `retired`). An approved entry additionally requires `approved_by` and `evaluation_sha256` referencing its reviewed evaluation artifact. Proposed and retired entries cannot produce executable workflow plans. This is trusted deployment configuration; it does not replace operation-level approval credentials or cryptographically certify an evaluation. Existing bundled definitions without this metadata retain release-controlled compatibility. No agent automatically promotes its execution trace into a trusted procedure.


### Admin full-cleanup receipts and recovery

`Clean schema` remains a destructive action requiring the existing Admin maintenance credential and explicit confirmation. The Import preflight now checks active/uncertain tasks, stored task/manifest legal holds, artifact/snapshot storage boundaries and deletion-fence boundaries before the graph reset starts. A cleanup retry receipt cannot override a currently active task's status. These checks do not constitute a universal graph-node or backup legal-hold policy.

Before deletion the service creates a receipt in PostgreSQL namespace `admin_cleanup_runs_v1`. If that initial receipt cannot be saved, the graph reset does not start. The response includes `cleanup_receipt` with separate graph, reconciliation, ontology-metadata and Import-workflow phases. An interrupted error response can include the `X-DEPO-Cleanup-ID` header. Read that receipt through authenticated `GET /api/v1/admin/cleanup-runs/{run_id}` using the existing Admin maintenance access; do not paste credentials into commands or chat. A pending/running phase after a service crash is not evidence that the operation failed or that it is safe to repeat.

There is no automatic graph-reset replay. Inspect graph state and the per-store receipt before deciding whether any further destructive action is required. Import task deletion fences retain per-task `artifacts`, `snapshots` and `manifest` progress; the existing Clear Import Workflows action reconciles remaining files/records under its normal activity and hold checks. A failed registry delete cannot be reported as complete merely because its files are gone. These receipts cover the named cleanup operation, not backups, all application data, or a legal/compliance deletion certification.


### Customer acceptance and backup/restore gate

After deploying matching service/frontend code, run the maintained deployment and browser-session diagnostics from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\test-depo-deployment.ps1 -EnvFile .\.env.local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-browser-session.ps1 -EnvFile .\.env.local
```

These verify connectivity/configuration/access; they do not certify ontology mapping or generated answer accuracy. Do not use the removed `backend/tests/customer_acceptance_test.py` legacy script. Use the domain fixtures and live matrix in [release acceptance](docs/architecture-review-2026-10-24/DEPO_RELEASE_ACCEPTANCE.md).

Customer release also requires a real backup/restore drill into disposable PostgreSQL, Neo4j and artifact stores. Identify the backup set and separate restore target before running any restore. Record release/database versions, a consistent recovery point, trusted checksums, schema verification, source/publication identity checks and measured recovery results. An installation backup of source code is not a database backup, and a passing schema check is not proof that a backup can be restored. The linked acceptance document specifies the required sequence and evidence without issuing an unsafe overwrite command against the current environment.

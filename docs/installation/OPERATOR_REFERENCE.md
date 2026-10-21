# Installation operator reference

## Import workflow cleanup

Admin → Maintenance → Clear Import Workflows deletes quiescent instance-import and schema-set task snapshots, task-owned sources/previews/reports and matching workflow artifact manifests in PostgreSQL. Full Schema Cleanup includes this operation; Graph Reset Only does not. Active processing, queued execution and uncertain publication outcomes block deletion before the graph is changed. Resolve those outcomes or cancel through the supported workflow controls first.

Import rows cached in this browser and other open tabs are invalidated on successful cleanup. Small persistent deletion receipts are retained to fence stale worker caches; do not delete these receipts as routine cache maintenance. Partial filesystem/database failures are logged and retryable. This is separate from agent audit-history retention, governed catalog artifacts, data products and shared content-addressed artifacts; those are retained. The Import page's Clear finished/failed history button clears browser rows only.

## Installer and diagnostic audit behavior

Run supported root entry points from the complete matching release. Update and diagnostics apply process-scoped bypass before loading their nested helpers, respect enforced signing policy and retain redacted action/error logs in logs/installation/runs. Root update accepts `-Python` and forwards it with the selected environment file and other explicit options. `-PreflightOnly` performs checks without stopping services or changing database schemas; retaining an audit log is expected. A custom selected environment file contributes secret values to audit redaction before environment import.

The package gate requires the Import cleanup and maintenance helpers together with their service callers. A release missing those coupled files is rejected before guided upgrade shutdown. Clean-machine, database-backup/restore, gateway and customer browser acceptance remain separate from offline fixture checks.

Start with [the customer installation guide](../../INSTALLATION.md). This reference covers database engines, Linux, gateway deployments, optional runtimes and individual service diagnostics. These are operator references, not a second installation sequence after guided Setup.

Commands assume the repository root unless explicitly stated. Start Windows operator shells with powershell.exe -NoProfile -ExecutionPolicy Bypass; organization signing policy remains authoritative. Replace example paths and hosts with your deployment. Back up databases, artifacts and configuration before updating.

## Reference map

- [LLM providers](#configurable-llm-providers)
- [Database and optional runtime prerequisites](#1-provision-the-customer-dependencies)
- [Server and browser configuration](#2-create-configuration)
- [Advanced Windows installation](#3-run-the-single-windows-installation-command)
- [Deployment verification and gateways](#4-complete-customer-deployment)
- [Gateway routing](#switching-local-services-and-api-gateway-routing)
- [Installation audit logs](#windows-setup-and-lifecycle-audit-logs)

## Configurable LLM providers

Set these values in the server root .env.local, then restart the backend APIs and workers using the supported deployment scripts. No frontend rebuild is needed for a provider switch. Keys remain on the server; never use VITE_ variables for them.

| Setting | Purpose |
| --- | --- |
| USE_LLM | ollama, openai, mistral, or existing azure |
| USE_EMBEDDER | Independent embedding provider; defaults to USE_LLM when absent |
| LLM_MODEL_NAME / EMBED_MODEL_NAME | Installed Ollama generation and embedding model names |
| OPENAI_MODEL / OPENAI_EMBED_MODEL | Explicit OpenAI chat and embedding model IDs |
| OPENAI_API_KEY | OpenAI project API key; separate from PMem ADMIN_API_KEY and Codex sign-in |
| MISTRAL_MODEL / MISTRAL_EMBED_MODEL | Explicit Mistral chat and embedding model IDs |
| MISTRAL_API_KEY | Mistral API credential |
| OPENAI_BASE_URL / MISTRAL_BASE_URL | Optional HTTPS API roots; default to the official /v1 endpoints |

Fully offline Ollama example (install or transfer both models before use):

~~~dotenv
USE_LLM=ollama
USE_EMBEDDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL_NAME=llama3:latest
EMBED_MODEL_NAME=nomic-embed-text:latest
~~~

A locally installed Mistral model can also run offline through Ollama: keep USE_LLM=ollama and set LLM_MODEL_NAME to its exact installed tag.

OpenAI example (replace the model placeholder with an ID enabled for your API project):

~~~dotenv
USE_LLM=openai
USE_EMBEDDER=openai
OPENAI_MODEL=<your-enabled-chat-model-id>
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_API_KEY=<your-project-api-key>
~~~

Mistral cloud example:

~~~dotenv
USE_LLM=mistral
USE_EMBEDDER=mistral
MISTRAL_MODEL=<your-enabled-chat-model-id>
MISTRAL_EMBED_MODEL=mistral-embed
MISTRAL_API_KEY=<your-mistral-api-key>
~~~

For mixed operation, set USE_LLM=openai or mistral and USE_EMBEDDER=ollama with the installed EMBED_MODEL_NAME. This keeps embeddings local but sends selected prompts and graph evidence to the chosen cloud provider. Provider selection never automatically falls back to another provider. Cloud failures remain errors, including authentication failures and rate limits.

Provider-specific cloud model settings are required deliberately: a leftover LLM_MODEL_NAME=llama3:latest will not be sent to a cloud API. Missing or invalid provider settings fail configuration readiness without returning secret values. Readiness validates configuration; it does not claim live inference succeeded. Explicit capability probes perform inference and may incur charges. Generation, structured output, native tool calling, and vision depend on the selected model's capabilities.

Summaries, agent proposals, capability probes and ontology review support Ollama, OpenAI and Mistral. The shared LangChain clients also preserve the existing Azure configuration. Azure-only agent review remains outside the supported agent provider set. OpenAI shared chat uses Responses; agent review adapters and Mistral use Chat Completions. Cloud output is buffered and validated before SSE delivery; OLLAMA_STREAMING_ENABLED controls only native Ollama streaming. Existing proposal-mode settings, approval rules, tool allowlists, prompt bounds and citation validation still apply.

Optional document vision: set USE_UNSTRUCTURED_LLM=true, UNSTRUCTURED_LLM_TYPE=openai or mistral, and UNSTRUCTURED_OPENAI_MODEL or UNSTRUCTURED_MISTRAL_MODEL to a vision-capable model. The selected provider's API key and base URL are reused. Without a separate unstructured provider, document processing follows the main LLM and therefore requires a model capable of the requested input.


Provider audit notes: set EMBEDDING_VECTOR_DIMENSIONS to the actual output dimension of your embedding model before creating graph or document vector indexes. Existing 768-dimensional indexes do not accept vectors of another size. Rebuild/migrate affected indexes deliberately before re-embedding. The graph embedding cache now includes the effective provider, model, endpoint and configured dimension; its version change causes existing graph chunks to be re-embedded on the next embedding run.

Cloud agent requests share the existing endpoint-scoped admission/circuit settings (OLLAMA_MAX_CONCURRENCY, OLLAMA_FAILURE_THRESHOLD, OLLAMA_CIRCUIT_COOLDOWN_SECONDS) and honor the remaining operation deadline. These legacy setting names also apply to the cloud review adapter.

Changing embedding model or provider requires re-embedding existing vectors into an index compatible with the new dimension/model. Never mix vectors from different models in one index. Switching generation provider does not migrate stored embeddings.

Official API references: [OpenAI text generation](https://developers.openai.com/api/docs/guides/text) and [Mistral migration and compatibility](https://docs.mistral.ai/resources/migration-guides).


## 1. Provision the customer dependencies

### 1.1 Install PostgreSQL 16

PostgreSQL is required. For a new Windows machine, download the supported
PostgreSQL 16 x64 installer from the [official PostgreSQL Windows download
page](https://www.postgresql.org/download/windows/). The installer is provided
by EDB and includes the database server and `psql` command-line tools. During
the installer screens:

1. Select **PostgreSQL Server** and **Command Line Tools**. pgAdmin is optional.
2. Keep the displayed data directory unless the customer storage policy assigns
   a dedicated data volume.
3. Choose and record the Windows service name shown by the installer.
4. Set a PostgreSQL administrator password. The installer starts the Windows
   service when it finishes.

Open a new PowerShell window and confirm the tools and service are available:

```powershell
$pgBin = 'C:\Program Files\PostgreSQL\16\bin'
& "$pgBin\psql.exe" --version
Get-Service | Where-Object DisplayName -like '*PostgreSQL*' | Format-Table Status, Name, DisplayName
```

If the service is stopped, start the exact `Name` returned above:

```powershell
Start-Service -Name 'postgresql-x64-16'
```

Record that exact service name. You will set
`DEPO_POSTGRES_MODE=service` and `DEPO_POSTGRES_SERVICE_NAME=<that-name>` in
the root `.env.local` in section 2.1, which allows the lifecycle launcher to
start and check the local database. For a managed or remote PostgreSQL server,
keep `DEPO_POSTGRES_MODE=external` and leave the service name blank.

Create a database, a least-privilege application login, and its schema with the
single reviewed provisioning script. It prompts securely for the application
password instead of writing it into PowerShell history. Replace only the server
administrator account when it differs from `postgres`. The `-v` values are
identifiers, not passwords; choose the same values that will be used in
`.env.local`. The administrator retains database ownership; `depo_app` owns
only the `semantic` schema.

```powershell
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 `
  -v depo_role=depo_app `
  -v depo_database=depo `
  -v depo_schema=semantic `
  -f .\infra\postgres\create-depo-database.sql
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL database provisioning failed.' }
```

In the root `.env.local` created in section 2, set
`DEPO_DATABASE_URL=postgresql://depo_app:URL_ENCODED_PASSWORD@127.0.0.1:5432/depo?sslmode=disable`
for this local setup. For a managed or customer database, ask the DBA to create
the equivalent login, database and schema; use `sslmode=verify-full` and the
customer CA certificate. If the customer has explicitly approved a private,
isolated non-TLS network, use `sslmode=disable` instead. Never paste a real
password into PowerShell history or source control.

If PostgreSQL is hosted on another VM, do **not** install PostgreSQL or set a
Windows PostgreSQL service name on the DEPO application VM. Ask the DBA to
create the database, role, and `semantic` schema on the database VM, permit the
application VM's private IP on port `5432`, and provide the CA certificate.
For an existing customer database, run the following in pgAdmin Query Tool as
its administrator **before** the DEPO installation. Replace the example role,
database and schema with the customer's chosen identifiers:

```sql
CREATE SCHEMA IF NOT EXISTS semantic AUTHORIZATION depo_app;
GRANT CONNECT ON DATABASE depo TO depo_app;
GRANT USAGE, CREATE ON SCHEMA semantic TO depo_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA semantic TO depo_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA semantic TO depo_app;
```

After running `configure-depo.ps1` in Section 2, configure the application VM:

```powershell
# Run from the DEPO repository root and edit the existing keys in this file.
notepad .env.local
```

The resulting entries must be exactly one line each (replace the placeholders
with DBA-approved values):

```text
DEPO_POSTGRES_MODE=external
DEPO_POSTGRES_SERVICE_NAME=
DEPO_POSTGRES_BIN_DIR=
DEPO_POSTGRES_DATA_DIR=
DEPO_DATABASE_SCHEMA=semantic
DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS=10
DEPO_DATABASE_URL=postgresql://depo_app:URL_ENCODED_PASSWORD@postgres-db.internal.example:5432/depo?sslmode=disable
```

Use `sslmode=verify-full` and the DBA-provided CA certificate when TLS is
required. With an approved private non-TLS network, keep `sslmode=disable` and
set pgAdmin and the ODBC DSN to **SSL mode: Disable** as well.

Edit existing keys in place if they already exist; do not append duplicate
keys. In external mode the Windows lifecycle scripts skip `Start-Service`,
`pg_ctl`, and local PostgreSQL paths. They connect to the remote database only
when schema initialization and service readiness checks run.

### 1.1.1 Test the remote PostgreSQL connection with pgAdmin 4

pgAdmin is a graphical PostgreSQL client; it does not install or host the
server, and a successful pgAdmin connection does not test ODBC. Install pgAdmin
4 on the administrator or application VM from the [official pgAdmin Windows
download](https://www.pgadmin.org/download/pgadmin-4-windows/).

Open pgAdmin, right-click **Servers**, select **Register > Server**, and enter
the DBA-provided host name/private IP, port `5432`, maintenance database
`depo` (or `postgres`), user `depo_app`, and password. Set SSL mode to
`verify-full` and select the customer CA certificate when required. Use any
local label such as `DEPO PostgreSQL (remote)` for the General > Name field.

Open **Tools > Query Tool** and run these read-only checks:

```sql
SELECT current_database(), current_user;
SELECT has_schema_privilege(current_user, 'semantic', 'USAGE, CREATE') AS has_semantic_schema_grants;
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'semantic'
ORDER BY table_name;
```

The first query must show `depo` and `depo_app`; the privilege query must return
`true`. pgAdmin may report `public` for `current_schema()` because it does not
use DEPO's runtime search path. The table query confirms that the application
schema is reachable. A pgAdmin connection
proves PostgreSQL network access and credentials only. For upgrades, the migration
role must also own the existing DEPO tables/views or inherit privileges from their
owning role. The migration command checks this before running migration SQL and
reports blocked relation names. Schema grants alone do not authorize `ALTER TABLE`;
have the DBA reconcile ownership rather than recreating the database. Continue with the ODBC
test below when another Windows application requires ODBC.

The Section 3 installer tests the **actual DEPO URL** after installing backend
dependencies and before migration. After the first installation, run the same
connection-only check independently from the application VM whenever the
database host, password, firewall or TLS settings change:

```powershell
.\infra\postgres\test-postgres-connectivity.ps1 -EnvFile .env.local
```

Success reports the database and login. A failed check reports a sanitized
PostgreSQL error category without printing the URL or password.

### 1.1.2 Install and test the PostgreSQL ODBC driver on a 64-bit Windows VM

Install psqlODBC on the Windows VM where the ODBC-consuming application or
service runs, not on the PostgreSQL database VM. Download the signed 64-bit
Windows installer from the [official PostgreSQL ODBC project](https://odbc.postgresql.org/).
After installation, verify that Windows registered the driver:

```powershell
Get-OdbcDriver -Name '*PostgreSQL*' | Format-Table Name, Platform, Version
Start-Process "$env:WINDIR\System32\odbcad32.exe"
```

On 64-bit Windows, `System32\odbcad32.exe` is the 64-bit ODBC Administrator.
In **System DSN**, select **Add**, choose **PostgreSQL Unicode(x64)**, and set
the data source name to `DEPO_PG_REMOTE`. Enter the DBA-provided host, port,
database `depo`, and user `depo_app`; set SSL mode to `verify-full` and select
the customer root CA if TLS is required. For an approved private non-TLS setup,
set SSL mode to `disable`. Use a System DSN for a Windows service. Do not
export the DSN with a plaintext password.

Test the System DSN without putting the password in command history:

```powershell
.\infra\postgres\test-postgres-odbc.ps1 -Dsn DEPO_PG_REMOTE -User depo_app
```

The script checks for a 64-bit driver and System DSN, prompts for the password,
and safely escapes connection string characters such as semicolons. It reports
the connected database and user. It does not require DEPO tables to exist.

The DEPO backend uses `DEPO_DATABASE_URL` through `psycopg`; ODBC is optional
for external Windows tools. If no driver appears, check that the 64-bit driver
was installed. A timeout indicates DNS, firewall, or port `5432` access; an SSL
error indicates a CA or hostname mismatch; an authentication error requires
the DBA to check role, password, and schema grants.

Neo4j may run on-premises, on a private VM, as a hosted self-managed server, or
in Neo4j Aura. Use the provider's actual database name. Production requires
certificate-verified TLS by default: `neo4j+s://` or direct `bolt+s://`. A
trusted private on-premises network may explicitly disable TLS as described
below. Bootstrap may use
`+ssc` or plaintext only on a controlled local network. Configure the advertised
Bolt address, certificate chain and application database account. The application
installer does not install or operate either database server.

The single installer in Section 3 applies the idempotent Neo4j publication
constraints after it creates the backend environment. It then performs a
read-only production verification. Do not run a separate Neo4j schema script.
When upgrading an existing deployment, rerun the installer before restarting
services. Semantic Bridge publication requires the `depo_bridge_publication_id`
uniqueness constraint; publication fails closed until Neo4j schema provisioning
has applied it.

Ontology publication from the review panel now submits a durable background job.
After upgrading and provisioning `uq_ontologystagedresource_identity`, each identified
publication commits resources and relationships in batches of 1,000. Batches use
the `StagedOntologyResource` label and remain outside the public RDF projection.
Activation also commits bounded node, relationship and cleanup batches, followed
by a small publication-receipt transaction. The panel shows queued/running status
and committed resource progress; it can be closed while the server works.

Interrupted batches are retained. Verify publication first, then explicitly
submit the same approved artifact again to resume its checkpoints. A changed
manifest cannot reuse those checkpoints. Cancel is available only before a
queued job starts; it does not undo completed writes. Do not delete staging data
manually while publication is active. Replacements also commit their preparation
batches and resume retained checkpoints. Final replacement activation reads staged
properties on the server and updates existing identities to preserve Semantic Bridge
and instance links. The previous projection remains readable during preparation.
During activation, a PostgreSQL visibility barrier temporarily rejects application
graph access instead of returning a partially updated projection. Receipt polling,
authentication and service readiness remain available. All graph-consuming services
must be upgraded together; older processes and external direct Neo4j clients do not
participate in this barrier.
Missing staging schema produces a
clear configuration error; rerun the matching release installer to provision
the staging constraint. Publication no longer silently falls back.

`GRAPH_PUBLICATION_TIMEOUT_SECONDS` bounds isolated RDF/projection preparation.
`GRAPH_PUBLICATION_WRITE_TIMEOUT_SECONDS` bounds the complete staged batch phase;
each batch receives only its remaining time. Final activation has a separate
`GRAPH_PUBLICATION_ACTIVATION_TIMEOUT_SECONDS` budget. Both optional settings
inherit the preparation budget when omitted and accept 1–3600 seconds.
Activation uses its activation allowance plus any unused write time. Each activation
transaction receives at most 30 seconds from that shared remaining budget. This
preserves graph identities while allowing checkpoint recovery. Preliminary reads and
connection acquisition are bounded. Confirmed-idle, resumable staged jobs retry
from retained checkpoints automatically, up to three attempts; uncertain atomic
writes are verified rather than replayed. Increasing browser timeouts does not
extend these server deadlines. Complex replacements can still exceed their
bounded allowance and require review; no timeout setting guarantees completion.
Graph views, dictionaries, requirements and OSLC queries exclude staged nodes.
Generic graph/OSLC reads also exclude internal `OntologyPublication` receipts
before pagination and aggregation. Deploy these readers together with the
publisher so unfinished batches cannot appear in customer results.

Lock acquisition and activation share one deadline. A failure while draining readers
or validating staging clears its own pre-write barrier. After graph writes may have
started, the barrier remains until the same publication resumes or its exact current
published receipt is verified. Normal receipt polling repairs a failed post-commit
marker acknowledgement. Marker cleanup has a bounded three-second recovery allowance;
it cannot clear another publication or write graph data. PostgreSQL transactions
recheck execution ownership and remaining time before commit; expired pooled
connections are discarded without reset SQL. A transport error during commit still
requires receipt reconciliation because the commit may already have succeeded.

Each activation attempt has a unique owner token. PostgreSQL ownership is checked
before every batch, and each Neo4j mutation locks its publication receipt before
checking the owner in the same transaction. A worker whose lock connection was lost
cannot keep writing after another worker resumes, nor clear that worker's barrier.
The receipt and canonical-resource uniqueness constraints must be provisioned along
with the staging constraint before publishing.

### 1.2 Install optional Apache Spark and PySpark

> **Current Windows deployment boundary:** Until a Linux Spark VM is available,
> DEPO runs native Windows Spark only in the dedicated
> `data-pipeline-worker` process. The HTTP Data Pipeline service submits a
> durable PostgreSQL run and returns a queued status; it does not own the JVM.
> PostgreSQL leases, worker heartbeats, bounded retries and expired-lease
> recovery prevent an API restart from losing submitted work. Set
> `DEPO_PIPELINE_EXECUTION_MODE=worker` for customer installations. The
> `inline` mode is retained only for isolated developer compatibility.

Install Spark only when the Data Pipeline service will execute Spark jobs. The
application validates one fixed layout: **Spark 4.1.2**, **Scala 2.13**, **JDK
21**, the bundled PySpark/Py4J libraries, and the Windows Hadoop helper. Follow
the commands below from an Administrator PowerShell window.

Run the Spark setup in this order. Do not jump directly to the final installer:

| Order | Run | Continue with |
| --- | --- | --- |
| 1 | Step A | Confirm `java -version` starts with `21` |
| 2 | Step B | Confirm both files exist under `C:\DEPO\downloads` |
| 3 | Step C | Confirm the SHA-512 and GPG checks pass |
| 4 | Step D | Confirm `spark-submit.cmd`, `pyspark.zip`, the Spark core JAR, approved `winutils.exe`, and `hadoop.dll` exist |
| 5 | Section 2.3 | Copy the verified paths into the root `.env.local` |
| 6 | Section 3 | Run the application installer with `-EnableSpark` |
| 7 | Section 4 | Complete post-install validation and customer acceptance |

The only archive downloaded in this sequence is
`spark-4.1.2-bin-hadoop3.tgz`. The `.tgz` is extracted by Windows
`tar.exe` in Step D; no separate unzip program or `pip install pyspark` command
is required.

The exact filenames expected at the end of the Spark setup are:

| Location | Exact filename |
| --- | --- |
| `C:\DEPO\downloads` | `spark-4.1.2-bin-hadoop3.tgz` |
| `C:\DEPO\downloads` | `spark-4.1.2-bin-hadoop3.tgz.sha512` |
| `C:\DEPO\downloads` | `spark-4.1.2-bin-hadoop3.tgz.asc` |
| `C:\DEPO\downloads` | `apache-spark-KEYS` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\bin` | `spark-submit.cmd` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\python\lib` | `pyspark.zip` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\python\lib` | `py4j-0.10.9.9-src.zip` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\jars` | `spark-core_2.13-4.1.2.jar` |
| `C:\DEPO\runtime\hadoop\bin` | `winutils.exe` |
| `C:\DEPO\runtime\hadoop\bin` | `hadoop.dll` |
| JDK installation directory `bin` | `java.exe` |

The Py4J filename can include a Spark-published patch version. Step D's
`Get-Item` check validates the PySpark archive and Spark core JAR; the runtime
smoke test validates the bundled Py4J library.

#### Step A — install and verify JDK 21

Install JDK 21 through the customer software catalogue. If the customer permits
Windows Package Manager, this command installs Microsoft OpenJDK 21:

```powershell
winget install --id Microsoft.OpenJDK.21 -e --source winget
java -version
$jdkHome = 'C:\Program Files\Java\jdk-21' # Replace if the installer used another JDK 21 folder.
Get-Item "$jdkHome\bin\java.exe", "$jdkHome\release"
```

Close and reopen PowerShell if `java` is not found. The version output must start
with `21`. Record the JDK installation folder containing `bin\java.exe` and a
`release` file. The examples below use `C:\Program Files\Java\jdk-21`; replace
that path if your JDK installer uses another folder.

#### Step B — download Spark 4.1.2 and its SHA-512 file

This release is intentionally pinned to Spark 4.1.2 because the application
checks for `spark-core_2.13-4.1.2.jar`. Apache ships the Windows-compatible
binary as a **`.tgz`** archive; it does not publish a `.zip` file for this
package. Windows 10/11 includes `tar.exe`, which extracts `.tgz` files.

Download these exact files. Do **not** download `pyspark-4.1.2.tar.gz`,
`pyspark_client-4.1.2.tar.gz`, `spark-4.1.2.tgz`, or the `-connect` archive:
they do not provide the full local Spark runtime expected by this application.

| Purpose | Exact file to download | Direct Apache URL |
| --- | --- | --- |
| Spark runtime | `spark-4.1.2-bin-hadoop3.tgz` | [download runtime](https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz) |
| SHA-512 checksum | `spark-4.1.2-bin-hadoop3.tgz.sha512` | [download checksum](https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz.sha512) |
| GPG signature | `spark-4.1.2-bin-hadoop3.tgz.asc` | [download signature](https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz.asc) |
| Apache signing keys | `KEYS` | [download keys](https://downloads.apache.org/spark/KEYS) |

The 4.1.2 files are historical-release artifacts because the application is
pinned to that approved baseline. Record the security approval alongside the
release evidence.

```powershell
$sparkVersion = '4.1.2'
$jdkHome = 'C:\Program Files\Java\jdk-21' # Replace with the JDK 21 folder verified in Step A.
$sparkHome = "C:\DEPO\runtime\spark-$sparkVersion-bin-hadoop3"
$sparkArchive = "C:\DEPO\downloads\spark-$sparkVersion-bin-hadoop3.tgz"
$sparkUrl = 'https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz'

New-Item -ItemType Directory -Force C:\DEPO\downloads, C:\DEPO\runtime, C:\DEPO\data\spark-output, C:\DEPO\runtime\hadoop\bin | Out-Null
Invoke-WebRequest -Uri $sparkUrl -OutFile $sparkArchive
Invoke-WebRequest -Uri "$sparkUrl.sha512" -OutFile "$sparkArchive.sha512"
```

#### Step C — verify the download before extracting it

Run the following checksum check. It stops immediately if the downloaded
archive differs from the Apache-published SHA-512 value.

```powershell
$expectedHash = ((Get-Content "$sparkArchive.sha512" -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA512 $sparkArchive).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) { throw "Spark SHA-512 verification failed. Delete $sparkArchive and download it again." }
Write-Host 'Spark SHA-512 verification passed.'
```

For a customer release, also validate the Apache release signature. Install
Gpg4win from the customer software catalogue first, then run. These commands
download the exact `.asc` and `KEYS` files listed in the table above:

```powershell
Invoke-WebRequest -Uri "$sparkUrl.asc" -OutFile "$sparkArchive.asc"
Invoke-WebRequest -Uri 'https://downloads.apache.org/spark/KEYS' -OutFile 'C:\DEPO\downloads\apache-spark-KEYS'
gpg --import C:\DEPO\downloads\apache-spark-KEYS
gpg --verify "$sparkArchive.asc" $sparkArchive
if ($LASTEXITCODE -ne 0) { throw 'Spark signature verification failed.' }
```

Record the successful SHA-512 and signature verification in the release
evidence. The archive directory lists the Spark binary and accompanying
`.sha512` and `.asc` files: [Spark 4.1.2 Apache archive](https://archive.apache.org/dist/spark/spark-4.1.2/).

#### Step D — extract Spark and install the Windows helper

Use the `tar.exe` included with current Windows. First verify that PowerShell
can find it, then list the archive contents, and only then extract it. The
commands stop if `tar.exe` is missing or the expected Spark folder already
exists. The final `Get-Item` command proves that the exact files required by
`test-depo-spark.ps1` exist.

```powershell
$tar = Get-Command tar.exe -ErrorAction Stop
& $tar.Source -tzf $sparkArchive | Select-Object -First 10
if (Test-Path $sparkHome) { throw "Spark folder already exists: $sparkHome. Verify it, or remove it before extracting again." }
& $tar.Source -xzf $sparkArchive -C C:\DEPO\runtime
if (-not (Test-Path "$sparkHome\bin\spark-submit.cmd")) { throw "Spark extraction did not create $sparkHome" }
```

##### Step D1 — obtain an approved Windows Hadoop helper

Microsoft does **not** publish a current supported `winutils.exe` package.
Microsoft's archived 2015 Spark-on-Windows article points to an obsolete
third-party Hortonworks HTTP download; do not use that URL for a customer
installation. Apache Hadoop contains the Windows helper source and looks for
`%HADOOP_HOME%\bin\winutils.exe`, but Apache Hadoop and Apache Spark do not
publish an official Windows `winutils.exe` binary with the Spark archive.

**Why Hadoop 3.4.2:** Spark's `v4.1.2` source sets
`<hadoop.version>3.4.2</hadoop.version>`. The downloaded
`spark-4.1.2-bin-hadoop3.tgz` therefore contains Hadoop 3.4.2 client JARs. Prove
the installed distribution matches before accepting any native helper:

```powershell
$sparkHome = 'C:\DEPO\runtime\spark-4.1.2-bin-hadoop3'
$expectedHadoopJars = @(
  "$sparkHome\jars\hadoop-client-api-3.4.2.jar",
  "$sparkHome\jars\hadoop-client-runtime-3.4.2.jar"
)
$missing = $expectedHadoopJars | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }
if ($missing) { throw "Spark 4.1.2 does not contain the expected Hadoop 3.4.2 JARs: $($missing -join ', ')" }
Get-Item $expectedHadoopJars | Select-Object Name, Length
```

There is no official URL from which to download a precompiled Hadoop 3.4.2
`winutils.exe`. The official download is **source code**. Build it once on an
approved Windows build workstation and publish the resulting binaries to the
customer's internal software repository. Do not build Hadoop on the production
application VM.

###### Step D1a — download and verify the official Hadoop 3.4.2 source

Run in PowerShell on the build workstation:

```powershell
$hadoopVersion = '3.4.2'
$downloadRoot = 'C:\DEPO\build-downloads'
$sourceArchive = "$downloadRoot\hadoop-$hadoopVersion-src.tar.gz"
New-Item -ItemType Directory -Force $downloadRoot | Out-Null

Invoke-WebRequest -Uri "https://archive.apache.org/dist/hadoop/common/hadoop-$hadoopVersion/hadoop-$hadoopVersion-src.tar.gz" -OutFile $sourceArchive
Invoke-WebRequest -Uri "https://archive.apache.org/dist/hadoop/common/hadoop-$hadoopVersion/hadoop-$hadoopVersion-src.tar.gz.sha512" -OutFile "$sourceArchive.sha512"
Invoke-WebRequest -Uri "https://archive.apache.org/dist/hadoop/common/hadoop-$hadoopVersion/hadoop-$hadoopVersion-src.tar.gz.asc" -OutFile "$sourceArchive.asc"

$expected = ((Get-Content "$sourceArchive.sha512" -Raw) -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash $sourceArchive -Algorithm SHA512).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Hadoop 3.4.2 source SHA-512 verification failed.' }
Write-Host 'Hadoop 3.4.2 source SHA-512 verification passed.'
```

If GnuPG is approved on the build workstation, also verify the Apache release
signature:

```powershell
Invoke-WebRequest -Uri 'https://downloads.apache.org/hadoop/common/KEYS' -OutFile "$downloadRoot\apache-hadoop-KEYS"
gpg --import "$downloadRoot\apache-hadoop-KEYS"
gpg --verify "$sourceArchive.asc" $sourceArchive
if ($LASTEXITCODE -ne 0) { throw 'Hadoop 3.4.2 source signature verification failed.' }
```

###### Step D1b — build the 64-bit Windows native distribution

The Hadoop 3.4.2 `BUILDING.txt` requires Windows 10, JDK 8, Maven, CMake 3.19+
and Visual Studio 2019. This JDK 8 is used only on the build workstation; DEPO
continues to use JDK 21 at runtime. Install the **Desktop development with C++**
workload and MSVC v142 toolset with Visual Studio 2019. Install Git for Windows,
Maven and CMake, and ensure `git.exe`, `mvn.cmd`, `cmake.exe` and the JDK 8
`java.exe` are on `PATH`.

The repository automates source download, SHA-512 and PGP verification, pinned
vcpkg dependency installation, compilation, output collection and SHA-256
manifest creation. From **x64 Native Tools Command Prompt for VS 2019**, run:

```powershell
Set-Location <repository-root>
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\infra\windows\build-depo-hadoop-windows.ps1 `
  -BuildRoot 'C:\DEPO\hadoop-build' `
  -VcpkgRoot 'C:\vcpkg' `
  -OutputDirectory 'C:\DEPO\approved\hadoop-3.4.2-windows-x64'
```

Do not use `-SkipSignatureVerification` for a production package. The switch is
provided only for an isolated build environment where the customer's approved
supply-chain process performs PGP verification outside this script. A failed
download, checksum, signature, dependency installation, compilation or missing
output stops the script. A successful run produces:

```text
C:\DEPO\approved\hadoop-3.4.2-windows-x64\
├── build-manifest.json
└── bin\
    ├── winutils.exe
    └── hadoop.dll
```

The following commands show the underlying Apache build procedure and provide
a manual recovery path if the automated script reports a workstation-specific
toolchain problem.

Open **x64 Native Tools Command Prompt for VS 2019** and execute the following
commands. Hadoop requires a short source path:

```bat
mkdir C:\hdc
cd /d C:\hdc
tar -xzf C:\DEPO\build-downloads\hadoop-3.4.2-src.tar.gz

cd /d C:\
git clone https://github.com/microsoft/vcpkg.git C:\vcpkg
cd /d C:\vcpkg
git checkout 7ffa425e1db8b0c3edf9c50f2f3a0f25a324541d
call bootstrap-vcpkg.bat
vcpkg.exe install boost:x64-windows protobuf:x64-windows openssl:x64-windows zlib:x64-windows

cd /d C:\hdc\hadoop-3.4.2-src
set classpath=
set PROTOBUF_HOME=C:\vcpkg\installed\x64-windows
set MAVEN_OPTS=-Xmx2048M -Xss128M
mvn clean package -Dhttps.protocols=TLSv1.2 -DskipTests -DskipDocs -Pnative-win,dist -Drequire.openssl -Drequire.test.libhadoop -Pyarn-ui -Dshell-executable=C:\Git\bin\bash.exe -Dtar -Dopenssl.prefix=C:\vcpkg\installed\x64-windows -Dcmake.prefix.path=C:\vcpkg\installed\x64-windows -Dwindows.cmake.toolchain.file=C:\vcpkg\scripts\buildsystems\vcpkg.cmake -Dwindows.cmake.build.type=RelWithDebInfo -Dwindows.build.hdfspp.dll=off -Dwindows.no.sasl=on -Duse.platformToolsetVersion=v142
if errorlevel 1 exit /b 1
```

The command is the Apache Hadoop 3.4.2 Windows build command with the
`native-win` profile. After it succeeds, locate and stage the two files:

```powershell
$sourceRoot = 'C:\hdc\hadoop-3.4.2-src'
$winutils = Get-ChildItem $sourceRoot -Recurse -Filter winutils.exe | Where-Object FullName -Match '\\target\\bin\\winutils\.exe$' | Select-Object -First 1
$hadoopDll = Get-ChildItem $sourceRoot -Recurse -Filter hadoop.dll | Where-Object FullName -Match '\\target\\bin\\hadoop\.dll$' | Select-Object -First 1
if (-not $winutils -or -not $hadoopDll) { throw 'The Hadoop Windows build did not produce winutils.exe and hadoop.dll.' }

$approvedOutput = 'C:\DEPO\approved\hadoop-3.4.2-windows-x64\bin'
New-Item -ItemType Directory -Force $approvedOutput | Out-Null
Copy-Item -LiteralPath $winutils.FullName -Destination "$approvedOutput\winutils.exe"
Copy-Item -LiteralPath $hadoopDll.FullName -Destination "$approvedOutput\hadoop.dll"
Get-FileHash "$approvedOutput\winutils.exe", "$approvedOutput\hadoop.dll" -Algorithm SHA256
```

Security must scan and approve these two files and their recorded SHA-256
values. Publish that exact folder in the customer's internal repository. The
application administrator downloads the approved internal package into
`C:\DEPO\downloads\hadoop-helper` and continues with Step D2 below.

The customer's security or platform team must provide these exact files through
its approved software repository or build them from the matching Apache Hadoop
source and publish them internally:

| Required file | Purpose |
| --- | --- |
| `winutils.exe` | Hadoop local-filesystem permission and helper operations on native Windows |
| `hadoop.dll` | Required native Hadoop library for the validated Windows runtime |

The internal package owner must provide a SHA-256 value for each file. Copy the
approved files to a staging folder such as `C:\DEPO\downloads\hadoop-helper`.
Do not put either binary in this Git repository and do not copy `hadoop.dll` to
`C:\Windows\System32`.

Confirm the supplied filenames and calculate the hashes:

```powershell
$helperSource = 'C:\DEPO\downloads\hadoop-helper'
Get-Item "$helperSource\winutils.exe", "$helperSource\hadoop.dll"
Get-FileHash "$helperSource\winutils.exe" -Algorithm SHA256
Get-FileHash "$helperSource\hadoop.dll" -Algorithm SHA256
```

Compare those values with the hashes published in the customer's software
approval record. A locally calculated hash alone does not establish trust.

##### Step D2 — install and validate the helper

Run the repository installer from the repository root. Replace the two example
hashes with the approved 64-character SHA-256 values:

```powershell
$helperSource = 'C:\DEPO\downloads\hadoop-helper'
$winutilsSha256 = '<approved-64-character-winutils-sha256>'
$hadoopDllSha256 = '<approved-64-character-hadoop-dll-sha256>'

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\infra\windows\install-depo-winutils.ps1 `
  -WinutilsPath "$helperSource\winutils.exe" `
  -WinutilsSha256 $winutilsSha256 `
  -HadoopDllPath "$helperSource\hadoop.dll" `
  -HadoopDllSha256 $hadoopDllSha256 `
  -Destination 'C:\DEPO\runtime\hadoop'
```

The script refuses a hash mismatch and refuses to overwrite an existing helper.
Use `-Force` only for an approved replacement. It installs the files under
`C:\DEPO\runtime\hadoop\bin`, removes the downloaded-file block after hash
approval, runs `winutils.exe ls`, and prints the installed hashes.

Verify the complete runtime layout:

```powershell
$hadoopHome = 'C:\DEPO\runtime\hadoop'
Get-Item "$sparkHome\bin\spark-submit.cmd",
  "$sparkHome\python\lib\pyspark.zip",
  "$sparkHome\jars\spark-core_2.13-4.1.2.jar",
  "$hadoopHome\bin\winutils.exe",
  "$hadoopHome\bin\hadoop.dll",
  "$jdkHome\bin\java.exe"

& "$hadoopHome\bin\winutils.exe" ls $hadoopHome
if ($LASTEXITCODE -ne 0) { throw 'winutils.exe validation failed.' }
```

Do not run `pip install pyspark`; the backend uses the PySpark and Py4J archives
already inside `$sparkHome`. Continue with section 2.3 to write these paths to
the root `.env.local`. The deployment scripts load root `.env.local` into the
Windows **process environment** each time they run; do not set permanent
machine-wide `SPARK_HOME`, `JAVA_HOME`, or `HADOOP_HOME` values. After the
backend install in section 3, execute this smoke test:

```powershell
# Spark configuration must be present in root .env.local first.
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local
```

Continue with the application installer in section 3, then complete section 4.
Spark jobs remain governed by the Data Pipeline
service and cannot write Neo4j directly. Add `-EnableNeo4jSparkConnector` only
after the regular smoke test passes and the Neo4j connection check in the
installer succeeds.

### 1.3 Install and integrate Spark on Linux

Use this path when the DEPO application and local Spark runtime run on a
supported 64-bit Linux VM. Linux does **not** use `winutils.exe`, `hadoop.dll`,
or `DEPO_HADOOP_HOME`. The supported release baseline is CPython 3.12, JDK 21,
Node.js 24 or newer, and `spark-4.1.2-bin-hadoop3.tgz`.

#### Copy-and-paste example: Ubuntu application VM

This example uses the following concrete deployment. Substitute the four
customer connection values when the configuration script prompts for them:

```text
Release files already extracted at: /tmp/PMem-release
DEPO installation:                  /opt/depo/app
PostgreSQL:                         10.20.30.40:5432/depo
Neo4j:                              graph.customer.example:7687
Frontend origin:                    https://depo.customer.example
Linux service account:              depo
```

Copy and paste this first block as an administrator. It stops on the first
failure and does not start any DEPO service:

```bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y openjdk-21-jdk python3.12 python3.12-venv curl tar gnupg ca-certificates openssl
node --version
npm --version
sudo useradd --system --create-home --shell /usr/sbin/nologin depo 2>/dev/null || true
sudo install -d -o depo -g depo -m 0750 /opt/depo/app /opt/depo/runtime /opt/depo/downloads /opt/depo/drivers
sudo install -d -o depo -g depo -m 0750 /var/lib/depo/artifacts /var/lib/depo/spark-output
sudo cp -a /tmp/PMem-release/. /opt/depo/app/
sudo chown -R depo:depo /opt/depo/app
cd /opt/depo/app
sudo -u depo bash infra/linux/diagnose-depo-linux.sh .env.local || true
sudo -u depo bash infra/linux/install-spark-linux.sh --install-root /opt/depo/runtime --download-root /opt/depo/downloads
```

The first diagnostic is expected to report that `.env.local`, the Spark runtime,
and possibly the reviewed Linux dependency lock are absent. It is included here
so the operator sees the exact remaining prerequisites before installation.
`node --version` must report `v24` or newer and `npm --version` must report 10.2
or newer; if either command is missing, stop and install the approved Node.js 24
package before continuing.

Create both configuration files with the interactive configurator. The
PostgreSQL URL and Neo4j password prompts do not echo their input. API/service
tokens are generated automatically and are never printed:

```bash
cd /opt/depo/app
sudo -u depo -H bash infra/linux/configure-depo-linux.sh /opt/depo/app/.env.local
```

Enter values in this form when prompted:

```text
PostgreSQL URL: postgresql://depo_app:<actual-password>@10.20.30.40:5432/depo?sslmode=require
Neo4j URI: neo4j+s://graph.customer.example:7687
Neo4j database name: ontology
Frontend origins: https://depo.customer.example,http://localhost:3000
Neo4j username: depo_graph
Neo4j password: <actual-password>
```

The localhost origin permits the temporary SSH-forwarded browser test below.
Do not type the password angle brackets. Enter the real password supplied by
the customer secret manager. If the Neo4j server intentionally has authentication disabled,
run the configurator with `NEO4J_AUTH_MODE=none`; it will not ask for a username
or password:

```bash
sudo -u depo -H env NEO4J_AUTH_MODE=none NEO4J_TLS_MODE=disabled NEO4J_ENCRYPTED=false NEO4J_TLS_VERIFY=false \
  bash infra/linux/configure-depo-linux.sh /opt/depo/app/.env.local
```

Continue only after the release team has supplied the reviewed Linux lock at
`backend/requirements-linux-lock.txt`. Then copy and paste:

```bash
cd /opt/depo/app
sudo -u depo bash infra/linux/diagnose-depo-linux.sh /opt/depo/app/.env.local
sudo -u depo bash infra/linux/install-depo-linux.sh --env-file /opt/depo/app/.env.local
sudo -u depo bash infra/linux/test-depo-spark.sh /opt/depo/app/.env.local
sudo -u depo bash infra/linux/start-depo-services.sh /opt/depo/app/.env.local
curl --fail http://127.0.0.1:8013/readyz
curl --fail http://127.0.0.1:8019/readyz
```

For a temporary browser smoke test, use a second terminal:

```bash
cd /opt/depo/app
sudo -u depo backend/.dt_venv/bin/python -m http.server 3000 --bind 127.0.0.1 --directory frontend/dist
```

On the administrator workstation, create a temporary SSH tunnel. Replace
`depo-admin@linux-vm` with the approved SSH account and hostname:

```bash
ssh -N \
  -L 3000:127.0.0.1:3000 \
  -L 8010:127.0.0.1:8010 -L 8011:127.0.0.1:8011 \
  -L 8012:127.0.0.1:8012 -L 8013:127.0.0.1:8013 \
  -L 8014:127.0.0.1:8014 -L 8015:127.0.0.1:8015 \
  -L 8016:127.0.0.1:8016 -L 8017:127.0.0.1:8017 \
  -L 8018:127.0.0.1:8018 -L 8019:127.0.0.1:8019 \
  depo-admin@linux-vm
```

Open `http://localhost:3000`. Stop the Python server and SSH tunnel with
`Ctrl+C` in their respective terminals.
For production, publish `frontend/dist` through the approved HTTPS reverse proxy;
the Python static server is only an installation test.

In token-authentication mode, open **Chat → Connection credentials** and paste
the `GRAPH_READ_TOKEN` value from the root `.env.local`. The UI keeps it only in
browser memory. An administrator can display that one value on the application
VM with the following command; do not copy it into `frontend/.env.local`:

```bash
sudo -u depo awk -F= '$1=="GRAPH_READ_TOKEN" {print $2}' /opt/depo/app/.env.local
```

The Linux sequence is:

| Order | Command | Result |
| --- | --- | --- |
| 1 | Install OS prerequisites | Java, Python, Node, GnuPG, curl and tar available |
| 2 | Run `install-spark-linux.sh` | Apache archive and signature verified, then Spark extracted |
| 3 | Complete root `.env.local` | DEPO, PostgreSQL, Neo4j and Spark configured in one service environment |
| 4 | Run `install-depo-linux.sh` | Backend virtual environment and frontend production build created |
| 5 | Run `test-depo-spark.sh` | Spark and enabled connectors execute real read-only jobs |
| 6 | Run `start-depo-services.sh` | Ten APIs and three workers start and pass readiness checks |

#### Linux Step A — install operating-system prerequisites

Run one block appropriate to the customer VM. Package installation requires an
approved repository and an administrator account.

Ubuntu 24.04 example:

```bash
sudo apt-get update
sudo apt-get install -y openjdk-21-jdk python3.12 python3.12-venv curl tar gnupg ca-certificates
java -version
python3.12 --version
```

Install Node.js 24 from the customer's approved package repository, then verify:

```bash
node --version
npm --version
```

The Node result must be `v24` or newer. Do not use a personal NVM installation
for a production service account.

RHEL-compatible example, using the customer-approved Python 3.12 and Node.js 24
repositories:

```bash
sudo dnf install -y java-21-openjdk-devel python3.12 curl tar gnupg2 ca-certificates
java -version
python3.12 --version
node --version
npm --version
```

#### Linux Step B — create the service directories

This example installs customer-managed runtime files under `/opt/depo` and
writable data under `/var/lib/depo`. Replace `depo` with the actual service
account only if the customer chose a different account.

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin depo 2>/dev/null || true
sudo install -d -o depo -g depo -m 0750 /opt/depo/runtime /opt/depo/downloads /opt/depo/drivers
sudo install -d -o depo -g depo -m 0750 /var/lib/depo/artifacts /var/lib/depo/spark-output
```

Clone or copy the reviewed release to `/opt/depo/app`, then assign it to the
service account according to the customer's deployment policy. The remaining
commands assume that `/opt/depo/app` is the repository root:

```bash
cd /opt/depo/app
chmod 0750 infra/linux/*.sh
```

#### Linux Step C — download, authenticate and extract Apache Spark

The installer downloads these exact official artifacts:

```text
spark-4.1.2-bin-hadoop3.tgz
spark-4.1.2-bin-hadoop3.tgz.sha512
spark-4.1.2-bin-hadoop3.tgz.asc
apache-spark-KEYS
```

It validates SHA-512, imports the Apache Spark release keys into a temporary
GnuPG home, validates the detached signature, validates the tar archive, and
refuses to overwrite an existing runtime. Run it as the service account so no
runtime file is owned by root:

```bash
sudo -u depo bash infra/linux/install-spark-linux.sh \
  --install-root /opt/depo/runtime \
  --download-root /opt/depo/downloads
```

Successful output prints the detected JDK path and exact Spark path. Verify the
installed files explicitly:

```bash
sudo -u depo test -x /opt/depo/runtime/spark-4.1.2-bin-hadoop3/bin/spark-submit
sudo -u depo test -f /opt/depo/runtime/spark-4.1.2-bin-hadoop3/python/lib/pyspark.zip
sudo -u depo find /opt/depo/runtime/spark-4.1.2-bin-hadoop3/python/lib -maxdepth 1 -name 'py4j-*-src.zip' -print
```

#### Linux Step D — create both `.env.local` files

Run the configurator. It asks only for customer-specific PostgreSQL, Neo4j and
frontend values, generates distinct service tokens, writes root `.env.local`,
writes `frontend/.env.local`, applies restrictive permissions, and refuses to
overwrite either existing file:

```bash
cd /opt/depo/app
sudo -u depo -H bash infra/linux/configure-depo-linux.sh /opt/depo/app/.env.local
```

The generated file uses these Linux-specific values by default:

```dotenv
ARTIFACT_STORAGE=/var/lib/depo/artifacts
DEPO_POSTGRES_MODE=external
DEPO_SPARK_ENABLED=true
DEPO_SPARK_HOME=/opt/depo/runtime/spark-4.1.2-bin-hadoop3
DEPO_JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
DEPO_SPARK_MASTER=local[2]
DEPO_SPARK_OUTPUT_ROOT=/var/lib/depo/spark-output
DEPO_PIPELINE_EXECUTION_MODE=worker
DEPO_PIPELINE_SCHEDULER_ENABLED=false
DEPO_SPARK_NEO4J_ENABLED=false
DEPO_SPARK_POSTGRES_ENABLED=false
```

On RHEL, determine the exact JDK directory rather than copying the Ubuntu path:

```bash
dirname "$(dirname "$(readlink -f "$(command -v java)")")"
```

Use that output as `DEPO_JAVA_HOME`. Do not set `DEPO_HADOOP_HOME` on Linux.

To enable the official Neo4j Spark connector after the base smoke test passes:

```dotenv
DEPO_SPARK_NEO4J_ENABLED=true
DEPO_SPARK_NEO4J_PACKAGE=org.neo4j.connectors:spark:6.0.0-s_2.13
```

The normal `NEO4J_URI`, `NEO4J_DATABASE`, `NEO4J_AUTH_MODE`, `NEO4J_USER`, and
`NEO4J_PASS` values are reused. With an intentionally unsecured private local
Neo4j instance, set `NEO4J_AUTH_MODE=none`; credentials are then not required.
The first connector execution resolves Maven artifacts, so an offline customer
must mirror and approve that package in its internal Maven repository.

To enable Spark JDBC reads from the external PostgreSQL VM, place the approved
PostgreSQL JDBC JAR on the application VM and configure:

```dotenv
DEPO_SPARK_POSTGRES_ENABLED=true
DEPO_SPARK_POSTGRES_DRIVER_JAR=/opt/depo/drivers/postgresql-42.7.13.jar
```

The connector reuses `DEPO_DATABASE_URL`. The JDBC test is read-only and does
not create or alter the PostgreSQL schema.

#### Linux Step E — install DEPO and build the frontend

The repository's `backend/requirements-lock.txt` is explicitly generated for
Windows x64 and must not be reused on Linux. The customer Linux release package
must contain `backend/requirements-linux-lock.txt`, generated and reviewed by
the release pipeline for CPython 3.12 on Linux x86_64. Every resolved requirement
must contain an exact version and approved artifact hashes (hashes may continue
onto subsequent lines):

```text
package-name==exact.version --hash=sha256:<approved-linux-artifact-hash>
```

The Linux installer stops when that lock is absent or malformed and never falls
back to an unpinned internet installation. Spark runtime provisioning remains
independent because the repository authenticates the Apache archive using its
published SHA-512 value and detached signature.

On the approved internet-connected Linux x86_64 release builder, with the
reviewed `pip-compile` build tool already installed, generate the lock using:

```bash
bash infra/linux/generate-linux-lock.sh
```

Review and scan the resulting `backend/requirements-linux-lock.txt`, then ship
that exact committed file with the release. Do not generate it on a customer
production VM.

Run the production installer from the repository root:

```bash
cd /opt/depo/app
sudo -u depo bash infra/linux/install-depo-linux.sh --env-file /opt/depo/app/.env.local
```

The installer creates `backend/.dt_venv`, installs the hash-pinned production
dependencies, imports every service, validates every OpenAPI contract, runs
`npm ci`, builds `frontend/dist`, and executes the Spark tests when Spark is
enabled. Use `--skip-frontend` only when the reviewed frontend artifact is
deployed separately. Use `--skip-dependencies` only to revalidate an existing
installation whose virtual environment and frontend dependencies already exist.

#### Linux Step F — run diagnostics independently

Run the same test again whenever Spark, Java, PostgreSQL, Neo4j or connector
configuration changes:

```bash
cd /opt/depo/app
sudo -u depo bash infra/linux/test-depo-spark.sh /opt/depo/app/.env.local
```

With connectors disabled, this executes the deterministic DEPO Spark dataframe
job. With either connector enabled, it additionally performs a real read-only
query against that dependency. A successful command ends with:

```text
DEPO Linux Spark validation passed.
```

#### Linux Step G — start, verify and stop DEPO

Start all ten HTTP services and both workers:

```bash
cd /opt/depo/app
sudo -u depo bash infra/linux/start-depo-services.sh /opt/depo/app/.env.local
```

The launcher applies and verifies PostgreSQL migrations first. It then waits
for every `/readyz` endpoint and rolls back processes started by the command if
any service fails. Logs and PID files are stored under
`logs/linux-services`. Verify the pipeline and graph services:

```bash
curl --fail http://127.0.0.1:8019/readyz
curl --fail http://127.0.0.1:8013/readyz
curl --fail http://127.0.0.1:8019/api/v1/health
```

Stop the deployment cleanly:

```bash
sudo -u depo bash infra/linux/stop-depo-services.sh
```

For an unattended customer deployment, install the supplied hardened `systemd`
unit. It runs as `depo`, protects operating-system paths, prepares the configured
log, artifact and Spark-output directories, and reads secrets through the
lifecycle script rather than copying them into the unit:

```bash
cd /opt/depo/app
sudo bash infra/linux/install-systemd-service.sh /opt/depo/app/.env.local depo
sudo systemctl start depo.service
sudo systemctl status depo.service --no-pager
```

The installer runs `systemd-analyze verify`, reloads systemd, and enables the
unit for boot. Keep `.env.local` readable only by the service account. Diagnose
a failed boot with `journalctl -u depo.service` and the service-specific files
under `logs/linux-services`.

### 1.4 Choose document OCR on Windows; verify it immediately after section 3

DEPO extracts the native PDF text layer first. Scanned PDFs then use the OCR
provider selected by `DOCUMENT_OCR_PROVIDER`. The standard installer installs
both Python adapters; EasyOCR provides an in-process fallback and does not
require a separate Windows executable. Tesseract remains supported when the
customer already operates an approved Tesseract installation.

Do not run the verification commands before the installer. Complete sections 2
and 3 first; then return to this subsection and run these commands from the
repository root after section 3 has created the backend virtual environment:

```powershell
Set-Location 'E:\App\PMem' # Replace only when the repository is elsewhere.
& '.\backend\.dt_venv\Scripts\python.exe' -c "import easyocr, fitz, pypdf, PIL; print('EasyOCR', easyocr.__version__); print('PyMuPDF', fitz.VersionBind); print('pypdf', pypdf.__version__)"
```

For an internet-connected provisioning VM, set the following temporarily in
the root `.env.local` so EasyOCR downloads its signed package-published model
assets on the first controlled OCR smoke test:

```dotenv
DOCUMENT_OCR_PROVIDER=easyocr
DOCUMENT_OCR_LANGUAGES=en
DOCUMENT_EASYOCR_MODEL_DIR=C:\DEPO\models\easyocr
DOCUMENT_EASYOCR_ALLOW_DOWNLOAD=true
DOCUMENT_OCR_GPU=false
DOCUMENT_MAX_OCR_PAGES=100
```

Create the model directory, run the smoke test, then set downloads to `false`:

```powershell
New-Item -ItemType Directory -Force 'C:\DEPO\models\easyocr' | Out-Null
$env:DOCUMENT_OCR_PROVIDER='easyocr'
$env:DOCUMENT_OCR_LANGUAGES='en'
$env:DOCUMENT_EASYOCR_MODEL_DIR='C:\DEPO\models\easyocr'
$env:DOCUMENT_EASYOCR_ALLOW_DOWNLOAD='true'
& '.\backend\.dt_venv\Scripts\python.exe' -c "from backend.Services.document_processor import _easyocr_reader; r=_easyocr_reader(); print(type(r).__name__)"
(Get-ChildItem -LiteralPath 'C:\DEPO\models\easyocr' -File).Name
```

Change `DOCUMENT_EASYOCR_ALLOW_DOWNLOAD=false` in `.env.local` after the model
files exist. Copy the populated model directory through the customer's normal
artifact-verification process when production VMs cannot access the internet.
Never copy IIF's hardcoded `C:\krown_code` path into DEPO configuration.

If the customer selects Tesseract instead, install its approved 64-bit Windows
package, place `tesseract.exe` on the service account's `PATH`, set
`DOCUMENT_OCR_PROVIDER=tesseract`, and verify it from the same PowerShell
session:

```powershell
tesseract --version
& '.\backend\.dt_venv\Scripts\python.exe' -c "from backend.Services.document_processor import runtime_status; import json; print(json.dumps(runtime_status(), indent=2))"
```

The final JSON must show `"ocr_available": true` and the intended
`"ocr_provider"`. OCR output is retained as raw page evidence with provider,
confidence when supplied by EasyOCR, and a SHA-256 text digest. LLM correction
or summarization is a separate review proposal and never replaces raw evidence.

## 2. Create configuration

### There are exactly two `.env.local` files in a standard installation

Create and configure **only these two files**. They are ignored by Git and
must never be copied into a release package or source-control repository.

| File | Who uses it | What it contains | Do not put here |
| --- | --- | --- | --- |
| `.env.local` at the repository root | All ten backend services, migrations, Neo4j checks and Spark scripts | Database and Neo4j credentials, service settings, API keys, Spark settings | Browser configuration |
| `frontend/.env.local` | The Vite frontend build only | Public HTTPS API gateway address and optional public browser settings | Passwords, API keys, database URLs, Neo4j credentials, Spark paths |

`config/deployment.env.example` and `config/spark.env.example` are **templates**,
not extra environment files. `standalone/ontology_agentic_service/.env.example`
belongs only to that separate standalone component; do not create it for this
application deployment.

Both environment files are UTF-8 text containing one `KEY=value` setting per
physical line. Do not paste PowerShell prompts, `$env:KEY=...` commands, JSON,
Markdown backticks or wrapped value continuations into them. In the root file,
spaces around `=` and balanced single/double quotes are supported; quotes do not
expand variables or execute commands. Full-line `#` comments and comments after
whitespace are supported. Quote a value if a whitespace-plus-`#` sequence is part
of the value. Keep Windows paths literal, for example `ARTIFACT_STORAGE=C:\DEPO\data\artifacts`.

Before starting services, validate the root file from the repository root without
printing any credentials:

```powershell
. .\infra\windows\runtime-config.ps1
Read-DepoEnvironment -Root (Get-Location).Path -EnvFile '.env.local' | Out-Null
Write-Host 'PASS: environment file syntax'
```

A parser failure reports the file and one-based line number. Open that line in
an editor, correct its syntax and repeat validation. Values are hidden in error
messages. Syntax validation does not verify database connectivity or required
customer settings; continue with the deployment diagnostic afterward.

### 2.1 Create the root server file

From the repository root, run this command once. It creates both supported
configuration files, copies the reviewed templates and generates distinct
server API-key values without printing them. Use an empty `GatewayUrl` only for
a direct local installation.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\configure-depo.ps1 `
  -AuthMode token `
  -GatewayUrl 'https://api.customer.example'
```

Open the new root `.env.local` and edit these values in order:

For customer-isolated agent memory, add a unique scope and retention period.
Use the actual customer and program identifiers; do not copy the example value
unchanged. Leave `AGENT_MEMORY_ENABLED=false` when Neo4j conversation memory is
not approved. PostgreSQL stores session metadata and execution traces; companion
conversation memory requires the Neo4j memory option.

```env
DEPO_TENANT_ID=customer-acme
DEPO_PROJECT_ID=program-alpha
AGENT_MEMORY_ENABLED=true
AGENT_MEMORY_SCOPE=customer-acme:program-alpha
AGENT_MEMORY_QUERY_TIMEOUT=5
AGENT_MEMORY_RETENTION_DAYS=30
AGENT_SESSION_IDLE_SECONDS=1800
AGENT_SESSION_MAX_SECONDS=86400
AGENTIC_RUN_TIMEOUT_SECONDS=900
LLM_REQUEST_TIMEOUT_SECONDS=300
AGENT_PROMPT_VERSION=1
AGENT_FAILURE_RATE_ALERT_THRESHOLD=0.2
AGENT_STUCK_RUN_SECONDS=900
```

Memory flags accept `true` or `false`; the query timeout must be an integer from
1 to 30 seconds. Explicit scopes must be complete and no longer than 256
characters. If omitted, a scope can be derived from valid tenant/project IDs.
Scopes are rejected rather than truncated. New memory IDs use versioned JSON
encoding; existing chat history remains readable through scope- and session-bound
legacy keys. New writes upgrade a matching legacy session without dropping its
uniqueness constraint. Historical records are retained.

Conversation/reasoning memory uses `AGENT_MEMORY_NEO4J_DATABASE` when configured,
otherwise `NEO4J_DATABASE`. Approved mapping facts remain in `NEO4J_DATABASE` so
they commit with graph links and publication receipts. Fact reuse resolves
ontology prefixes to registered ontology IDs and reads that same graph database.
The agent maintenance task initializes both databases when memory is enabled;
the configured Neo4j account needs access and schema privileges in each.

Authenticated `GET /api/v1/memory/status` on the agentic service probes read
connectivity and reports `status`, `write_status`, `schema_status`, `database`,
`facts_database` and `facts_status`. Enabling memory alone does not verify storage.
Write status becomes available after a successful memory mutation. Schema checks
verify constraint definitions, refresh per database, and never automatically drop
constraints. Memory failures remain best effort and are reported separately from
chat generation. Retention applies to conversation sessions and their traces;
approved mapping facts remain retained with their publication evidence.

The companion creates a session on the first request without `session_id`.
Reuse the returned ID with the same authenticated identity. The defaults expire
it after 30 minutes without a request or 24 hours from creation; activity does
not extend the maximum lifetime. HTTP 410 means expired and HTTP 404 means
unknown: start without an ID. The frontend retries read-only retrieval once with
a fresh session for these responses. Separate users need separate credentials;
a shared API key represents a shared identity. Every five minutes, the running
Agentic service cleans expired session metadata and prunes scoped graph memory.
Expired memory is also excluded during retrieval.

Workflow execution has a five-minute deadline by default. Terminal states are
`completed`, `failed`, `timed_out` and `interrupted`. Error responses include
`X-DEPO-Run-ID` after a run was created. Read `GET /api/v1/workflow-runs/{run_id}`
before retrying. If `reconciliation_required=true`, a downstream write may have
executed: check its receipt first. After a process interruption, reads project
`interrupted` once the persisted deadline passes. This does not prove whether a
downstream write completed and does not automatically repeat it.

Use `POST /api/v1/runs` with `agent_id`, `tool_id` and `inputs`; use
`POST /api/v1/workflow-runs` with `workflow_id`, optional `step_inputs` (one object
per step), and approval fields when required. Only completed prior steps can be
referenced with `$steps.1.result` or `$steps.1.result.field`. Arbitrary imported
OpenAPI operations are not executable. Chat jobs run synchronously and return
HTTP 200 with `status=completed`; SSE emits completed-response events rather
than progressive LLM generation. JSON-LD artifacts must use `.jsonld` and inline
contexts; remote contexts and `@import` are rejected.

After the installer starts the Agentic service, verify its monitoring loop as
part of Section 4.7. Do not run these commands during configuration. The
summary and run endpoints use graph-read authentication. The Prometheus
endpoint exposes aggregate operational values and contains no prompt or
tool-input content.

```powershell
Invoke-RestMethod http://127.0.0.1:8012/healthz
Invoke-RestMethod http://127.0.0.1:8012/api/v1/observability/summary `
  -Headers @{ Authorization = "Bearer $env:GRAPH_READ_TOKEN" }
Invoke-WebRequest http://127.0.0.1:8012/api/v1/metrics | Select-Object -ExpandProperty Content
```

1. Set `DEPO_DATABASE_URL` to the PostgreSQL connection URL and
   `DEPO_DATABASE_SCHEMA=semantic` (or the customer-approved schema). For the
   local Windows service installed in section 1.1, also set
   `DEPO_POSTGRES_MODE=service` and `DEPO_POSTGRES_SERVICE_NAME` to the exact
   Windows service `Name`. For a managed or remote database, retain
   `DEPO_POSTGRES_MODE=external` and leave `DEPO_POSTGRES_SERVICE_NAME` empty.
2. Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS` and `NEO4J_DATABASE`. Aura
   exports named `NEO4J_URL`, `NEO4J_USERNAME` and `NEO4J_PASSWORD` are also
   accepted by Windows installation, diagnostics and service startup. They are
   normalized to `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASS` before launching
   Python. Use one name per setting; conflicting concrete aliases are rejected
   without printing values. Keep the secure production defaults whenever
   the server supports TLS:

   ```dotenv
   NEO4J_URI=neo4j+s://graph.customer.example
   NEO4J_TLS_MODE=required
   NEO4J_ENCRYPTED=true
   NEO4J_TLS_VERIFY=true
   ```

   Installation reads the repository-root `.env.local` by default and prints its
   selected full path. The frontend `.env.local` contains browser configuration
   and cannot supply database credentials. To select an existing deployment file:

   ```powershell
   Set-Location 'E:\App\PMem'
   .\install-depo.ps1 -EnvFile 'E:\App\PMem\.env.local'
   ```

   If preflight reports `Missing Neo4j setting: NEO4J_URI`, complete that selected
   file with the existing database URI (`NEO4J_URI` or `NEO4J_URL`) and database
   name. A valid alias takes precedence over an empty/template canonical value.
   `configure-depo.ps1 -UpdateMissing` preserves existing Neo4j aliases instead of
   appending canonical placeholders over them. Increasing service timeouts does
   not correct a missing configuration setting.

   Upload limits are integer byte counts in the server file. For a 500-MiB
   ingestion limit, use exactly `DEPO_MAX_INGEST_BYTES=524288000`; for a 64-MiB
   SysML snapshot limit, use `SYSML_V2_MAX_SNAPSHOT_BYTES=67108864`. Do not append
   `MB`, `MiB`, `cls` or a PowerShell command. Invalid limits are rejected with
   the selected file path and line number before dependency installation,
   credential import or service launch. If ingestion exited with
   `DEPO_MAX_INGEST_BYTES must be an integer`, correct that line before retrying
   the same installation/start command; a larger readiness timeout cannot
   repair an import exception.

   For an on-premises server on a trusted private network that does not provide
   TLS, configure the exception explicitly. Authentication can remain enabled:

   ```dotenv
   NEO4J_URI=bolt://10.20.30.40:7687
   NEO4J_AUTH_MODE=token
   NEO4J_TLS_MODE=disabled
   NEO4J_ENCRYPTED=false
   NEO4J_TLS_VERIFY=false
   NEO4J_USER=depo_graph
   NEO4J_PASS=<password>
   NEO4J_DATABASE=neo4j
   ```

   If that private Neo4j server also has authentication disabled, change only
   `NEO4J_AUTH_MODE=none` and leave `NEO4J_USER` and `NEO4J_PASS` empty. The
   explicit TLS mode prevents an accidental URI downgrade; production rejects
   non-TLS URIs unless `NEO4J_TLS_MODE=disabled` is present.
3. Set `ALLOWED_ORIGINS` to the actual browser origin (HTTP or HTTPS), for
   example `ALLOWED_ORIGINS=http://10.10.12.21:3000` for a private-network
   frontend, or `ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000`
   when browsing on the application VM. Both profiles accept these exact
   origins. Use no path or trailing slash. Set
   `OSLC_BASE_URL` to the reachable API base using HTTP or HTTPS. For direct
   access to the OSLC service on an application VM at `10.10.12.21`, use
   `OSLC_BASE_URL=http://10.10.12.21:8015`. For access only on that VM, use
   `OSLC_BASE_URL=http://127.0.0.1:8015`. A gateway example is
   `OSLC_BASE_URL=https://api.customer.example`. Replace example addresses with
   the actual deployment address. Both Bootstrap and Production support HTTP;
   do not include credentials, placeholders, query parameters, fragments or the
   `/oslc` resource suffix. Restart services after changing this published base.
   Set `ARTIFACT_STORAGE=C:\DEPO\data\artifacts`, create that directory, and
   grant the DEPO service account Modify permission. The API services and the
   data-pipeline worker must resolve this exact same absolute path.
4. Keep `AUTH_MODE=token`. This delivery uses API keys; it does not require
   Entra or GitHub Actions. Do not replace the generated token values unless
   the customer secret-management process supplies approved replacements.
   Confirm the generated root file contains distinct non-placeholder values
   for `GRAPH_READ_TOKEN`, `GRAPH_PUBLICATION_TOKEN`,
   `ONTOLOGY_APPROVAL_TOKEN`, `DATA_PRODUCT_APPROVAL_TOKEN`,
   `DATA_JOB_EXECUTION_TOKEN`, `INGESTION_WRITE_TOKEN`, and
   `AGENTIC_APPROVAL_TOKEN`. The API gateway supplies the appropriate token to
   backend requests; never put these server secrets in `frontend/.env.local`.
5. Leave all `DEPO_SPARK_*` values out until step 2.3 unless Spark is part of
   this installation.

Ontology agents are deterministic by default. Keep
`ONTOLOGY_AGENT_LLM_ENABLED=false` for the initial installation. To enable
review-only LLM suggestions later, configure the existing Ollama or Azure
provider in the server environment, set `ONTOLOGY_AGENT_LLM_ENABLED=true`, and
restart the Agentic service. The LLM can suggest validation questions; it cannot
approve mappings or publish to Neo4j. Keep
`ONTOLOGY_AGENT_ALLOWED_ROOTS` limited to approved ontology data directories.
Keep `ONTOLOGY_AGENT_MAX_BYTES=26214400` unless the customer has approved a
different artifact limit.

The shared parser rejects duplicate keys before changing the process
environment. Edit a key in place; never append another line with the same key.

### 2.2 Create the frontend browser file

The `configure-depo.ps1` command in Section 2.1 already created this file and
set the public API gateway URL. A browser can read every `VITE_*` value, so this
file must contain no credentials. Open it only to review the generated value.

```powershell
notepad .\frontend\.env.local
```

For a customer deployment, set this single line and leave the individual
service URLs commented unless the customer deliberately exposes separate
gateway routes:

```text
VITE_API_GATEWAY_URL=https://api.customer.example
```

For a local developer installation, leave `VITE_API_GATEWAY_URL` empty. The
frontend then uses the configured local service inventory.

For a local installation without an API gateway, use this command instead of
the customer-gateway example in Section 2.1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\configure-depo.ps1 -AuthMode token -GatewayUrl ''
notepad .\frontend\.env.local
```

Keep this line empty in the file:

```text
VITE_API_GATEWAY_URL=
```

For the current Windows installation with direct local service access, no
gateway and no Spark, verify these exact values before running the installer.
The first block belongs in the **root** `E:\App\PMem\.env.local`:

```dotenv
ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
DEPO_SERVICE_HOST=127.0.0.1
DEPO_PIPELINE_EXECUTION_MODE=worker
DEPO_SPARK_ENABLED=false
DEPO_SPARK_NEO4J_ENABLED=false
DEPO_SPARK_POSTGRES_ENABLED=false
DEPO_PIPELINE_SCHEDULER_ENABLED=false
```

The durable `data-pipeline-worker` is required in `worker` mode even when
`DEPO_SPARK_ENABLED=false`; it claims approved jobs from PostgreSQL and can run
non-Spark handlers. Spark, its connectors, and its scheduler remain disabled.
The second block belongs in `E:\App\PMem\frontend\.env.local`:

```dotenv
VITE_API_GATEWAY_URL=
```

Do not put `ALLOWED_ORIGINS` or server API keys in the frontend file. If the
browser runs on another machine, the local verification server bound to
`127.0.0.1` is not externally reachable; deploy `frontend\dist` through the
customer HTTPS web server and use that exact HTTPS origin instead.

Save the file and return to the repository root. Do not run `npm ci`, build, or
start the frontend yet; the single installer in Section 3 performs the clean
frontend installation and production build. Section 4.4 starts the completed
build for the local browser smoke test. Open `http://127.0.0.1:3000/` only
after reaching that section, and use **Ctrl+F5** after rebuilding.
The ontology registry request must go to
`http://127.0.0.1:8014/api/v1/ontology/registered`. If that endpoint returns
HTTP 200 with an `ontologies` array but the UI is blank, rebuild after checking
that `VITE_API_GATEWAY_URL` is still empty; Vite embeds environment values at
build time.

### 2.3 Add optional Spark settings to the root server file

For Spark, merge only the required values from `config/spark.env.example` into
the existing **root** `.env.local`. Do not create `spark.env.local`.
Add these values after the database and Neo4j settings:
`DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`, `DEPO_HADOOP_HOME`,
`DEPO_SPARK_OUTPUT_ROOT` and `DEPO_SPARK_MASTER`.

This release uses an in-process `SparkSession` on the Windows application VM.
Apache Spark Connect was assessed but is not enabled because it requires a
separately operated Spark Connect server endpoint, and this customer topology
currently has no Linux or managed Spark cluster. Spark Connect is the preferred
future production topology when that server exists: the Windows application VM
then acts only as a client and no longer needs a local Spark JVM or
`winutils.exe`. PostgreSQL JDBC remains a data-source connector in either
topology; it is not a substitute for Spark Connect.

Example for an installation under `C:\DEPO\runtime`. This command updates each
Spark key in place, so it is safe to run again after changing a path:

```powershell
$sparkSettings = @{
  DEPO_SPARK_HOME = 'C:\DEPO\runtime\spark-4.1.2-bin-hadoop3'
  DEPO_JAVA_HOME = 'C:\Program Files\Java\jdk-21'
  DEPO_HADOOP_HOME = 'C:\DEPO\runtime\hadoop'
  DEPO_SPARK_OUTPUT_ROOT = 'C:\DEPO\data\spark-output'
  DEPO_SPARK_MASTER = 'local[2]'
  DEPO_SPARK_ENABLED = 'false'
  DEPO_SPARK_NEO4J_ENABLED = 'false'
  DEPO_SPARK_POSTGRES_ENABLED = 'false'
  DEPO_PIPELINE_SCHEDULER_ENABLED = 'false'
  DEPO_PIPELINE_EXECUTION_MODE = 'worker'
  DEPO_PIPELINE_LEASE_SECONDS = '300'
  DEPO_PIPELINE_POLL_SECONDS = '5'
}
$lines = Get-Content .\.env.local
foreach ($entry in $sparkSettings.GetEnumerator()) {
  $match = "^$([regex]::Escape($entry.Key))="
  if ($lines -match $match) {
    $lines = $lines | ForEach-Object { if ($_ -match $match) { "$($entry.Key)=$($entry.Value)" } else { $_ } }
  } else {
    $lines += "$($entry.Key)=$($entry.Value)"
  }
}
Set-Content .\.env.local $lines
```

Verify the file is valid and that the Windows process receives the expected
non-secret runtime paths. This command does not print passwords or API keys:

```powershell
. .\infra\windows\runtime-config.ps1
Import-DepoEnvironment -Root (Get-Location).Path -EnvFile .env.local
[pscustomobject]@{
  DEPO_SPARK_HOME = $env:DEPO_SPARK_HOME
  DEPO_JAVA_HOME = $env:DEPO_JAVA_HOME
  DEPO_HADOOP_HOME = $env:DEPO_HADOOP_HOME
  DEPO_SPARK_OUTPUT_ROOT = $env:DEPO_SPARK_OUTPUT_ROOT
  DEPO_SPARK_MASTER = $env:DEPO_SPARK_MASTER
  DEPO_PIPELINE_EXECUTION_MODE = $env:DEPO_PIPELINE_EXECUTION_MODE
} | Format-List
```

Set feature flags to `true` only after the Spark smoke test passes. Edit existing
keys instead of appending duplicates; duplicate keys fail validation.

#### Optional: allow Spark jobs to read PostgreSQL through JDBC

The backend services continue to use `psycopg` for migrations, transactions,
and control-plane records. Enable JDBC only when an approved Spark data job must
read PostgreSQL. Spark must not write the DEPO-owned `semantic.depo_*` tables.

Download the Java 8-or-newer PostgreSQL JDBC 4.2 driver from the official
[pgJDBC download page](https://jdbc.postgresql.org/download/). The release
validated by this guide is `postgresql-42.7.13.jar`. Run these commands from an
elevated PowerShell prompt:

```powershell
New-Item -ItemType Directory -Force 'C:\DEPO\drivers' | Out-Null
Invoke-WebRequest -Uri 'https://jdbc.postgresql.org/download/postgresql-42.7.13.jar' -OutFile 'C:\DEPO\drivers\postgresql-42.7.13.jar'
Get-Item 'C:\DEPO\drivers\postgresql-42.7.13.jar'
Get-FileHash 'C:\DEPO\drivers\postgresql-42.7.13.jar' -Algorithm SHA256
```

Record the SHA-256 value in the customer installation evidence and compare it
with the checksum approved by the customer's software-supply process. Then add
these two unique lines to the root `.env.local`:

```dotenv
DEPO_SPARK_POSTGRES_ENABLED=true
DEPO_SPARK_POSTGRES_DRIVER_JAR=C:\DEPO\drivers\postgresql-42.7.13.jar
```

The same root file must already contain the remote PostgreSQL URL, including
the application role. Keep special characters percent-encoded. For the
customer's non-TLS database configuration, the shape is:

```dotenv
DEPO_DATABASE_URL=postgresql://depo_app:<percent-encoded-password>@<database-vm-ip>:5432/depo?sslmode=disable
```

Run the dedicated read-only JDBC test before installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local -PostgresConnector
```

Success prints `DEPO Spark PostgreSQL JDBC smoke test passed.` The probe runs
only `SELECT 1`; it does not create or modify tables. To enable the connector
through the single installer, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-depo.ps1 -EnvFile .env.local -Profile Production -EnableSpark -EnablePostgresSparkConnector
```

### 2.4 Confirm the two files before installation

Run this check. It must show the root server file and the frontend browser file;
it must not show a `backend/.env.local` or a `spark.env.local`.

```powershell
Get-Item .\.env.local, .\frontend\.env.local | Select-Object FullName, Length, LastWriteTime
```

## 3. Run the single Windows installation command

After PostgreSQL, Neo4j, optional Spark, and both `.env.local` files are ready,
first run the non-mutating prerequisite diagnostic from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase Prerequisites
```

After it reports success, run **one** installation command. This is the
supported customer installation path; do not run individual migration, startup,
or validation scripts by hand.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-depo.ps1 -EnvFile .env.local -Profile Production
```

For a Spark deployment, use this command instead. Add the connector and
scheduler switches only when those customer capabilities are required:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-depo.ps1 -EnvFile .env.local -Profile Production -EnableSpark
# Optional: -EnableNeo4jSparkConnector -EnablePostgresSparkConnector -EnablePipelineScheduler
```

The installer performs these stages in this fixed order and stops at the first
failure:

1. Validates server and frontend configuration before dependency installation,
   then validates Python, Node.js, npm, and the frontend lockfile.
2. Creates `backend/.dt_venv`, installs backend dependencies, runs `npm ci`,
   and builds `frontend/dist`.
3. Validates root `.env.local` and the ten-service deployment configuration.
4. Tests PostgreSQL login through the configured `DEPO_DATABASE_URL`, then
   applies and verifies migrations.
5. Applies the idempotent Neo4j publication constraints, waits for their
   backing indexes, and verifies TLS, authentication and database access.
6. When enabled, validates Spark/JDK/Hadoop paths and runs the DataFrame smoke
   job before services are started.
7. Starts the ten APIs, data-product outbox worker, durable data-pipeline
   worker and agentic workflow worker; validates all endpoints; and seeds the
   approved baseline assets and data jobs.
8. Runs release preflight, including schema, Neo4j, Spark, and production
   configuration checks.

The command is safe to run again after correcting a failure: package installs,
migrations, validation, and baseline seeding use their existing idempotent
contracts. It does not create or overwrite `.env.local`, PostgreSQL accounts,
Neo4j accounts, Spark files, or customer secrets.

### 3.1 Service ports and health checks

The standard Windows service topology does not use port `8000`. Do not test
`http://127.0.0.1:8000/health` unless a customer has separately configured a
legacy aggregate API. Test the service ports below instead:

| Port | Service | Health URL |
| --- | --- | --- |
| 8010 | Schema Sets | `http://127.0.0.1:8010/readyz` |
| 8011 | Ontology | `http://127.0.0.1:8011/readyz` |
| 8012 | Agentic | `http://127.0.0.1:8012/readyz` |
| 8013 | Graph | `http://127.0.0.1:8013/readyz` |
| 8014 | Ingestion and ontology registry | `http://127.0.0.1:8014/readyz` |
| 8015 | OSLC | `http://127.0.0.1:8015/readyz` |
| 8016 | Data Catalog | `http://127.0.0.1:8016/readyz` |
| 8017 | Data Products | `http://127.0.0.1:8017/readyz` |
| 8018 | CEIM | `http://127.0.0.1:8018/readyz` |
| 8019 | Data Pipeline | `http://127.0.0.1:8019/readyz` |

Check every HTTP service from the application VM:

```powershell
8010..8019 | ForEach-Object {
  $url = "http://127.0.0.1:$($_)/readyz"
  $response = Invoke-WebRequest $url -UseBasicParsing
  "{0}: {1}" -f $url, $response.StatusCode
}
```

The expected status is `200` for every enabled service. The browser frontend
is separate and is served at `http://127.0.0.1:3000/` during a local smoke
test.

### 3.2 What the installer installs and configures

The repository-root `install-depo.ps1` is the only customer installation entry
point. Scripts below `infra/windows` and `infra/deployment` are internal stages;
do not run them individually for a customer installation.

| Component | Runtime module or output | Configuration source | Customer command |
| --- | --- | --- | --- |
| Frontend | `frontend/dist` | `frontend/.env.local` (`VITE_*`) | `install-depo.ps1` |
| Schema Sets/QIF | `backend.qif.app:app` / 8010 | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| Ontology | `backend.ontology_service.app:app` / 8011 | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| Agentic | `backend.agentic_service.app:app` / 8012 | root `.env.local` plus agentic settings | `install-depo.ps1`; later `manage-depo.ps1` |
| Graph | `backend.graph_service.app:app` / 8013 | root `.env.local`, Neo4j settings | `install-depo.ps1`; later `manage-depo.ps1` |
| Ingestion | `backend.ingestion_service.app:app` / 8014 | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| OSLC | `backend.oslc_service.app:app` / 8015 | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| Catalog | `backend.data_catalog_service.app:app` / 8016 | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| Data Products | `backend.data_product_service.app:app` / 8017 | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| CEIM | `backend.ceim_service.app:app` / 8018 | root `.env.local`, Neo4j settings | `install-depo.ps1`; later `manage-depo.ps1` |
| Data Pipeline | `backend.data_pipeline_service.app:app` / 8019 | root `.env.local`, Spark settings | `install-depo.ps1`; later `manage-depo.ps1` |
| Data-product worker | `backend.data_product_service.worker` | root `.env.local` | `install-depo.ps1`; later `manage-depo.ps1` |
| Data-pipeline worker | `backend.data_pipeline_service.worker` | root `.env.local`, PostgreSQL, artifact storage, optional Spark | `install-depo.ps1`; later `manage-depo.ps1` |

The authoritative module and port list is
[`infra/deployment/services.json`](../../infra/deployment/services.json). The
installer creates the backend virtual environment, installs the exact versions
and SHA-256 hashes in `backend/requirements-lock.txt`,
runs `npm ci` in `frontend`, and runs `npm run build`; it does not install
PostgreSQL, Neo4j, Java, Hadoop, or Spark binaries. Those runtimes must be
installed and configured before the installer command in Section 3.

## 4. Complete customer deployment

Complete these steps in order after Section 3 reports success. If a step fails,
stop, fix that step, and rerun only the relevant validation; do not skip ahead.

### 4.1 Confirm the installer result

From the repository root, run the complete runtime diagnostic:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 `
  -Phase All `
  -EnvFile .env.local `
  -Profile Production
```

It checks software prerequisites, configuration, PostgreSQL relations,
constraints and indexes, Neo4j constraints and connectivity, optional Spark,
and all running service endpoints. In `Production` profile it does not create
database or graph schema. The optional Spark smoke test writes only disposable
test output below the configured Spark output root. Then confirm the browser build and the two
configuration files:

```powershell
Test-Path .\frontend\dist
Get-Item .\.env.local, .\frontend\.env.local | Select-Object FullName, Length, LastWriteTime
```

Both paths must exist. Never copy either `.env.local` file into `frontend\dist`.

### 4.2 Confirm the application processes

The supported installer starts the DEPO APIs and both workers. Confirm the
recorded processes rather than listing every unrelated Python process on the
VM:

```powershell
Get-ChildItem .\logs\windows-services\*.pid | ForEach-Object {
  $processId = [int](Get-Content -LiteralPath $_.FullName)
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  [pscustomobject]@{ Service = $_.BaseName; ProcessId = $processId; Running = [bool]$process; Path = $process.Path }
} | Format-Table -AutoSize
```

The `diagnose-depo.ps1 -Phase All` command above checks the health URL of every
enabled service and fails if any response is not HTTP 200. The authoritative
inventory is read by the root commands internally. Do not expose internal
service ports directly to the browser or the public network.

### 4.3 Verify the PostgreSQL schema

The DBA provisioned the application schema in Section 1.1, and the installer
applied the versioned DEPO tables. Connect as `depo_app` for this read-only
verification.

For a remote deployment, use pgAdmin Query Tool on the PostgreSQL VM or admin
workstation, connected to database `depo`. For a local deployment, use pgAdmin
on the application VM. Run:

```sql
SELECT current_database(), current_user;
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'semantic';
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'semantic'
ORDER BY table_name;
```

The `semantic` schema must be present and the table query must return the DEPO
tables. On the application VM, confirm the runtime uses the remote mode:

```powershell
. .\infra\windows\runtime-config.ps1
Import-DepoEnvironment -Root (Get-Location).Path -EnvFile .env.local
if ($env:DEPO_POSTGRES_MODE -ne 'external') { throw 'Expected external PostgreSQL mode' }
$env:DEPO_POSTGRES_MODE
```

Do not run `Start-Service` for PostgreSQL on the application VM.

### 4.4 Serve the frontend

The installer creates static files in `frontend\dist`. Start the local frontend
with the supplied lifecycle script. It uses the already-installed backend
Python runtime, records a PID, checks for a conflicting port, verifies the
rendered application shell, and does not download another npm package:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\start-depo-frontend.ps1
```

The defaults are `-BindHost 127.0.0.1 -Port 3000`. An equivalent explicit
command, useful when recording installation evidence, is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\infra\windows\start-depo-frontend.ps1 `
  -BindHost 127.0.0.1 `
  -Port 3000
```

Open `http://127.0.0.1:3000` in a browser and confirm the DEPO landing page
loads. In a direct-service installation without a gateway, complete the
authentication step before opening a data page:

1. Open the root server configuration without copying its contents to the
   frontend configuration:

   ```powershell
   notepad .\.env.local
   ```

2. Copy the value after `GRAPH_READ_TOKEN=`.
3. In the DEPO header, select **API access**, paste that value into **Graph read
   API key**, and select **Apply and retry**.
4. Open Graph, Data Products, Data Pipeline, or Code Audit and confirm their
   requests return HTTP 200. The key exists only in the current browser tab's
   memory; a full reload clears it, so repeat this step after reloading.

If `ALLOWED_ORIGINS` was edited after the services started, restart every
backend service before opening the UI. Environment-file changes cannot alter
an already-running Python process:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Stop -EnvFile .env.local
powershell -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Start -EnvFile .env.local -Profile Bootstrap -SkipPostgres
```

Verify that a service returns the configured CORS header:

```powershell
$response = Invoke-WebRequest -UseBasicParsing `
  -Uri http://127.0.0.1:8011/api/v1/ontologies/health `
  -Headers @{ Origin = 'http://127.0.0.1:3000' }
$response.Headers['Access-Control-Allow-Origin']
```

The final command must print `http://127.0.0.1:3000`.

If the browser console still names an old hashed file such as
`index-DFbOVHXy.js`, the VM is serving a stale frontend build. Confirm the
checked-out release and the bundle referenced by the deployed HTML:

```powershell
git branch --show-current
git log -1 --oneline
Select-String -Path .\frontend\dist\index.html -Pattern 'assets/index-.*\.js'
```

The branch must be `codex/semantic-bridge-release`, the commit must be the
release commit being installed, and the browser console filename must match the
filename printed from `dist\index.html`. The frontend start script now refuses
to start when a source file is newer than the production build.

Never put `GRAPH_READ_TOKEN` in `frontend\.env.local` or a `VITE_*` setting.
The API access control is for a controlled direct-service installation. A
customer gateway must authenticate browser requests and keep backend service
ports private.

Stop the local frontend with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\stop-depo-frontend.ps1
```

For a customer release, copy or mount `frontend\dist` into the approved HTTPS
web server document root and configure the single-page-application fallback to
`index.html`. The local script is intended for installation verification and a
controlled demonstration; use the customer web server for unattended service,
TLS, restart recovery, and external access.

### 4.5 Configure the customer gateway

Route browser API requests through the customer HTTPS gateway to the internal
DEPO services listed in `infra\deployment\services.json`. Keep service ports
private. Configure the gateway to forward the required API-key headers and to
preserve WebSocket or streaming support when the selected UI feature needs it.

### 4.6 Switch from direct service access to a gateway

A direct installation can be migrated later. The database and backend service
configuration does not change; only the browser routing and CORS configuration
change. Complete these steps in order:

1. Configure the gateway to route these paths to the internal service ports:

   ```text
   /qif            -> 8010
   /ontology       -> 8011
   /agentic        -> 8012
   /graph          -> 8013
   /ingestion      -> 8014
   /oslc           -> 8015
   /catalog        -> 8016
   /data-products  -> 8017
   /ceim           -> 8018
   /data-pipeline  -> 8019
   ```

2. Update the root server `.env.local` CORS value to the browser origin:

   ```text
   ALLOWED_ORIGINS=https://app.customer.example
   ```

3. Update `frontend/.env.local` before building:

   ```text
   VITE_API_GATEWAY_URL=https://api.customer.example
   ```

4. Rebuild the browser bundle from the repository root:

   ```powershell
   Set-Location .\frontend
   npm ci
   npm run build
   Test-Path .\dist\index.html
   ```

5. Deploy the new `frontend\dist` directory and restart the backend services so
   the new CORS setting is loaded. The browser bundle embeds Vite environment
   values at build time; changing `.env.local` without rebuilding has no effect.

6. Verify the gateway before browser acceptance:

   ```powershell
   Invoke-WebRequest https://api.customer.example/ontology/readyz -UseBasicParsing
   Invoke-WebRequest https://api.customer.example/ingestion/readyz -UseBasicParsing
   Invoke-WebRequest https://api.customer.example/data-pipeline/readyz -UseBasicParsing
   ```

   Each enabled route must return HTTP 200. Keep ports `8010–8019` private
   after the gateway is working.

### 4.7 Perform release acceptance

Run these checks in the browser in order:

1. Sign in using the customer API-key flow.
2. Open Ontology Junction and load the registered ontology list.
3. Open Semantic Bridge, select an imported instance and ontology, create a
   preview, review candidates, and confirm that publication requires approval.
4. Open the data pipeline page and verify the configured job status.
5. If Spark is enabled, run the documented Spark smoke test and confirm its
   output artifact.
6. If Neo4j is enabled, open the graph view and verify a read-only query.

Record the installer output, dependency lock versions, PostgreSQL schema result,
Neo4j evidence, Spark smoke result when enabled, browser acceptance, process
supervision, reboot recovery, monitoring, backup/restore drill, and rollback
evidence in the customer release record.

The included launcher uses hidden user-session processes and PID files. It is
suitable for installation verification and controlled demonstrations, but it
does not register Windows services and does not provide reboot recovery. Before
production acceptance, the customer platform team must place the ten API
commands and two worker commands from `infra/deployment/services.json` under
its approved Windows service/process supervisor, using the same root
`.env.local`, repository working directory, service account and restart policy.
Treat missing supervision and reboot-recovery evidence as a release blocker.

After recording supervision/reboot recovery, backup/restore, browser acceptance
and rollback results as files, produce the final tamper-evident handoff record:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\certify-depo-release.ps1 `
  -EnvFile .env.local `
  -SupervisorEvidencePath C:\DEPO\evidence\supervisor-reboot.txt `
  -BackupRestoreEvidencePath C:\DEPO\evidence\backup-restore.txt `
  -BrowserAcceptanceEvidencePath C:\DEPO\evidence\browser-acceptance.txt `
  -RollbackEvidencePath C:\DEPO\evidence\rollback.txt
```

The command refuses missing or empty evidence, reruns the complete Production
diagnostic, and writes a JSON record containing the Git revision and SHA-256
hashes. Store the generated record with the customer release package.

For a controlled installation or demonstration, stop and restart the complete
set in this order from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Stop -EnvFile .env.local
powershell -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Start -EnvFile .env.local -Profile Bootstrap -SkipPostgres
```

`-SkipPostgres` means “do not operate a local PostgreSQL process”; database
connectivity and schema validation still run against `DEPO_DATABASE_URL`.

The supported commands read the authoritative service inventory internally.
Only infrastructure utilities explicitly named in this guide should be run
directly. Other scripts under `infra/windows/` and `infra/deployment/` are
implementation stages, not separate customer installation instructions.

### Updating an existing installation

Use **Setup-DEPO.cmd → Install / update / repair** for the supported guided update. Take reviewed PostgreSQL, Neo4j and artifact backups first. Keep root/frontend environment files and customer data when placing the matching release. Setup validates before shutdown and reuses verified dependency installations.

Advanced operators can run the repository-root updater from a PowerShell session started with process-scoped execution-policy bypass:

```powershell
Set-Location E:\App\PMem
.\update-depo.ps1 -EnvFile .\.env.local -InstallDependencies
```

Do not manually stop services before running preflight. On failure, read the retained audit log and rerun the same supported command after correcting the error. Never delete environment files, checkpoints or databases as a general repair step. A schema migration failure requires review of migration history and the backup/rollback procedure before trying an older release.

#### Connect the browser after importing credentials

For `AUTH_MODE=token` and `DEPO_CREDENTIAL_STORE=postgres`, the PowerShell credential import registers server-side digests. It cannot inject plaintext keys into a browser. Use the new central session connection instead of entering each service key:

1. Run `infra/windows/apply-depo-service-credentials.ps1 -EnvFile .env.local` and confirm `status: ok`. Start backend and frontend services using the steps below.
2. Open the app, navigate to **Admin → Service credentials → Connect registered service credentials**.
3. Copy only `ADMIN_API_KEY` from the selected root `.env.local` into **Administrator key for connection**. If APIM is enabled, enter the APIM subscription key in its separate field first.
4. Leave workflow scopes unchecked for read-only browsing. To upload/register ontologies or execute approved workflows, explicitly check **Enable registered upload, execution and approval scopes for this session**.
5. Click **Connect registered services**. The app checks read access on every configured service before applying the session. Rows report connected scopes; the administrator input is cleared. You do not need to copy the individual keys or register them again.
6. Use the application. For a manual delegated central session, reconnect when its fifteen-minute session expires. Local broker mode manages session renewal; do not paste server keys into the browser. The delegated central session survives same-tab refresh when session storage is available. **Clear credentials** disconnects the session when reachable and clears browser memory; a session that cannot be disconnected still expires server-side. Rotation/revocation invalidates the affected scope; rotating/revoking the issuing Admin key invalidates all its sessions.

Deploy matching backend files to all services and rebuild the frontend before using this feature. No new database migration is needed beyond the existing registry and credential tables (migrations 001 and 008). Sessions store token digests and credential fingerprints in `depo_registry`; plaintext service keys are never returned. Sessions are held only in browser memory and cannot rotate or revoke credentials. Credential administration still requires the separate Admin key; workflow review/approval requirements remain in force. For APIM, import the updated OpenAPI and permit the ontology service's `POST /auth/browser-session` and `DELETE /auth/browser-session`, forwarding `X-API-Key` on connection and `Authorization` on disconnection.

Knowledge Companion currently provides evidence-grounded ontology resource search. It is not an instance EBOM/MBOM comparison or change-impact engine. Its `/api/v1/chat/capabilities` reports this limit. The selected ontology filters server-side search; browser-provided graph labels are not trusted evidence. Applying a different graph read key in Admin resets the credential-owned chat session. In token mode, Companion forwards the verified caller read key to Graph, so read-key rotation does not require an environment copy for this retrieval path. Other outbound worker/tool credentials still follow their documented server configuration.

On first deployment, the database administrator must first run the database/role/schema provisioning steps in this guide, including `infra/postgres/create-depo-database.sql`. That file is for **first installation only**: do not rerun it against an existing database. The application installer does not create the PostgreSQL database or schema.

After completing root `.env.local` and the frontend configuration steps, run on the application VM:

```powershell
Set-Location E:\App\PMem
.\install-depo.ps1 -EnvFile .\.env.local -Profile Production
.\infra\windows\start-depo-frontend.ps1 -EnvFile .\.env.local
```

For an existing installation, arrange and verify the approved database backup first. Stop the frontend and backend before replacing release files or installing dependencies; running processes can lock `node_modules` and retain old code or configuration. Keep root `.env.local`, frontend configuration, durable artifacts and the existing PostgreSQL database. Run:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
.\manage-depo.ps1 -Action Stop -EnvFile .\.env.local
```

Now deploy the new release files, preserving those customer settings and data. Then run:

```powershell
Set-Location E:\App\PMem
.\install-depo.ps1 -EnvFile .\.env.local -Profile Production
.\infra\postgres\test-postgres-schema.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .\.env.local
```

The Windows installer applies pending migrations while backend processes are stopped.
Normal Windows startup verifies the installed schema in a read-only transaction;
pending migrations require the installation or upgrade command. Applied versions
and checksums are recorded in the configured schema's `depo_schema_migrations`
table. Already applied files are skipped and changed historical files are rejected.
New releases must add numbered migrations rather than edit applied files. A failed
migration or final verification rolls back the update transaction and prevents the
installer from launching services.

With `DEPO_CREDENTIAL_STORE=postgres`, migration also inserts missing credential profiles from the selected environment. Existing rotated or revoked profiles are preserved. Reinstallation does not reset database-managed keys or make expired/revoked keys valid. Schema updates do not automatically create analytics tables from imported XSD plans.

### 4.8 Schema-only redeployment

When a release changes only PostgreSQL DDL, stop the application services,
take the approved database backup, apply the schema update, validate it, and
then start the services. Run these commands from the repository root:

For an already deployed customer environment, preserve root `.env.local`,
frontend configuration and durable artifacts. After stopping the application
and completing the DBA backup, copy the matching release files, including
`backend` and the complete `infra/postgres/migrations` folder. Do not run
`initialize-depo-postgres.ps1`, recreate the database, or replace released SQL
files with edited copies. If dependencies changed, follow the full upgrade
sequence in section 4.7 instead.

```powershell
.\manage-depo.ps1 -Action Stop -EnvFile .env.local
.\infra\postgres\test-postgres-connectivity.ps1 -EnvFile .env.local
.\infra\postgres\update-postgres-schema.ps1 -EnvFile .env.local
.\infra\postgres\test-postgres-schema.ps1 -EnvFile .env.local
.\manage-depo.ps1 -Action Start -EnvFile .env.local -Profile Production -SkipPostgres
```

`update-postgres-schema.ps1` contacts only the PostgreSQL URL configured in the
root `.env.local`. It does not install packages, start PostgreSQL, build or
start the application, contact Neo4j, or run Spark. It applies each new file in
`infra\postgres\migrations` once, in numeric order, under an advisory lock and
then verifies the full released schema contract. `test-postgres-schema.ps1`
uses the same contract in read-only mode and is safe for routine diagnostics.

Proceed to startup only after each command succeeds. The migration and final
verification run in one transaction; failure rolls back their changes. Current
success output lists migration versions 1 through 11 and checks 11 relations,
53 columns, 22 constraints and 9 indexes. Repeating the update skips migrations
already recorded with matching checksums. Startup also runs this migration
step automatically before launching services. Existing credential profiles
are preserved; routine schema upgrades do not require `-Synchronize` or token
rotation. Missing history versions, newer database versions or changed SQL
checksums require DBA investigation, not deletion of history rows. This
updates the application control-plane schema; it does not regenerate customer
analytics product schemas. There is no automatic downgrade migration.
The automated `infra/windows/update-depo-windows.ps1` path checks PostgreSQL
table ownership, view read access and migration history, and inspects existing
Neo4j publication constraints/indexes before stopping application processes.
These preflight checks are read-only and allow missing objects that pending
migrations/provisioning will create. They do not prove that every later DDL,
dependency installation or startup operation will succeed; maintain a backup
and an agreed recovery plan. A preflight failure leaves running services alone.

### Optional Windows dependency isolation by microservice

The default `DEPO_SERVICE_RUNTIME_MODE=shared` preserves the existing common
`backend/.dt_venv` installation. To install separate CPython 3.12 Windows x64
environments, set `DEPO_SERVICE_RUNTIME_MODE=isolated` in the selected root
environment file, stop the existing services, then run the full installer with
dependency installation enabled. Do not use `-SkipDependencyInstall` for the
first switch. The installer retains `backend/.dt_venv` for platform tools and
creates `backend/.dt_venv-<service-id>` for each API and worker. Startup verifies
every selected runtime before launching processes. Shutdown recognizes both
shared and isolated runtimes, including after a mode change.

| API / worker | Locked packages | Fewer than shared 199-package runtime |
| --- | ---: | ---: |
| Schema sets | 176 | 23 |
| Ontology | 176 | 23 |
| Agentic | 75 | 124 |
| Graph | 177 | 22 |
| Ingestion | 86 | 113 |
| OSLC | 74 | 125 |
| Catalog | 74 | 125 |
| Data products | 74 | 125 |
| CEIM | 74 | 125 |
| Data pipeline | 74 | 125 |
| Product outbox worker | 17 | 182 |
| Pipeline worker | 69 | 130 |
| Agentic workflow worker | 70 | 129 |

These are package distributions in each lock, including transitive dependencies;
they exclude pip and optional OCR. Three semantic services retain Semantica and
its mandatory ML/visualization dependencies. LangChain integrations already
used by feature paths remain present where required. LangChain does not replace
RDF/XSD validation, XML parsers, database drivers, approval controls or durable
publication receipts. Versions and artifact hashes match the shared release.

Platform tools have a 26-package profile. `-EnableOcr` installs the complete
28-package OCR closure into the isolated ingestion environment (some packages
overlap its base profile). It does not add OCR to every service. Existing
environments are not pruned automatically: switching an already populated
environment to a smaller lock does not uninstall old distributions. Use a new
reviewed environment for measured reductions. Multiple environments on one VM
duplicate shared packages and can consume more total disk than one shared
environment; per-service/container deployments benefit most from isolation.

To install or validate an individual stopped service without migrating the
database or starting processes:

```powershell
.\infra\windows\install-depo-service.ps1 -ServiceId catalog -EnvFile .env.local -CheckOnly
.\infra\windows\install-depo-service.ps1 -ServiceId catalog -EnvFile .env.local -Python .\backend\.dt_venv\Scripts\python.exe
```

`-ServiceId all` covers all ten APIs and three workers. The installer rejects
unknown IDs and running target runtimes, uses `--require-hashes`, runs `pip check`,
and verifies the selected service import/OpenAPI contract or worker import.
This smoke check does not prove live database, gateway or model connectivity.

Release builders can inventory imports with
`python infra/deployment/service-dependencies.py` and verify the reviewed locks
with `python infra/deployment/build-service-locks.py --check` (build dependency:
`packaging`). `backend/dependency-profiles/windows-metadata.json` records the
official PyPI requirements and verified existing artifact hashes used to derive
the locks. Refresh metadata and shared pins together when upgrading packages.
Do not reuse Windows wheel locks on Linux; the existing native Linux release
builder remains required for Linux dependency locks.

Windows prerequisites enforce 64-bit CPython 3.12. Spark and connector runtime
settings selected by installer switches are checked before dependency or database
installation stages. Bootstrap loopback-only disabled-auth deployments retain
their explicit configuration checks during final release validation.

Linux installation compiles browser routing from the selected root environment
using `DEPO_ROUTING_MODE`, `DEPO_API_GATEWAY_URL` and the per-service gateway paths.
Only public routing values are passed to Vite. Quoted environment values are
literal; unquoted inline comments must be preceded by whitespace. Malformed
environment diagnostics do not print the offending value.

# Switching local services and API gateway routing

## Azure API Management: deploy and verify every service

1. Configure root `.env.local` (replace the customer hostname):

```dotenv
DEPO_ROUTING_MODE=gateway
DEPO_API_GATEWAY_URL=https://customer-apim.azure-api.net/depo
AUTH_MODE=token
DEPO_SERVICE_HOST=10.0.2.16
ALLOWED_ORIGINS=http://10.0.2.16:3000
OSLC_BASE_URL=https://customer-apim.azure-api.net/depo/oslc
DEPO_APIM_SUBSCRIPTION_KEY=
```

Retain all server read/approval keys. If APIM requires a subscription key, set `DEPO_APIM_SUBSCRIPTION_KEY` to the actual server subscription credential. For browser calls, enter a browser-authorized subscription key in **API access → APIM subscription key (optional)**; it remains in memory and is cleared with the read key. The subscription key is separate from `GRAPH_READ_TOKEN`, not its replacement. Never embed either key into a bundle or URL. In Entra mode use `AUTH_MODE=entra`, HTTPS, trusted gateway addresses and a gateway-validated JWT; the gateway diagnostic requires a valid JWT supplied as a SecureString.

2. In Azure Portal, open API Management → APIs. Create/import the ten service APIs using the port/suffix table below. With the example root `/depo`, API URL suffixes are `depo/qif`, `depo/ontology`, `depo/agentic`, `depo/graph`, `depo/ingestion`, `depo/oslc`, `depo/catalog`, `depo/data-products`, `depo/ceim`, `depo/data-pipeline`. Each Web service URL is its backend root, for example graph `http://10.0.2.16:8013` (not `/api/v1`). Import that service's `/openapi.json`. APIM must also expose `/healthz`, `/readyz` and `/openapi.json` explicitly: the health routes are omitted from the imported OpenAPI. Preserve `/api/v1/...` when forwarding functional operations. If actual API suffixes differ, set the corresponding root override, such as `DEPO_GATEWAY_GRAPH_PATH=engineering/graph`; use relative segments without a leading slash or `/api/v1`.

3. Ensure APIM can reach `10.0.2.16:8010` through `8019` through customer routing/VNet/VPN or a self-hosted gateway. A cloud gateway cannot reach a private VM merely because a URL is configured. Keep authentication enabled, preserve Authorization, and preserve `X-DEPO-Service-Token` for internal catalog calls. In token mode do not apply JWT validation to DEPO's opaque API keys. Entra mode requires a separate JWT validation/identity forwarding policy; these policies are customer-controlled.

4. Configure API-level CORS from the same exact origins in root `ALLOWED_ORIGINS`. Allow GET, POST, PUT, PATCH, DELETE and OPTIONS, and headers `Authorization`, `Content-Type`, `X-API-Key`, `X-Request-ID`, `X-Session-ID`, and `Ocp-Apim-Subscription-Key` if used. Expose `X-Request-ID`, `X-Session-ID`, `X-Session-Expires-At`, `X-DEPO-Run-ID`, `X-DEPO-Run-Kind` and `OData-Version`. Browser preflight does not send the bearer/subscription credentials, so ensure OPTIONS is handled before authentication. Do not add an explicit OPTIONS operation that bypasses the intended APIM CORS policy. Microsoft references: https://learn.microsoft.com/en-us/azure/api-management/cors-policy and https://learn.microsoft.com/en-us/azure/api-management/set-backend-service-policy .

5. Deploy all changed source files together, including the runtime helper, frontend configuration and launcher. Rebuild once, then restart services and frontend:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
.\infra\windows\stop-depo-services.ps1
Set-Location .\frontend
npm.cmd run build
Set-Location ..
.\infra\windows\start-depo-services.ps1 -EnvFile .env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .env.local -BindHost 10.0.2.16
.\infra\deployment\test-depo-gateway.ps1 -EnvFile .env.local
```

The gateway test checks all ten public routes for health, readiness, OpenAPI and unauthenticated browser preflight, then a protected graph read. It performs no writes. Failures identify the service route without displaying credentials. Run it on the VM and, for remote access, from an authorized client network. For Entra testing:

```powershell
$depoGatewayJwt = Read-Host 'Paste a valid gateway JWT' -AsSecureString
try {
    .\infra\deployment\test-depo-gateway.ps1 -EnvFile .env.local -AccessToken $depoGatewayJwt
} finally { Remove-Variable depoGatewayJwt -ErrorAction SilentlyContinue }
```

Open the frontend, refresh with Ctrl+F5, and check `window.DEPO_RUNTIME_CONFIG` in Developer Tools. All ten service URLs must reference your configured gateway, not `127.0.0.1`. An old compiled bundle is now rejected by the launcher even if its HTML has the runtime script tag. The installer writes runtime routes into the built output so customer web servers receive the same routes. Rebuilding directly with npm replaces the public configuration stub; rerun the frontend launcher or `Write-DepoBrowserRouting` before publishing the rebuilt output.

## Using services and tokens: application VM example

This example uses application VM `10.0.2.16`, frontend port `3000`, and an independently configured PostgreSQL VM. Replace the application IP if yours differs. Complete dependency installation and PostgreSQL/Neo4j setup first. Root `E:\App\PMem\.env.local` holds server credentials; browser configuration must never contain keys.

### 1. Configure service access in root .env.local

Edit existing entries rather than adding duplicate keys:

```dotenv
DEPO_ROUTING_MODE=local
AUTH_MODE=token
DEPO_SERVICE_HOST=10.0.2.16
DEPO_LOCAL_SERVICE_HOST=10.0.2.16
ALLOWED_ORIGINS=http://10.0.2.16:3000,http://127.0.0.1:3000,http://localhost:3000
OSLC_BASE_URL=http://10.0.2.16:8015
```

Keep the generated `GRAPH_READ_TOKEN`, `ADMIN_API_KEY` and distinct approval/service keys already in this file. Do not replace them with these variable names or example placeholders. `ALLOWED_ORIGINS` is a list of frontend browser addresses, not backend service addresses; it does not authenticate a user or start a listener.

### 2. Start backend services, then frontend

Run on the application VM from the repository root. If services already run, stop them before applying changed settings:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
.\infra\windows\stop-depo-services.ps1
.\infra\windows\start-depo-services.ps1 -EnvFile .env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .env.local -BindHost 10.0.2.16 -Port 3000
```

The frontend must already be built using the installation instructions. Open `http://10.0.2.16:3000` after both launchers report readiness. Remote browsers require customer firewall rules permitting the configured frontend and direct API ports. With a gateway deployment, expose the gateway instead of direct service ports.

| Service | Direct port | Gateway service suffix |
| --- | --- | --- |
| Schema sets / QIF | 8010 | /qif |
| Ontology | 8011 | /ontology |
| Agentic | 8012 | /agentic |
| Graph | 8013 | /graph |
| Ingestion | 8014 | /ingestion |
| OSLC | 8015 | /oslc |
| Catalog | 8016 | /catalog |
| Data products | 8017 | /data-products |
| CEIM | 8018 | /ceim |
| Data pipeline | 8019 | /data-pipeline |

### 3. Enable authenticated reads in the UI

On the application VM, open root `.env.local` in your approved editor and locate `GRAPH_READ_TOKEN`. Copy only its value, without `GRAPH_READ_TOKEN=` or surrounding quotes. For limited individual-key access, choose **API access** to navigate to Admin → Service credentials, enter the value in the GRAPH_READ_TOKEN row and select **Test and apply**. For central PostgreSQL credentials, prefer the single Admin connection described in Step I. This enables protected read requests; it does not authorize publication or job execution. A full browser reload clears the key, so enter it again after reloading. **Clear** removes active browser credentials and resets credential-bearing controls. Do not distribute the root environment file to users; an administrator should provide only the key authorized for their role.

### 4. Use separate credentials for protected actions

| Action | Root environment key | Where to use it |
| --- | --- | --- |
| Protected graph/evidence reads | GRAPH_READ_TOKEN | Header API access dialog |
| Administrative endpoints | ADMIN_API_KEY | Admin page: Admin API key, then Refresh |
| Agent tools and Semantic Bridge approval | AGENTIC_APPROVAL_TOKEN | Matching approval controls with approver identity |
| Ontology registration/transitions/merge | ONTOLOGY_APPROVAL_TOKEN | Matching ontology approval controls |
| Run approved data jobs | DATA_JOB_EXECUTION_TOKEN | Job execution approval controls |
| Approve data jobs | DATA_JOB_APPROVAL_TOKEN | Job approval controls |
| Publish data products | DATA_PRODUCT_APPROVAL_TOKEN | Product publication approval controls |

The endpoint defines the required key; keys are not interchangeable. Other specialized actions use their corresponding key, such as `CEIM_PUBLISH_APPROVAL_TOKEN` or `VOCABULARY_APPROVAL_TOKEN`. Protected JSON actions generally require `approved_by` and `approval_token`; header-authorized writes use a Bearer token. Backend-to-backend credentials such as `CATALOG_SERVICE_TOKEN`, `GRAPH_PUBLICATION_TOKEN` and `INGESTION_WRITE_TOKEN` remain on the server and are selected by the calling service. Never put approval/admin keys into the read-key dialog or compile any key into Vite configuration.

### 5. Test a service without displaying the token

First check liveness (no token required):

```powershell
Set-Location E:\App\PMem
Invoke-RestMethod -Uri 'http://10.0.2.16:8013/healthz'
```

Then load the same root configuration parser used by the launcher and test a protected read:

```powershell
. .\infra\windows\runtime-config.ps1
$depoSettings = Read-DepoEnvironment -Root 'E:\App\PMem' -EnvFile '.env.local'
$depoReadHeaders = @{ Authorization = 'Bearer ' + $depoSettings['GRAPH_READ_TOKEN'] }
try {
    Invoke-RestMethod -Uri 'http://10.0.2.16:8013/api/v1/graph/overview?limit=10' -Headers $depoReadHeaders
} finally {
    $depoReadHeaders.Clear()
    $depoSettings.Clear()
    Remove-Variable depoReadHeaders, depoSettings -ErrorAction SilentlyContinue
}
```

Do not print the settings or header variables. For gateway mode, substitute the configured gateway root followed by `/graph/api/v1/graph/overview?limit=10`; the gateway must preserve the authorization header.

### 6. Interpret failures before changing credentials

| Result | Next step |
| --- | --- |
| Cannot connect | Check startup logs and listener/interface; credentials cannot fix a stopped service. |
| Browser CORS failure | Check the exact browser origin against root ALLOWED_ORIGINS, then restart backend services. |
| 403 invalid read/approval key | Use the key required by that endpoint and re-enter it after rotation/reload. |
| 401 key expired | Rotate the key and restart services; enter the replacement in the UI. |
| 503 actor/expiry configuration | Correct the named server configuration; do not disable authentication. |
| Health succeeds, protected query fails | Authentication and downstream readiness still need checking; health alone is not a functional test. |

Finally run `.\diagnose-depo.ps1` after starting services. Never paste `.env.local`, authorization headers or keys into diagnostic tickets. HTTP is supported but does not encrypt credentials; use HTTPS for remote confidential access.

## Central origins and API key lifecycle

Root `.env.local` is the sole CORS allowlist: set `ALLOWED_ORIGINS` to comma-separated exact browser origins. Services do not add localhost, LAN IPs, HTTPS variants or other ports automatically. Missing origins permit no cross-origin requests. Restart backend services after editing it.

With central sessions, original service keys remain server-side. Connect once in Admin as described in Step I. For individual-key access, enter the read key in the Admin credential table. Clear removes the read key, admin key, chat session identifier and remounts page/chat controls to discard approval inputs. Browser reload clears in-memory credentials.

Optional root settings:

```dotenv
DEPO_TOKEN_EXPIRES_AT=2026-12-31T23:59:59Z
GRAPH_READ_TOKEN_ACTOR=customer-reader
AGENTIC_APPROVAL_TOKEN_ACTOR=customer-approver
DEPO_REQUIRE_TOKEN_ACTOR=false
```

Replace the deadline with your actual UTC expiry. A `<KEY>_EXPIRES_AT` setting overrides the shared deadline. Expired keys return 401; malformed deadlines return 503. Configure `<KEY>_ACTOR` for each read/approval key before enabling `DEPO_REQUIRE_TOKEN_ACTOR=true`. These are key identities; distinct human identities require distinct credentials or gateway authentication.

Rotate one existing key without displaying its value:

```powershell
Set-Location E:\App\PMem
.\infra\windows\rotate-depo-api-key.ps1 -EnvFile .env.local -Key GRAPH_READ_TOKEN -Actor customer-reader -ValidDays 90
```

The command updates the key, its expiry and actor in the protected environment file. Restart all services/workers sharing the file, then clear and re-enter browser credentials. Old process environments continue using the previous key until restarted. Rotation is explicit; no scheduler is installed.

HTTP remains supported. It cannot encrypt bearer keys in transit; use HTTPS for remote access when confidentiality is required. A gateway must preserve Authorization and, in Entra mode, validate JWTs and supply verified identity headers from configured trusted gateway addresses. The routing switch does not provision APIM policies.

Set these entries in the repository-root `.env.local` to bypass Azure API Management:

```dotenv
DEPO_ROUTING_MODE=local
DEPO_LOCAL_SERVICE_HOST=127.0.0.1
AUTH_MODE=token
ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
OSLC_BASE_URL=http://127.0.0.1:8015
```

Use the application VM's reachable IP or hostname instead of `127.0.0.1` when browsers run on other computers. Set `DEPO_SERVICE_HOST` to a listening interface reachable by those browsers and include their exact frontend origin in `ALLOWED_ORIGINS`.

For gateway routing, replace the routing entries with:

```dotenv
DEPO_ROUTING_MODE=gateway
DEPO_API_GATEWAY_URL=https://customer.example/depo
```

Replace the example with the actual gateway API root. It must route `/qif`, `/ontology`, `/agentic`, `/graph`, `/ingestion`, `/oslc`, `/catalog`, `/data-products`, `/ceim` and `/data-pipeline`, preserving the subsequent `/api/v1` paths. HTTP gateway URLs are supported. Set `OSLC_BASE_URL` separately to the public OSLC service URL. API keys, PostgreSQL, Neo4j and the LLM provider retain their independent settings.

An explicit routing mode overrides all ten backend peer URLs and browser service URLs. Omitting the mode preserves the existing explicit configuration. Local routing requires API-key mode, not Entra header forwarding. Keep credentials out of frontend environment variables.

Run from PowerShell after deploying this release:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
.\infra\windows\stop-depo-services.ps1
# One-time rebuild if the deployed frontend predates runtime routing:
Set-Location .\frontend
npm.cmd run build
Set-Location ..
.\infra\windows\start-depo-services.ps1 -EnvFile .env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .env.local
```

Subsequent routing changes only require restarting the launchers and refreshing the browser. The frontend launcher writes a public `frontend/dist/depo-runtime-config.js` containing only routing URLs. Retain the normal installation/diagnostic prerequisites; this switch does not install dependencies or alter database authentication.

## Check and use ontology registration

Registration belongs to the ontology service on port 8011. It creates a **draft catalog artifact**; it does not approve the ontology or publish nodes to Neo4j. The ingestion service's historical registry is a compatibility view, not the native registration endpoint.

Direct endpoints: `GET /api/v1/ontologies` lists records, `POST /api/v1/ontologies/register` uploads a draft, and `GET /api/v1/ontologies/{ontology_id}` reads its metadata. Through APIM prepend the configured ontology suffix, for example `/depo/ontology/api/v1/ontologies/register`.

Check service liveness on the application VM:

```powershell
Set-Location E:\App\PMem
Invoke-RestMethod 'http://10.0.2.16:8011/healthz'
Invoke-RestMethod 'http://10.0.2.16:8011/api/v1/ontologies'
```

Registration requires `ONTOLOGY_APPROVAL_TOKEN` in `Authorization: Bearer ...`, not GRAPH_READ_TOKEN. Multipart fields: `artifact` (the file), `ontology_name`, `prefix`; optional fields: `description`, `source`. Prefixes start with a letter and contain letters, digits, underscores or hyphens. Files may be `.ttl`, `.rdf`, `.xml`, `.owl`, `.jsonld` or `.json` containing RDF/OWL or JSON-LD. Generic business XML/XSD must first be converted through ingestion. XML DTD/entity declarations and remote/imported JSON-LD contexts are rejected. Use inline JSON-LD contexts. The filename `metadata.json` is reserved.

`ONTOLOGY_MAX_UPLOAD_BYTES` defaults to 26214400 (25 MiB). Oversized HTTP uploads return 413. Invalid syntax/fields return 422, invalid registration keys return 403. Success returns 201 with `ontology_id`, `lifecycle_status=draft` and syntax-validation details. Refresh Ontology Registry to see the draft; graph views can remain empty until approved publication. Backend ingestion/QIF workflows use the server ontology write credential rather than forwarding an unrelated client token.


### Service readiness and gateway credential checks

`/healthz` confirms that a service process is running. `/readyz` also checks its configured dependencies. In production, missing database configuration reports `503`; Neo4j readiness checks the database selected by `NEO4J_DATABASE`, not only the server connection.

Pipeline publication uses `CEIM_PUBLISH_APPROVAL_TOKEN`; publication recovery reads use `GRAPH_READ_TOKEN`. Keep both in the root `.env.local`. In gateway mode, backend calls also use the root `DEPO_APIM_SUBSCRIPTION_KEY`, scoped to `DEPO_API_GATEWAY_URL`. Do not copy server credentials into frontend environment files.

After editing backend configuration, restart backend services with the installation's stop/start sequence. Once services are running, execute the full diagnostic from the repository root:

```powershell
Set-Location E:\App\PMem
.\diagnose-depo.ps1 -EnvFile .env.local
```

Expected result: every enabled service responds and the diagnostic completes without a failed check. A successful offline package check alone does not prove that PostgreSQL, Neo4j or Azure APIM can be reached.


### Publish a completed semantic data job

1. Open **Metadata Registry** and create/review the semantic release. Complete its steward and approval evidence, then approve it.
2. Open **Data Flow** and click **Load approved semantic releases**. Select the approved asset/version.
3. Enter a stable **Source system** identifier, for example `teamcenter-customer-prod`. Reuse this value on subsequent publications from that same system.
4. In token mode, enter the approver and the key for the action: execution/replay uses `DATA_JOB_EXECUTION_TOKEN`; definition governance uses `DATA_JOB_APPROVAL_TOKEN`; semantic publication uses `CEIM_PUBLISH_APPROVAL_TOKEN`. Keys stay in browser memory.
5. Publish the completed accepted semantic run. The backend rechecks release approval and SHACL before graph publication.

For new scoped publications, root `.env.local` must contain completed tenant/project values and the scope mode:

```dotenv
DEPO_TENANT_ID=customer-a
DEPO_PROJECT_ID=engineering-prod
DEPO_CEIM_IDENTITY_MODE=scoped
```

Scoped IDs include the tenant/project/source-system boundary. Existing graph IDs are not rewritten. To preserve an existing single-source legacy integration temporarily, explicitly set `DEPO_CEIM_IDENTITY_MODE=legacy`; agree a data migration before switching its historical graph to scoped IDs. Do not use legacy mode to combine unrelated systems whose local identifiers overlap. Rebuild the frontend after updating these UI files and restart backend services after changing configuration.

Generic XML profiles retain existing leaf text fields, preserve qualified element/attribute names and mixed text/tails under `_xml`, and expose repeated leaf attributes under `<field>_attributes`. For `<Value unit="mm">3.2</Value>`, map `Value` to the value and `Value_attributes.0.unit` to the unit. The extraction helper supports numeric list indexes in dotted paths.


### Graph 403 and Create ontology from XSD: separate read, upload and publication

A green Online indicator reports service availability, not permission to read or write.
A 403 from `/api/v1/graph/overview` means the graph request was rejected. In the
frontend header, select **API access**, enter the **GRAPH_READ_TOKEN** from the
root `.env.local` loaded by the running services, and select **Apply and retry**.
The updated dialog checks a protected graph request before confirming access.
A full browser reload clears this key: enter it again afterwards. Changing a key
in `.env.local` requires restarting backend services before using the new key.
When routing through APIM, enter its subscription key too and ensure its policy
forwards the Authorization header to the backend.

For **Import → Create ontology**, use this sequence:

1. In **Admin → Connect registered service credentials**, connect using ADMIN_API_KEY and request the required workflow scopes. Alternatively test and apply INGESTION_WRITE_TOKEN in the central Service credentials table.
2. To create and publish an XSD/XMI ontology, select **Convert XSD/XMI to OWL,
   register and publish to Neo4j after policy and quality checks**. The ingestion
   service calls the ontology service and graph service using its configured
   ONTOLOGY_APPROVAL_TOKEN and GRAPH_PUBLICATION_TOKEN. These server keys must be
   configured on the running services; do not enter them into frontend build files.
3. Select the source XSD/XMI file, complete its ontology name and prefix, and
   select **Start**. The publication option produces OWL through the engineering
   conversion workflow. Leaving it unchecked uses the selected generation type
   and retains/registers the source; it does not publish a graph.
4. Read the result message. **Published** requires a successful graph publication
   response. **Registered source** only confirms source registration. A policy,
   quality or parsing error is not a successful publication.
5. Open Graph Explorer with validated read access. For a restored failed row,
   remove that row and select the original source file again. Persisted jobs do
   not retain the browser's local File object and cannot retry from it.

Related XSD includes/imports still require the schema-set workflow and their
referenced files. Uploading a collection of unrelated single-file jobs does not
make their dependencies available to each other. Inspect the detailed failure
message before retrying a schema that refers to sibling XSD files.

After applying the source changes, rebuild and restart the frontend. From a
PowerShell prompt on the application VM:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
Set-Location .\frontend
# Close running Vite/Node processes for this frontend before replacing dependencies.
# Run npm ci only when dependencies have not been installed or the lockfile changed.
if (-not (Test-Path .\node_modules\vite\bin\vite.js)) { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' } }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
Set-Location ..
.\infra\windows\start-depo-frontend.ps1 -EnvFile .env.local -BindHost 10.0.2.16
```

Replace `E:\App\PMem` and `10.0.2.16` with your installation path and application
VM address. Reload the browser once to load the new bundle, then apply the read
key and upload key in the UI. Do not reload again to retry authenticated requests.


### Import service OpenAPI contracts and map runtime credentials

After deploying this version, restart backend services to publish the updated
`/openapi.json` metadata and rebuild the frontend using the commands above.

1. Open **API access** in the frontend header. If using APIM, enter its
   subscription key before importing contracts.
2. Select **Import service OpenAPI contracts**. The frontend contacts all ten
   configured service roots. It displays an imported operation count or a
   connection/CORS/gateway failure for each service. It does not use server URLs
   embedded inside an imported document to redirect credentials.
3. The imported contracts list required key names, such as INGESTION_WRITE_TOKEN,
   DATA_JOB_EXECUTION_TOKEN or DATA_PRODUCT_APPROVAL_TOKEN. Enter each required
   value from the environment loaded by your running services into its password
   field. Values stay only in the tab's memory; entering a key does not certify
   its validity. The backend validates it when an operation runs.
4. Enter GRAPH_READ_TOKEN in the existing read-key field and select **Apply and
   retry** to validate graph reading. Successful validation refreshes the page
   data without a full browser reload.
5. Execute your workflow. A single explicit operation profile selects its runtime
   key automatically. Credentials explicitly entered on a workflow page take
   precedence. Multiple or unresolved protected profiles are not guessed; use
   that workflow's explicit credential controls and inspect its error message.
6. **Clear** removes all profile keys, the read key and the subscription key.
   Reloading also clears them. Reopen API access to import current contracts after
   a service upgrade or a switch between local and gateway routing.

Contracts contain non-secret `x-depo-authorization.credential_profiles` names,
not key values. Discovery adds route ownership while the existing route map
remains available when a service is offline. Duplicate ownership is not resolved
by guessing a service. OpenAPI discovery does not replace business approval,
policy checks, database migrations or worker readiness.


### SysML v2 repository import and ArchiMate completeness

Configure these entries in the existing root `.env.local` (replace existing values
rather than adding duplicate keys). The repository URL and IDs below are examples;
replace them with values from your SysML server. Do not use a branch ID as a commit ID.

```dotenv
SYSML_V2_API_ENABLED=true
SYSML_V2_API_BASE_URL=https://sysml.customer.example/api/rest
SYSML_V2_API_TOKEN=<repository-read-token>
SYSML_V2_PROJECT_ID=<repository-project-id>
SYSML_V2_COMMIT_ID=<immutable-commit-id>
SYSML_V2_PAGE_SIZE=500
SYSML_V2_REQUEST_TIMEOUT_SECONDS=120
SYSML_V2_MAX_SNAPSHOT_BYTES=67108864
```

The repository token is server-side and distinct from DEPO's
DATA_JOB_EXECUTION_TOKEN. Snapshot download uses the smaller of the configured
SysML snapshot limit and DEPO_MAX_INGEST_BYTES and stops while streaming if the
aggregate limit is exceeded. It also limits page size, element count and page
count and rejects pagination outside the configured commit.

After updating server configuration, restart backend services from the app root:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-services.ps1
.\infra\windows\start-depo-services.ps1 -EnvFile .env.local
```

Rebuild and restart the frontend after installing this version, using the
frontend rebuild commands above. Then:

1. Apply GRAPH_READ_TOKEN through **API access**, then open **Import → SysML repository**. Configuration and readiness endpoints require read authorization.
2. Select **Check repository configuration** and verify the displayed project and
   commit. This checks configuration; it does not certify repository connectivity.
3. Enter DATA_JOB_EXECUTION_TOKEN in API access or the tab's execution-key field.
4. Select **Import configured commit** once. Download, reference validation and
   governed execution happen on the server. Read any validation error before retrying.
5. Follow **Open Data Flow** to review the returned durable run and required
   approval/publication steps. Import success does not itself publish a graph.

This adapter consumes repository element JSON and SysML v1 XMI; it does not parse
native `.sysml` or `.kerml` text. Invalid root shapes, IDs, types and references
produce validation errors. Single-name type arrays are normalized; multiple type
names require an explicit model conversion rather than an arbitrary choice.

For **Import ArchiMate process model**, duplicate identifiers fail parsing.
Unresolved element, view or folder references remain visible in preview diagnostics
but block graph commit. Correct the source model and re-import it before loading;
there is no implicit partial-publication bypass.


### Track imports and recover interrupted agent runs

1. After submitting a governed import or SysML repository commit, retain the returned `run_manifest.run_id`. Queued and running mean the durable worker has not finished; they do not mean the ontology is published.
2. Click **View run** in the import monitor. It opens `#/data-flow/<run-id>` and fetches that exact run, including runs outside the recent list. A missing or inaccessible run displays an error; check API access before submitting again.
3. In Data Flow, inspect the status and retained evidence. Replay creates a new run ID; the selected replay shows its **Replay of** parent. Retain both IDs for support.
4. If an agent request fails after execution starts, the API returns `X-DEPO-Run-ID`. The frontend displays **Execution needs review**. Click **Load retained run status** before retrying. A deadline-expired run may require reconciliation of downstream writes.
5. API clients can retrieve retained agent state using authenticated `GET /api/v1/workflow-runs/<run-id>` for workflows or `GET /api/v1/runs/<run-id>` for tool runs at the configured agentic service base. Use the read credential profile shown in API access. Workflow records include `telemetry_run_id`; telemetry includes `workflow_run_id`. These IDs identify different records and should not be substituted for one another.

Rebuild the frontend and restart the agentic service after deploying these changes. Live worker recovery still requires verification against the customer's PostgreSQL and downstream services.


### Agent execution limits and recovery access

Configure these optional limits in the root `.env.local` before starting services:

```dotenv
AGENTIC_MAX_RESPONSE_BYTES=8388608
DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS=30
```

The first value bounds each decoded downstream tool response to 8 MiB, including chunked responses. Narrow requests that exceed it. The second value bounds PostgreSQL registry statements to 30 seconds (allowed 1–300); lock waits are capped at 10 seconds or the configured statement limit, whichever is smaller. Existing PostgreSQL connection timeout configuration also applies. Restart backend services after changing either value.

Workflow results now require the same execution owner, or supervisory access with `AGENTIC_APPROVAL_TOKEN` in token mode. Configure that operation's credential in **API access** using its discovered profile when retrieving approved workflows or historical ownerless workflow records. A shared graph read key does not grant access to another execution owner's complete workflow traces. Entra deployments use the existing gateway approval-role checks for supervisory access. Ownerless historical records are never assigned to the first reader.

Ontology and companion responses include telemetry run IDs, and processing errors expose `X-DEPO-Run-ID`. DT integration recovery uses `/api/v1/integrations/dt-requirements-design/runs/<run-id>` with its existing approval credential. `dispatch_uncertain` means inspect the remote outcome before retrying; it is not permission to resend. Cancellation stops waiting locally but cannot retract a PostgreSQL statement already executing in a background thread or a dispatched remote write. The statement deadline bounds that database work.


### OSLC read access, remote synchronization and TRS paging

OSLC graph/query/TRS/dictionary/taxonomy data endpoints require the configured read credential. Public catalog/provider discovery remains available. Configure OSLC API access using the service's imported OpenAPI credential profiles; a successful health response does not authorize data reads.

Remote calls require `OSLC_REMOTE_ENABLED=true`, a completed `OSLC_REMOTE_BASE_URL`, and the provider credential in `OSLC_REMOTE_TOKEN` when required. Leave the switch false to disable outbound calls. `OSLC_MAX_RESPONSE_BYTES=8388608` optionally caps decoded remote responses to 8 MiB. Restart the OSLC service after configuration changes.

Staged snapshot reads additionally require explicit grants in root `.env.local`. Replace the example actor with the identity returned by your read-credential configuration:

```dotenv
OSLC_LIFECYCLE_READ_GRANTS={"ui-user":["syncs:*","ontologies:*"]}
OSLC_TRS_MAX_BASE_RESOURCES=50000
OSLC_MAX_RESPONSE_BYTES=8388608
OSLC_SYNC_MAX_PAGES=20
OSLC_SYNC_MAX_RESOURCES=10000
OSLC_SYNC_MAX_BYTES=33554432
```

Merge grants into existing policy instead of replacing it. For access to only one snapshot use `syncs:<snapshot-uuid>`. Listing all snapshots requires `syncs:*`. Ontology shape reads require `ontologies:<ontology-id>` or `ontologies:*` on both primary and fallback resolution paths. The actor must match the configured read token actor; the example does not establish a new user identity.

Remote synchronization strips approval fields before dispatch/storage. Existing snapshot parameter files are redacted when snapshots are listed or retrieved. Previously exposed credentials must be rotated using the existing rotation process; removing stored values does not revoke a key or erase remote logs.

Remote synchronization follows pagination within the configured provider base, up to `OSLC_SYNC_MAX_PAGES`. Cyclic pagination or exceeding resource/byte bounds fails without writing a snapshot. If the page cap is reached, the snapshot is `staged_partial` with `complete=false`; retrieve the remaining pages before approving ingestion. Local OSLC query responses expose `nextPage` and preserve filters.

Catalog, provider, shape, query and graph resource routes negotiate `application/json`, `text/turtle`, `application/rdf+xml`, or `application/ld+json`. JSON remains the default. Unmapped metadata uses DEPO extension predicates; this is not certification of complete OSLC domain conformance. SHACL property descriptors retain `shape_id` and `target_classes`; multiple class-specific constraints are not combined into one global cardinality.

The provider advertises these read-only domain projections:

| Domain | Query resource types | Supported projection |
| --- | --- | --- |
| RM | `requirements`, `requirement-collections` | Requirements, collections, common metadata and retained `oslc_rm:uses` links |
| AM | `architecture-resources` | Architecture/model elements recognized from graph labels and source metadata |
| CM | `change-requests` | Change requests and retained status; no lifecycle transitions |
| QM | `test-cases`, `test-results` | Test cases/results and retained result status |
| AP242 profile | `resources` | General graph discovery; no dedicated AP242 query filter or complete OSLC domain claim |
| Registered ontologies | `ontology:<ontology-id>` | Queries scoped to the registered ontology and retained ontology shapes |

Resource responses expose mapped values in `domainProperties` alongside original `properties`; RDF responses publish those mapped predicates directly. Missing values are not synthesized. Discovery `supportProfile` explicitly lists read operations and unsupported writes/transitions. Enabling a domain does not enable creation factories, updates, deletions, approval workflows or complete domain conformance.

After importing the root environment in PowerShell, test a query as follows:

```powershell
Set-Location E:\App\PMem
. .\infra\windows\runtime-config.ps1
Import-DepoEnvironment -Root 'E:\App\PMem' -EnvFile '.env.local'
$headers = @{ Authorization = "Bearer $env:GRAPH_READ_TOKEN"; Accept = 'text/turtle' }
$base = $env:OSLC_BASE_URL.TrimEnd('/')
Invoke-WebRequest -UseBasicParsing -Uri "$base/oslc/query/resources?oslc.paging=true&oslc.pageSize=20" -Headers $headers
```

Set `ONTOLOGY_SERVICE_URL` to the reachable ontology API base including `/api/v1` (direct example: `http://10.0.2.16:8011/api/v1`). OSLC ontology export links use that service URL rather than the OSLC port. Retained `uri` or `rdf_uri` identities produce stable graph-resource links; resources without either still use legacy Neo4j element IDs and need a durable identity before links can survive recreation.

For TRS Base, start with `/oslc/trs/base?limit=200`, retain its `snapshot_id` and `cutoff_order`, then follow `nextPage` until null. All pages use the same retained membership. Snapshots expire after 15 minutes; restart the Base if expired. After completing the Base, read `/oslc/trs/changelog?after=<cutoff_order>&limit=200` and advance `next_after`. If `rebase_required=true`, start a fresh Base. A Base above `OSLC_TRS_MAX_BASE_RESOURCES` fails explicitly; adjust capacity and restart the Base instead of accepting truncated state. Concurrent graph mutation/change-event publication still requires customer integration validation.


### PostgreSQL schema upgrade integrity and legacy checksum adoption

Schema updates now verify the final structure **before committing** migrations and history. Failure rolls back the update transaction. Migration 007 adds registry/runtime JSON object constraints and a namespace/history index. Invalid existing scalar/array JSON causes a clear constraint failure; diagnose the rows before retrying. No upgrade deletes customer records.

Fresh installations record SQL checksums automatically. For an existing installation created before checksum tracking, first review the SQL files in `infra/postgres/migrations` against your deployed release and take a database backup using your DBA process. Adopt historical checksums explicitly in root `.env.local`:

```dotenv
DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS=true
DEPO_MIGRATION_STATEMENT_TIMEOUT_SECONDS=300
DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS=30
```

From the repository root, run:

```powershell
Set-Location E:\App\PMem
.\infra\postgres\update-postgres-schema.ps1 -EnvFile .env.local
.\infra\postgres\test-postgres-schema.ps1 -EnvFile .env.local
```

After successful adoption, change `DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS=false`. Retain the two timeout values as appropriate. Migration statements allow 1–3600 seconds with lock waits capped at 60 seconds; registry and compatibility runtime statements allow 1–300 seconds with lock waits capped at 10 seconds. Connection timeout remains independently configured.

Verification checks the released relations, columns, constraints, index definitions, required nullability/defaults, chat message sequence, analytics view and all numbered migrations with checksums. Use the current JSON verifier output for exact counts and migration versions. A drift failure does not grant permission to delete or recreate a customer table. Restore the matching immutable release SQL for checksum differences; use a reviewed corrective migration for schema/data changes. Read-only verification never adopts missing checksums.

The ontology analytics view remains an ontology-statistics projection. This schema update does not create a dimensional warehouse or populate fact/dimension tables.


### XSD structural analytics data-product output

XSD conversion returns a `schema-analytics-data-product-v2` draft with retained source XSD, Turtle serialization, ontology SHACL, analytics profile, structural model and analytics schema plan references. Supplied XSD dependencies also remain retained artifacts. Draft `artifacts` entries contain `artifact_id` objects compatible with the publication API. Non-XSD conversion contracts remain compatible with v1. The existing `schema-analytics-product` data job accepts both versions and computes bounded schema statistics without requiring Spark.

The structural model uses namespace-qualified entity IDs, effective occurrence ranges, particle paths and resolved datatype/facet metadata. Anonymous roots and repeated primitive values have entity-table plans. Prohibited attributes are excluded; nillable elements have nullable SQL projections. The source XSD remains the authority: Turtle alone does not preserve every closed-world XML constraint.

To inspect an already registered XSD, request `/reports/xsd-relational?ontology_id=<registered-id>` at the ingestion service base with the configured read credential. Its response includes `analytics_schema_plan`. This endpoint requires an accessible original XSD and its local include/import closure. Dependencies must stay inside the approved schema-set directory; remote dependencies are not downloaded. A single-file conversion with missing dependencies retains a blocked model draft rather than claiming a complete schema.

Inspect `ddl_blockers`, `validation.formal_xsd_validation`, `analytics_schema_plan.sql`, and `data_product_draft.quality_status`. The PostgreSQL SQL is a **new-schema review plan**, not an upgrade script; it is never executed by conversion. Plans with unsupported choice/group/identity/facet mappings contain no SQL. Review-only plans never authorize automatic DDL or publish a data product. Formal grammar compilation uses lxml when installed; lack of that compiler is an explicit blocker.

This product is schema-design evidence. Before building reporting tables, define fact grain, dimension keys, measure expressions, units, aggregation and history policy; then implement and approve XSD-validated instance materialization with cardinality, identity, count reconciliation and lineage checks. Those business definitions and the generic XML-to-warehouse loader are still required. No fact/dimension data or customer tables are created by this change.


### Graph key rejected after OpenAPI import

OpenAPI import discovers routes; it does not authenticate graph reads. In **API access**, paste only the value of `GRAPH_READ_TOKEN` from the root `.env.local` used to start the services. Do not paste `GRAPH_READ_TOKEN=`, `Bearer `, the administrator key, graph publication key, or APIM subscription key. Enter an APIM subscription key in its separate field when applicable.

The Apply action calls `/api/v1/graph/access`, which validates read authorization without querying Neo4j. A rejected key must be corrected in the browser or the running service configuration. After changing the root `.env.local`, stop and start backend services so they load the new value. After deploying this frontend change, rebuild the frontend and reload the browser; keys are held only in tab memory.

From PowerShell on the application VM, test the actual configured graph URL (replace the example host if needed) without writing the key into command history:

```powershell
$graphKey = Read-Host 'GRAPH_READ_TOKEN' -AsSecureString
$graphCredential = New-Object System.Management.Automation.PSCredential('reader', $graphKey)
$graphHeaders = @{ Authorization = 'Bearer ' + $graphCredential.GetNetworkCredential().Password }
Invoke-RestMethod -Uri 'http://10.0.2.16:8013/api/v1/graph/access' -Headers $graphHeaders
Remove-Variable graphKey, graphCredential, graphHeaders
```

For gateway mode use the configured gateway graph API base followed by `/graph/access` and supply the gateway subscription header if required. If this direct test succeeds but the browser fails, inspect the browser request URL and whether Authorization reaches the service. If it fails, use the returned detail to check the running graph service's key, expiration and authentication mode. Never include keys in screenshots or logs.


Graph access diagnostics now distinguish these cases:

- HTTP 503, `GRAPH_READ_TOKEN is not configured`: the running graph process did not load a usable read key. Check the root environment file supplied to the launcher and restart backend services.
- HTTP 403, `Authorization header is missing`: inspect the request headers and gateway Authorization forwarding. OpenAPI import alone does not apply the read key.
- HTTP 403, `key does not match`: use the read key loaded by the running graph service. Changing a file does not update an already running process.
- HTTP 401, `API key has expired`: check `GRAPH_READ_TOKEN_EXPIRES_AT` and the shared `DEPO_TOKEN_EXPIRES_AT` policy with the deployment administrator.
- HTTP 404 on `/api/v1/graph/access`: deploy the matching backend version; the browser and backend releases are out of sync.

The access check explicitly sends the entered read key and does not depend on the imported contract's credential metadata. No key values are returned by this endpoint. An ingestion OpenAPI timeout is a separate connectivity/response failure; inspect the configured ingestion `/openapi.json` URL and the ingestion service logs rather than changing the graph key.


### Prevent stale frontend and legacy deployment confusion

The supported customer entry point is root `install-depo.ps1`. It orchestrates scripts under `infra/windows` and `infra/deployment`; `infra/windows/install-depo.ps1` installs dependencies only. The service inventory in `infra/deployment/services.json` defines ten APIs and three workers (catalog outbox, data pipeline and agentic workflows). Root `main.py` and `backend/main.py` are retained compatibility/test hosts, not customer startup targets.

The frontend launcher checks source files, public assets, frontend environment files, Vite configuration and dependency manifests against the built index timestamp. Rebuild after changing any of those inputs. This timestamp check detects common stale builds; it is not a content-hash release attestation and preserved file timestamps can defeat it.

Never add token, password, secret, API-key or subscription-key values under `VITE_*` or `REACT_APP_*` names. Vite can compile prefixed values into browser assets. The build now rejects credential-shaped setting names and reports names only. Keep server credentials in the root deployment environment and enter browser credentials through API access.


### Build identity and compatibility configuration safeguards

Rebuild once after upgrading to the build-receipt release. `npm run build` now emits `frontend/dist/depo-build-receipt.json` containing SHA-256 hashes of frontend source, public assets, environment files, Vite configuration, package manifests and the receipt plugin. The Windows frontend launcher compares the current file set and hashes with this receipt and refuses stale or missing receipts. This detects changed/deleted inputs even when deployment copies preserve timestamps. It is an input-consistency check, not a signature or complete bundle-integrity attestation. A source-free customer package needs a separate supported integrity procedure; this launcher expects the repository layout.

Do not hand-edit the receipt. Run the documented frontend build after changing build inputs. Root `.env.local` runtime routing changes still use the runtime-routing launcher and are not frontend build inputs. Inherited build-only environment changes also require a rebuild; they cannot be verified from filesystem hashes.

Conflicting `VITE_*` and matching `REACT_APP_*` settings now stop the build. Use the current `VITE_*` setting or identical compatibility values. The managed Windows environment importer sets `DEPO_ENV_INJECTED=true`; production and managed Neo4j consumers skip legacy `.env` discovery. Configure every required value in the selected root deployment file or process-manager environment instead of relying on old defaults.


### Integration release fixes: definition authoring, startup and acceptance

Creating a data-job definition (`POST /api/v1/pipeline/jobs/definitions`) now requires the existing `DATA_JOB_APPROVAL_TOKEN` header credential. The backend derives `owner` from `DATA_JOB_APPROVAL_TOKEN_ACTOR`, or `data-job-author` when that optional actor is absent. A caller's owner field cannot impersonate another author. In the API-access dialog import current OpenAPI contracts, then enter the `DATA_JOB_APPROVAL_TOKEN` profile for definition authoring/approval. The baseline seeder uses that key and the selected local/gateway routing configuration; `DATA_PIPELINE_SERVICE_TOKEN` is no longer its credential. Definitions are inserted atomically; an existing job/version returns HTTP 409 and is never overwritten during creation.

`infra/windows/start-depo-postgres.ps1` starts only the explicitly selected service/portable PostgreSQL runtime. External mode makes no server changes. The installer invokes it before URL connectivity and schema migration; API startup reuses the same helper. Custom `-EnvFile` now also reaches frontend routing preflight.

Every service exposes `/auth/access` for read-key validation without shared-store queries. Token-mode startup and deployment validation require the current `GRAPH_READ_TOKEN` to pass that check on all ten services. An old running process using a different key must be stopped and restarted; a missing `/auth/access` means backend modules must be upgraded together. This detects stale read keys, not every possible configuration change. Restart services after other configuration changes too.

Certification now requires structured JSON acceptance evidence for this deployment and commit. Add a unique nonsecret value, for example `DEPO_DEPLOYMENT_ID=customer-depo-vm01`, to the selected root environment. Each of the four evidence JSON files must contain:

```json
{
  "contract_version": "depo-acceptance-v1",
  "deployment_id": "customer-depo-vm01",
  "git_commit": "<full-release-commit>",
  "evidence_type": "browser_acceptance",
  "status": "pending",
  "reviewer": "<reviewer-name>",
  "executed_at": "<actual-UTC-time-with-Z>",
  "checks": [{"name": "<actual-check-name>", "status": "pending"}]
}
```

This is an intentionally nonpassing template. After executing and reviewing the real checks, record their actual results, the commit from `git rev-parse HEAD`, and the actual timezone-qualified execution timestamp. All checks and the overall status must be `passed` for certification. Use evidence types `supervisor`, `backup_restore`, `browser_acceptance`, and `rollback` in their matching files. Certification rejects failed results, wrong commits/deployments/types, empty checks, missing reviewers and future timestamps. It verifies the evidence contract, not whether a person truthfully performed the claimed check; retain supporting logs/screenshots and review them.

From the repository root, after successful customer acceptance:

```powershell
.\certify-depo-release.ps1 -EnvFile .env.local -SupervisorEvidencePath release-evidence/supervisor.json -BackupRestoreEvidencePath release-evidence/backup_restore.json -BrowserAcceptanceEvidencePath release-evidence/browser_acceptance.json -RollbackEvidencePath release-evidence/rollback.json
```

Offline regression scripts exercise authorization boundaries, insert-only conflict semantics, PostgreSQL runtime selection and evidence rejection. They do not replace real concurrent PostgreSQL requests, live gateway tests or browser workflow acceptance. Do not certify a customer release from offline checks alone.


## Worker execution readiness and lease fencing

API readiness and job execution readiness are separate checks. `/readyz` checks API dependencies. In worker mode, `/api/v1/pipeline/execution-ready` returns HTTP 200 only when a current worker heartbeat exists; otherwise it returns HTTP 503. Inline mode does not require a worker. Authentication is checked separately through `/auth/access`.

From PowerShell on the application VM, use the configured application host in this command (the example host is `10.0.2.16`):

```powershell
Invoke-RestMethod -Uri 'http://10.0.2.16:8019/api/v1/pipeline/execution-ready'
```

Windows startup and deployment diagnostics perform this worker readiness check automatically. If it fails, inspect `logs/windows-services/data-pipeline-worker.err.log`, PostgreSQL connectivity, and worker heartbeats. A live process ID alone does not establish execution readiness.

The worker checks run ownership, attempt identity, and lease expiry before execution, registry writes, artifact retention, and completion. Renewal failure prevents subsequent guarded persistence. Already running native, Spark, or external operations may finish; this mechanism cannot undo external effects and does not guarantee exactly-once execution. Review external effects before replaying a failed run.

Catalog reconciliation reads a bounded batch of due records, serializes publication, retry, and revocation with a per-product advisory lock, and conditionally updates unchanged records. HTTP 409 means another product operation owns the lock; retry after it completes. A remote catalog call and a local PostgreSQL update are not one atomic transaction.

Code Network excludes generated `dist` files and includes JavaScript modules, PowerShell, SQL, and JSON source files. Literal file references and Python launch references contribute impact edges. Dynamic paths and environment-dependent routing still require manual inspection; the complete graph analysis requires the installed NetworkX dependency. Registry namespace ownership is recorded in `docs/architecture/REGISTRY_NAMESPACE_OWNERSHIP.md`.


## Tracked imports, Bridge approval, and publication retries

Standalone ingestion on port 8014 hosts `/api/v1/import/upload`, `/status/{task_id}`, `/preview/{task_id}`, `/pre-commit/{task_id}`, `/commit/{task_id}`, and `/cancel/{task_id}`. Configure `INGESTION_WRITE_TOKEN` for upload, cancellation, and commit; use `GRAPH_READ_TOKEN` for status, preview, and pre-commit reads. Commit additionally requires the approver and approval key through the frontend review dialog. Restart services after updating server keys. Import API access profiles must match the keys loaded by the running services.

For instance-to-ontology linking, select a completed instance import and target ontology in Import. Use the embedded Bridge job controls to create a preview, review candidate IDs, and publish approved mappings. The older semantic workflow report is preview-only.

After a concurrent-change conflict, refresh the job definition before retrying; stale approval must not undo disable. Quality-warning runs are finished executions requiring evidence review; they are not automatically approved for publication.

The first semantic publication attempt binds its ontology, prefix, release, source, and batch digest. Retry the same values to reconcile an interrupted call. Conflicting destinations return HTTP 409. Published runs return the stored receipt even without a checkpoint. Do not change destinations to bypass an uncertain result.


## PostgreSQL connection rejection diagnostics

Run from the application VM, using the root environment file:

```powershell
Set-Location E:\App\PMem
.\infra\postgres\test-postgres-connectivity.ps1 -EnvFile .\.env.local
```

The selected file must contain `DEPO_DATABASE_URL` or its legacy alias `DATABASE_URL`. A stale shell alias cannot override the other alias configured in this file. Failure JSON reports password-free `connection` fields. An HBA rejection also reports PostgreSQL's validated `rejected_client_address` and, for simple database/role names, an `hba_rule_example`. The connection host is the database VM; the rejected client address is the application VM as seen by PostgreSQL, including any NAT. These addresses need not match.

On the database VM, use pgAdmin's administrator Query Tool:

```sql
SHOW hba_file;
SELECT line_number, type, database, user_name, address, auth_method, error
FROM pg_hba_file_rules ORDER BY line_number;
```

Edit the exact returned file to add the diagnostic's example rule using your real user, database, and client address, before any applicable reject rule. `host` matches SSL and non-SSL TCP connections; `hostssl` will not match `sslmode=disable`. Then check errors and reload:

```sql
SELECT line_number, error FROM pg_hba_file_rules WHERE error IS NOT NULL;
SELECT pg_reload_conf();
```

The error query should return zero rows. Retest connectivity before running `.\infra\windows\initialize-depo-schema.ps1 -EnvFile .\.env.local`. A working database-local pgAdmin connection does not establish remote application access. Never paste the full database URL or password into diagnostic reports.


## Windows startup configuration and recovery

Add these public frontend listener settings to the root `.env.local`, substituting your application VM address:

```dotenv
DEPO_SERVICE_HOST=10.0.2.16
DEPO_FRONTEND_HOST=10.0.2.16
DEPO_FRONTEND_PORT=3000
```

`DEPO_FRONTEND_HOST` defaults to `DEPO_SERVICE_HOST`, then loopback when neither is supplied. Explicit `-BindHost` and `-Port` arguments take precedence. Wildcard addresses are listener settings; open the VM's actual address in the browser.

```powershell
Set-Location E:\App\PMem
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .\.env.local
```

Backend command-line Spark switches are applied after schema initialization reloads configuration. Non-Spark approved jobs can be scheduled with `DEPO_SPARK_ENABLED=false` and `DEPO_PIPELINE_SCHEDULER_ENABLED=true`; Spark-dependent handlers still require Spark. Readiness and CORS errors are reported before testing API keys.

Frontend content hashes in the build receipt determine whether a rebuild is needed; copying unchanged files with newer timestamps does not require one. Launchers check that the selected port/binding belongs to their verified process tree before accepting reuse. Startup rollback and frontend stop terminate verified descendants before parents, retaining tracking when cleanup fails. PID reuse or an unidentified port owner requires inspection; these scripts do not terminate unrelated processes.

```powershell
.\infra\windows\stop-depo-frontend.ps1
.\infra\windows\stop-depo-services.ps1
```

If a tracked backend listener has a different bind address, stop it before changing `DEPO_SERVICE_HOST` or `-BindHost`. A frontend process that has already lost its launcher cannot safely be identified by its port alone; inspect the reported owner rather than killing arbitrary Python processes.


### Central browser credential setup in Admin

Open the frontend, select **API access** in the header, and use **Admin → Service credentials**. Enter the administrator-issued `GRAPH_READ_TOKEN`, select **Test and apply**, and require **Validated and applied** before opening graph pages. Repeat for `INGESTION_WRITE_TOKEN` before creating an ontology, and `DATA_JOB_EXECUTION_TOKEN` before submitting governed instance jobs. Each test checks authorization without uploading data or executing a job. Enter the APIM subscription key only for gateway routing. A rejection means the running service does not accept the supplied key; check the root environment file selected at backend startup and restart after changing server keys.

The Import page uses these shared credentials and no longer has separate upload/execution key fields. A full browser reload clears manually entered keys. Delegated central sessions survive same-tab refresh until expiry. OpenAPI contract import discovers operations and additional profiles but does not validate those additional credentials. With DEPO_CREDENTIAL_STORE=postgres, use the explicit database registration and rotation controls described below; Test and apply alone changes only browser credentials. For restored failed uploads, remove the row and attach the original file again before starting.


All 17 application credential profiles, including `ADMIN_API_KEY`, approval, publication, vocabulary, federation, retention and speed-path keys, are entered and tested in **Admin → Service credentials**. Workflow pages consume the shared profile at the time of the action; users still enter approver names and confirm writes on those pages. A successful key test validates credentials on the selected service only; it does not approve a write or guarantee downstream dependencies. Backend `NEO4J_PASS`, database passwords, `DT_AGENT_GATEWAY_TOKEN`, `OSLC_REMOTE_TOKEN` and other outbound secrets remain server-side in the root configuration. Database registration stores salted key digests only when DEPO_CREDENTIAL_STORE=postgres; browser key values remain in tab memory.


### Catalog, products and agent workflow checks

After **Admin → Service credentials → GRAPH_READ_TOKEN → Test and apply** succeeds, open **Data Catalog** to browse registered product versions, or **Data Products** to inspect published package metadata. An empty list means that service has no registered products; registering an ontology does not automatically publish an analytics product. Credential changes refresh these views and clear previously loaded details.

For a multi-step agent workflow, validate `AGENTIC_APPROVAL_TOKEN` in Admin, then enter its run ID in **Admin → Agent workflow control** and select **Inspect / refresh**. Pause, resume and cancel requests take effect at the next tool boundary. They retain completed writes and do not extend the original deadline. Standalone ontology review operations are single operations and do not use these controls.

Ontology agents must be permitted to read their retained artifacts. The default `ONTOLOGY_AGENT_ALLOWED_ROOTS=data;ontology;backend/test_data;ontology_uploads` covers repository storage. If `ONTOLOGY_SERVICE_STORAGE` uses another location, add that exact durable directory to the allowed roots. For example, with native ontology storage at `C:\DEPO\data\ontologies`, use:

```dotenv
ONTOLOGY_AGENT_ALLOWED_ROOTS=data;ontology;backend/test_data;ontology_uploads;C:\DEPO\data\ontologies
```

Deploy the updated backend and frontend source together, rebuild using `infra/windows/build-depo-frontend.ps1` as described above, and restart the services and frontend. These controls use the existing PostgreSQL registry; they do not require an additional control table.

### Offline Ollama configuration and functional checkpoints

Ollama must already be installed and its model available on the application VM. Environment entries select a server and model; they do not install either. In root `.env.local`, use the exact model name shown by `ollama list`, for example:

```dotenv
USE_LLM=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL_NAME=llama3:latest
LLM_REQUEST_TIMEOUT_SECONDS=300
ONTOLOGY_AGENT_LLM_ENABLED=true
COMPANION_LLM_ENABLED=true
```

On the application VM, check the runtime:

```powershell
ollama list
Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
```

If Ollama is installed but its server is not running, open a separate PowerShell window and run `ollama serve`. Keep it open during this manual test. If the model is missing, transfer/install it using your approved model distribution process; a disconnected VM cannot download it by changing `.env.local`. Restart DEPO after changes. In **Admin → Agent workflow controls → Check offline Ollama**, require `ready` and check the model and enablement flags. The diagnostic requires read access. Model suggestions cannot approve or publish data.

After rebuilding and restarting matching backend/frontend files, check these flows in order:

1. In manual/gateway mode, connect credentials in Admin. Its delegated session lasts fifteen minutes; reconnect after expiry or rejection. Local broker mode manages session renewal; writes are never automatically retried.
2. Import an XSD, then confirm it appears on Home. Both native and legacy registries are included; different IDs sharing a prefix remain selectable.
3. Select the ontology in Junction. Mapping Vocabulary displays returned mapping edges. A valid empty list means no mappings exist; authorization and service failures must appear as errors.
4. In Semantic Bridge select the imported instance and target ontology directly. For ontology merging, select two different ontology IDs, review the preview, and apply the steward-approved merge. Its result is a registered draft, not automatic graph publication. Retrying the same applied preview returns its retained result.
5. Data Products shows new schema conversions under **Schema design drafts**. Published packages remain separate and require an approved semantic release and product steward approval.
6. In Reports choose **All ontologies** or one ID. Graph reports are bounded projections, not complete warehouse totals. The separate XSD selector remains available after a report error. New native conversions use their retained structural model. Reimport an older conversion if source references were not retained; missing source evidence is not fabricated.

The merge registry uses the existing PostgreSQL registry table; these changes require no new SQL migration.

### PostgreSQL central API-key authority (migration 008)

To enable central authentication on the application VM, set this entry in `E:\App\PMem\.env.local`:

```dotenv
DEPO_CREDENTIAL_STORE=postgres
```

Keep existing application keys in the root file for the first bootstrap. Each must be a random value of at least 32 characters. Supply `ADMIN_API_KEY` and `GRAPH_READ_TOKEN`. Database passwords and outbound integration secrets remain server-side. Use the same store mode and PostgreSQL database/schema for all services. This setting is opt-in for existing deployments; the customer template enables it.

From PowerShell on the application VM:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-services.ps1
.\infra\windows\initialize-depo-schema.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
```

Migration 008 creates `depo_api_credentials` (salted key digests, actor, expiry and revocation) and `depo_api_credential_events` (rotation/revocation audit events). No plaintext keys are stored. Bootstrap inserts missing profiles only: reinstall never overwrites rotated or revoked profiles. Services reject database outages rather than falling back to old environment keys.

In Admin → Service credentials, test and apply the current `ADMIN_API_KEY`. Enter a new random profile key and an assigned actor, then use **Register / rotate in database** and confirm. This invalidates the prior key for that profile. Lost registration responses are ambiguous: test the proposed new key before retrying. Rotating the administrator key requires retaining the new key securely; there is no anonymous password recovery. The **Test and apply** button does not register a key. Graph-read testing checks all configured services, with individual results.

Backend agent dispatch still needs plaintext outbound keys to authenticate to peer APIs. After rotating a profile used by backend calls, update that corresponding root environment value and restart the calling services. Incoming API validation immediately uses PostgreSQL and does not require a restart. This implementation does not distribute plaintext secrets from PostgreSQL. Keep the profile expiry and revocation managed in the authority; expiry changes in legacy environment mode still require restart. Raw browser API keys remain memory-only and must be re-entered after a full reload. Delegated central sessions survive same-tab refresh until expiry.

For Azure APIM, import the updated OpenAPI contracts and preserve the service-relative `/auth/access`, `/auth/credential-check`, `/auth/admin-access` and `/auth/credentials` routes under each service gateway prefix. Forward `Authorization` and `X-API-Key` without substituting the APIM subscription key. Add these routes to the same origin/CORS policy as the existing APIs. Credential management routes require ADMIN_API_KEY and return no plaintext keys or digests. The protected GET `/auth/credentials` returns profile, actor, expiry, revocation and update metadata only.


### Apply service keys from the root environment file automatically

After migration 008 and setting `DEPO_CREDENTIAL_STORE=postgres`, run this on the application VM. No manual database-key entry is required:

```powershell
Set-Location E:\App\PMem
.\infra\windows\apply-depo-service-credentials.ps1 -EnvFile 'E:\App\PMem\.env.local'
```

The script reads only application API-key profiles and their `_ACTOR`/`_EXPIRES_AT` metadata from the selected file, registers missing profiles, and preserves identical records. Missing optional profiles are skipped. An active ADMIN_API_KEY and GRAPH_READ_TOKEN must exist after the batch; otherwise the entire import is rolled back. This command is for AUTH_MODE=token. Each provided key must be a random value of at least 32 characters; expiry must be a future timezone-aware ISO timestamp. A missing actor defaults to `deployment-bootstrap`. Only profile names and results are printed. Secrets are passed over stdin, never command-line arguments or temporary files. The entire batch rolls back on failure.

If the selected file intentionally replaces existing central keys or metadata, review it first, then run:

```powershell
.\infra\windows\apply-depo-service-credentials.ps1 -EnvFile 'E:\App\PMem\.env.local' -ReplaceExisting
```

Replacement revives revoked profiles and invalidates their old keys. Update every caller's protected outbound environment file and restart callers after deliberate rotation. The script uses the protected PostgreSQL connection in this file and must be run by the deployment administrator with table write privileges; it does not require an API gateway or a running HTTP service.

This applies keys to the server authority. It does not inject keys into browsers or persist browser secrets. Admin displays a table of credential profiles, services, key inputs, actions and status; Admin → Connect registered service credentials establishes the current tab's short-lived session using one Admin-key sign-in; per-profile Test and apply remains available as an alternative. Database passwords, Neo4j passwords and outbound connector tokens are excluded from the import.


### RDF, OWL and SHACL artifact checkpoints

New engineering conversions retain a SHACL shapes artifact alongside the source and serialized ontology. Registration records its content-addressed identifier in PostgreSQL metadata for that ontology version. In **Import**, use the completed ontology row's **Export → SHACL shapes (TTL)** option. Older versions without shapes return an explicit unavailable message; re-import the original source to retain the association.

These shapes currently enforce default ontology checks, not every XSD cardinality, choice or datatype constraint. Semantic validation reports `shape_source`, `shape_artifact_id` and `scope`. Use XML/XSD validation for source instance conformance. Full schema-derived shape generation and a shape editor remain unavailable. Rebuild the frontend and restart affected services after this update. No PostgreSQL migration is needed: the association uses existing registry metadata.


### QIF–AP242 agent review checkpoint

In **QIF**, select two distinct registered versions identified as QIF and AP242. **Inspect selected schema inventories** reads retained version artifacts without requiring graph publication. **Run QIF–AP242 agent review** calls the Agentic service using the central graph-read credential. Review source IRIs, target IRIs, structural issues, ambiguity and truncation warnings. Candidates use typed name evidence; they do not establish PMI equivalence, unit conversion or instance traceability. No links are published by this agent. Open Ontology Junction / Semantic Bridge with the AP242 target, select the corresponding QIF instance import run and complete the existing review/approval workflow. A verified engineering mapping profile is still required. Deploy matching backend/frontend files, rebuild the frontend and restart affected services.


### Credential consistency on installation and redeployment

Environment parsing tolerates repeated keys only when their normalized values
are exactly identical (case-sensitive), with a warning naming the key and line
numbers. Conflicting duplicates stop deployment without printing values or
partially importing settings. Keep one entry per key; in particular, retain
only one `GRAPH_PUBLICATION_TIMEOUT_SECONDS=180` entry when using that timeout.

Admin cleanup checkpoints: Clear Cache refreshes projections but does not delete
ontology registrations or execution history. Full Schema Cleanup removes Neo4j
data, legacy upload metadata and native ontology registrations/recovery metadata;
retained native artifacts and backend workflow audit history remain. The Import
page's saved browser projection is cleared so completed rows are not restored as
current graph state. Delete Old XSD Schemas targets only superseded/merged legacy
XSD candidates and their matching native registrations; it does not delete all
ontologies. Partial cleanup must show a warning, not an unconditional success.
Refresh the landing registry after completion and verify the affected ontology
is absent. A historical executed run is not proof its graph output still exists.
With PostgreSQL configured, catalog reads use PostgreSQL exclusively. Retained
local artifact metadata does not automatically restore deleted registrations.
Reset Graph Database alone retains registrations; use Full Schema Cleanup when
the registry must also be emptied. Deploy the updated backend and rebuild the
frontend before checking this behavior, then restart both service launchers.

XSD ontology upload supports named model groups (`xs:group`) from the supplied
schema dependency set. Reattach the original XSD and its local dependencies
after updating the backend, then retry a failed upload. Missing or cyclic group
references still fail before output is written. Nested and repeating choices
retain properties and occurrence ranges but carry conversion limitations:
generated OWL/SHACL is not a replacement for validating XML against the original
XSD. `xs:attributeGroup`, redefine and override remain unsupported by this
conversion profile and produce explicit errors.
Group expansion currently applies to ontology generation. The relational
analytics mapper still reports model groups as unsupported structural
constructs and blocks automatic SQL generation; do not treat the generated
ontology as approval to create or load an analytics warehouse.
Schema dependency resolution stays inside the selected schema directory, with
at most 64 documents and the `ONTOLOGY_AGENT_MAX_BYTES` combined byte limit
(25 MiB by default). Supply relative local `schemaLocation` paths. External
paths, remote URLs, DTDs and entity declarations are rejected before conversion.
If an upload reports an external `schemaLocation`, supply its companion XSD
locally and edit the reference to match its uploaded relative path. For example,
replace `schemaLocation="https://standards.example/common/common.xsd"` with
`schemaLocation="common.xsd"` and attach `common.xsd` alongside the root file.
A dependency at `types/part.xsd` may reference `../common.xsd` when both remain
inside the uploaded set. A root file cannot reference `../common.xsd`: use
`common.xsd` instead. The ontology upload source filename is a plain filename.
In Import -> Create ontology, attach companion schemas using **Companion XSD
files**. Enter one relative path per companion in the selected file order, matching
its `schemaLocation` (for example `common.xsd` or `types/part.xsd`). Letter casing
must match exactly, including folder names, for Windows/Linux portability. Use
literal paths without URI encoding, query strings or fragments. Choose OWL
generation for a root with companions. Selecting unrelated root uploads does not
build a shared dependency set. Companion files must be selected again after reload.

The AP242 Edition 2 BOM schema set is included in
`data/business_object_models/managed_model_based_3d_engineering/`:

1. Open Import -> Create ontology and add `bom.xsd` as the root source.
2. Choose OWL generation and complete the requested ontology name and prefix.
3. Under Companion XSD files, select `common.xsd` from the same directory.
4. Keep its relative path as `common.xsd`, then review and register the ontology.

The bundled `bom.xsd` already imports the local `common.xsd`. Both compile as an
XSD schema set without network access. `SCHEMA-SOURCES.md` in that directory
records the official ISO source and checksum of the unchanged companion file.
Do not substitute the newer `DomainModel.xsd` or remove the import: the BOM
requires the Edition 2 companion definitions. External schemas are never fetched
by the upload service. Analytics SQL generation remains subject to the structural
limitations described above.

For QIF schemas with sibling-folder references, prepare an upload copy first.
`QIFProduct.xsd` uses `../QIFLibrary/...`; a plain root upload loses its original
`QIFApplications` directory. Do not remove those includes or weaken path checks.
Run from the repository root after installing backend dependencies:

```powershell
Set-Location E:\App\PMem
.\backend\.dt_venv\Scripts\python.exe .\infra\prepare-xsd-upload.py --source .\docs\xsd\QIFApplications\QIFProduct.xsd --schema-root .\docs\xsd --output .\qif-product-upload
if ($LASTEXITCODE -ne 0) { throw 'QIF upload preparation failed.' }
Get-Content .\qif-product-upload\dependency-paths.txt
```

The output directory must not already exist. This produces a copied root and
11 companions; it updates references in copies only and never downloads schemas.
In Import -> Create ontology, add `qif-product-upload\QIFProduct.xsd` as the root
and choose OWL. In Companion XSD files select all 11 `.xsd` files from
`qif-product-upload\QIFLibrary`. Enter each relative path as
`QIFLibrary/<selected filename>.xsd`, in the displayed selection order.
`dependency-paths.txt` lists the required paths; ensure its order matches your
selected-file order before pasting. Then review and register. Do not also upload
the original QIFProduct root or queue each companion as a separate ontology.
The same preparation command supports other local schema sets by changing
`--source`, `--schema-root` and `--output`; missing or external dependencies fail
before any output is created. Offline XSD compilation does not certify complete
OWL translation of every QIF construct.

Startup checkpoints, in order: configuration validation; dependencies and
frontend build; configured PostgreSQL runtime handling; application-role login;
transactional schema migration/verification; credential validation or explicit
synchronization; Neo4j constraints; optional Spark probes; API/worker launch;
readiness, listener ownership and authorization; browser-session verification;
release preflight. Success at one checkpoint does not certify later checkpoints.
The frontend build alone does not serve the UI: run its launcher afterward.

If backend startup takes roughly one minute per API, deploy the corrected
`infra/windows/process-control.ps1` together with the matching startup script.
Listener verification must be read-only: it must never create `stop-*.request`
files or wait for shutdown. Cooperative stop requests belong exclusively in
the stop function. Do not increase readiness timeouts to conceal this defect.
The startup script now reports each process check, reuse and launch before
readiness validation. Shutdown requests are sent to all verified service launchers together. The stop
script uses one shared graceful shutdown allowance, defaulting to 60 seconds,
rather than a separate 60-second wait per service. It reports each service while
stopping. Process identity and listener cleanup are still checked afterward.
From the repository root, run:

```powershell
.\infra\windows\stop-depo-services.ps1 -ShutdownGraceSeconds 30
```

This allowance does not include Windows process inspection or optional PostgreSQL
shutdown. Lowering it may force termination of active work after the deadline.
Security prompts pause execution until answered; they are separate from shutdown.
After verifying that the release came from your trusted source, remove the
Windows download warning from its PowerShell files once:

```powershell
Set-Location E:\App\PMem
Get-ChildItem -LiteralPath .\infra -Filter *.ps1 -Recurse | Unblock-File
```

Do not disable execution policy globally. Restarting services does not require
reinstalling dependencies for this stop-script update.

The repository contains two different files named `install-depo.ps1`: the root
file is a launcher; `infra/windows/install-depo.ps1` installs dependencies and
supports `-CheckPrerequisites`. Preserve their original directories when copying
a release. Never overwrite the nested file with the root launcher. The Windows
installer now checks this contract before starting deployment stages.

If root `install-depo.ps1` is missing, restore the complete matching release before installation. Do not substitute an internal dependency helper. If an
environment entry is rejected, repair the reported line in root `.env.local`:
use one `KEY=value` per line or a `#` comment, with no shell commands or Markdown.
Do not create another legacy `.env` file. The dependency installer loads the
selected environment before running the import/OpenAPI checks.
Pip's newer-version notice and npm deprecation warnings are informational when the native command exits successfully; upgrading pip does not repair
application imports, migration SQL or invalid configuration.

To make the selected root `.env.local` authoritative during an existing
installation update, use the integrated synchronization option. After replacing
the matching release files, run this from the application VM:

```powershell
Set-Location E:\App\PMem
.\install-depo.ps1 `
  -EnvFile 'E:\App\PMem\.env.local' `
  -Profile Production `
  -SkipDependencyInstall `
  -SynchronizeCredentials
```

Use `-SkipDependencyInstall` only when this release's dependencies are already
installed; omit it if requirements or lockfiles changed. The installer migrates
and verifies PostgreSQL, atomically synchronizes the supplied application key
profiles and their metadata, then continues service startup and release checks.
There is no separate credential command to run. `-SynchronizeCredentials` is
an alias for `-ReplaceExistingCredentials` and works with the root launcher too.
Omitted profiles are preserved. Database passwords, Neo4j and Ollama credentials
are not imported as application API-key profiles. Old keys and sessions may stop
working: reconnect in Admin using the selected file's `ADMIN_API_KEY`.
Without this option the installer validates existing profiles and stops on a
mismatch; it does not silently overwrite customer credentials.

The installer migrates PostgreSQL, initializes missing profiles and checks supplied credential keys, actor metadata, expiry and revocation before launching APIs. Existing keys are preserved. Conflicts stop the installation with profile names and reasons; secret values are never printed.

Normal first installation or redeployment, from the application repository root:

```powershell
Set-Location E:\App\PMem
.\install-depo.ps1 -EnvFile 'E:\App\PMem\.env.local' -Profile Production
```

If the reviewed file intentionally replaces the central credentials, stop running services first, then use the explicit option. This rotates all supplied application key profiles and invalidates dependent browser sessions:

```powershell
.\infra\windows\stop-depo-services.ps1 -EnvFile 'E:\App\PMem\.env.local'
.\install-depo.ps1 -EnvFile 'E:\App\PMem\.env.local' -Profile Production -SkipDependencyInstall -ReplaceExistingCredentials
.\infra\windows\test-depo-browser-session.ps1 -EnvFile 'E:\App\PMem\.env.local'
.\infra\windows\start-depo-frontend.ps1 -EnvFile 'E:\App\PMem\.env.local'
```

The installer builds the frontend unless skipped; frontend serving remains an explicit final step. Reconnect in Admin after rotating credentials.

### Optional Ollama proxy with subscription authentication

Put these values in the root `.env.local`, never the frontend environment. Use this example only when the route explicitly requires an APIM subscription. For the custom REST API-key deployment, use the Custom Ollama REST operation section instead. Replace the subscription placeholder with the issued key:

```dotenv
USE_LLM=ollama
USE_EMBEDDER=ollama
# Public APIM root; use HTTPS. This example requires subscription authentication.
OLLAMA_BASE_URL=https://azdtapimanager.azure-api.net/ollama
# Root defaults to POST /api/chat; APIM must expose it.
# OLLAMA_API_URL=https://azdtapimanager.azure-api.net/ollama/api/chat
OLLAMA_API_KEY=<issued-subscription-key>
OLLAMA_API_KEY_HEADER=Ocp-Apim-Subscription-Key
LLM_MODEL_NAME=llama3.1:8b
EMBED_MODEL_NAME=nomic-embed-text:latest
LLM_REQUEST_TIMEOUT_SECONDS=300
COMPANION_LLM_ENABLED=true
ONTOLOGY_AGENT_LLM_ENABLED=true
```

The base URL must preserve the `/ollama` API suffix. Configure APIM operations and backend rewriting for GET `/api/tags`, POST `/api/chat`, POST `/api/generate` and the embedding operations used by the deployed Ollama SDK. The selected models must already exist on the Ollama server. Restart services and use Agent Control's Ollama check; an unexposed `/api/tags` operation prevents that model diagnostic even if chat works. This configuration uses an offline model server behind APIM, rather than a fully disconnected network deployment.


Ollama timeout configuration is consistently bounded to 1–120 seconds for main chat, embeddings and unstructured chat. Unstructured Ollama inherits the main URL/key unless its own overrides are set; its model remains separately configured and must support the requested document/vision operation. Ollama health checks are read-only `/api/tags` probes and do not trigger generation. Agent Control distinguishes authentication rejection, missing route and upstream HTTP failures. The installer now verifies central browser-session authentication automatically after service startup; gateway mode also checks APIM session routing.

### Browser connection after credential synchronization

A successful `test-depo-browser-session.ps1` verifies the services; it does not authenticate the browser.

1. Open the frontend and select **Admin → Service credentials**.
2. In **Administrator key for connection**, enter the current `ADMIN_API_KEY` accepted by the central PostgreSQL credential store.
3. For ontology uploads or workflow execution, select **Enable registered upload, execution and approval scopes for this session**. Leave it unchecked for read-only access.
4. Click **Connect registered services**. Wait for the connected-scopes confirmation. Graph, catalog, data products and observability reads all use the registered read scope.
5. Navigate to Home and refresh data. The delegated session survives refresh in the same tab when session storage is available and expires after fifteen minutes. Raw keys remain memory-only.

Testing `ADMIN_API_KEY` in the individual profile table validates administrator operations only. It does not connect other services. Blank key inputs are intentional after central connection: raw server keys are never returned to the browser. Read-only sessions leave write profiles unavailable.

If connection fails, read the message beneath **Connect registered services**. A credential-change rejection clears the affected browser session and requires reconnection; policy denials do not clear a valid session. Do not rotate database credentials merely because the browser is unsigned-in. Capture the failed request's Response detail in browser Network tools without sharing Authorization headers or keys.

### Deliberately synchronize application keys from the root environment file

To make the application API-key values in the selected file authoritative in PostgreSQL, use `-Synchronize` (an alias for `-ReplaceExisting`). This updates every nonempty supported application profile supplied in that file, including ADMIN_API_KEY, GRAPH_READ_TOKEN, ingestion, execution and approval tokens. Actor and expiry metadata are also applied. Missing or blank profiles preserve their central values; the script lists these omissions. A failed batch rolls back all changes.

From the application repository root, run each command separately and stop on failure:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-services.ps1 -EnvFile 'E:\App\PMem\.env.local'
.\infra\windows\apply-depo-service-credentials.ps1 -EnvFile 'E:\App\PMem\.env.local' -Synchronize
# Continue only after status: ok.
.\infra\windows\start-depo-services.ps1 -EnvFile 'E:\App\PMem\.env.local'
.\infra\windows\test-depo-browser-session.ps1 -EnvFile 'E:\App\PMem\.env.local'
```

Then reconnect in Admin using the synchronized ADMIN_API_KEY. Select workflow scopes when uploads or execution are needed. The PowerShell script cannot sign a browser in. Without `-Synchronize`, the script creates missing profiles and validates existing values, refusing conflicts. Database/Neo4j passwords and Ollama/APIM outbound keys are not application credential profiles and remain in server configuration.

### Ollama API URL, key and models

In the root `.env.local`, configure the API URL, key and model names. Remove OLLAMA_BASE_URL if configuring OLLAMA_API_URL for a different server. The legacy setting remains supported. Keyed Ollama REST APIs default to api-key regardless of hostname. Set OLLAMA_API_KEY_HEADER=Ocp-Apim-Subscription-Key only when the route requires a subscription. Set Authorization for bearer-key authentication. A blank key sends no authentication header.

The supplied `Ollama.openapi.json` declares `http://azdtapimanager.azure-api.net/ollama`, with POST `/api/chat`, `/api/generate`, `/api/embed` and `/v1/chat/completions`; it does not declare GET `/api/tags`. Python clients and the PowerShell diagnostic preserve HTTP or HTTPS as configured. To follow that export, use `OLLAMA_API_URL=http://azdtapimanager.azure-api.net/ollama`, `OLLAMA_CHAT_API_URL=http://azdtapimanager.azure-api.net/ollama/api/chat`, `OLLAMA_API_KEY_HEADER=api-key` and `OLLAMA_DISCOVERY_ENABLED=false`. HTTP sends the configured key without transport encryption. The export documents the contract, not live gateway availability; test POST operations separately. `/ollama-clone` is not the server path in this export.


```dotenv
USE_LLM=ollama
USE_EMBEDDER=ollama
# Server and scheme from the supplied Ollama.openapi.json; POST /api/chat.
OLLAMA_API_URL=http://azdtapimanager.azure-api.net/ollama
# To retain a native generate operation instead, replace the preceding entry:
# OLLAMA_API_URL=http://azdtapimanager.azure-api.net/ollama/api/generate
OLLAMA_CHAT_API_URL=http://azdtapimanager.azure-api.net/ollama/api/chat
OLLAMA_DISCOVERY_ENABLED=false
OLLAMA_API_KEY_HEADER=api-key
OLLAMA_API_KEY=<your-current-api-key>
LLM_MODEL_NAME=llama3:latest
EMBED_MODEL_NAME=nomic-embed-text:latest
ONTOLOGY_AGENT_LLM_ENABLED=true
COMPANION_LLM_ENABLED=true
```

Replace the key placeholder and restart services. The remote server must have the named models installed. OLLAMA_API_URL accepts the API root or full native /api/chat URL. DEPO uses /api/chat for generation, /api/tags for model discovery, and native embedding operations for SDK embeddings. A model-discovery 404 does not verify generation availability; check proxy routing separately. OpenAI-compatible chat-completions APIs use a different protocol and cannot be configured as native Ollama endpoints.

### Refresh and delegated browser authentication

Central API-key records persist in PostgreSQL. A browser uses a separate fifteen-minute delegated session. The frontend restores that opaque session from sessionStorage before initial requests, so same-tab refresh keeps graph, catalog, data-product and observability reads authenticated. Workflow scopes are restored only if granted when connecting. Service URL changes discard the stored session to prevent reuse against a different configured deployment.

Raw ADMIN_API_KEY, individual service API keys and APIM subscription keys are never persisted in browser storage. Restricted browser storage falls back to memory-only operation. A gateway requiring an APIM subscription key therefore requires that key again after refresh. Clear credentials removes the stored delegated session. Expiry, central revocation and credential rotation still require reconnection; no failed write is automatically repeated.

Deploy the updated frontend source and rebuild with npm run build, then restart the frontend using the documented launcher. Connect in Admin once after deployment; refresh the page within fifteen minutes to verify continued access. Do not use the diagnostic's temporary session in the browser: the diagnostic disconnects it when finished.

### Landing-page ontology and graph metrics

Home → Graph profile provides an ontology scope selector and declared counts for classes, object properties, data properties, annotation properties and explicit named individuals. Graph resource and relationship counts are separate: referenced vocabulary and blank nodes are resources, and literal values are retained as node properties. These are complete aggregates for the published RDF projection, not the limited explorer sample. They do not represent reasoner-inferred axioms or unpublished registry artifacts. The per-ontology breakdown displays up to 200 rows; totals still include the complete selected scope.

Deploy matching frontend and graph-service files, rebuild the frontend and restart the graph service. When using a gateway, import the graph service's updated OpenAPI contract so GET /api/v1/graph/metrics is exposed and Authorization is forwarded. Connect through Admin before checking Home. The metrics endpoint accepts ontology_id as an exact registered publication identity and requires GRAPH_READ_TOKEN or its delegated scope.

An unavailable service or rejected credential displays an error, not zero totals. A registered ontology with no published projection legitimately has no published counts; inspect its publication workflow before treating this as missing registry data. Protégé-style inferred axiom counts are not implemented by this projection endpoint.

### Registry, catalog and product-list completeness

Agent workflow controls provide a recent-run picker, distinguish standalone executions from multi-step workflows, and refresh the selected workflow every three seconds while visible. Control requests receive a separate acknowledgement when the executor reaches a tool boundary. Pause/resume/cancel availability and write-reconciliation eligibility come from the same backend heartbeat projection. GET `/api/v1/workflow-runs` must be exposed in the gateway for the picker; owner read access sees its recent runs and agent supervision access can inspect all recent workflows.

Set `AGENTIC_EXECUTION_MODE=worker` with `AUTH_MODE=token` for PostgreSQL-backed queued execution. The manifest starts `backend.agentic_service.worker`, and readiness requires its current worker-mode heartbeat. Queue submissions return a run ID immediately. The worker revalidates credential fingerprints, active PostgreSQL profiles and tool contracts, preserves the original deadline and owner, and uses compare-and-put fencing before execution. It automatically recovers stale read-only interruptions; uncertain writes require reconciliation. Browser credentials and bearer tokens are not saved in queued jobs. Restart both the API and worker after changing configuration. `AGENTIC_EXECUTION_MODE=process` retains in-process execution for deployments using gateway Entra delegation; that mode still needs supervised restart recovery.

Set `AGENTIC_WORKER_CONCURRENCY=4` to allow four active workflows per worker (valid range 1–16). A paused workflow occupies one slot; other available slots continue processing queued runs. The `data-product-governed-publication` workflow previews and publishes an approved product through the existing data-product service.

Ollama proposals use live OpenAPI input schemas and remain review-only. `OLLAMA_PROPOSAL_MODE=structured` is the default; `native` requests exactly one native function call for review and never automatically executes it. Agentic POST `/api/v1/llm/probe` requires agent-supervisor approval (`approved_by` and `approval_token`, or the configured gateway identity). It sends up to three small inference requests to test generation, structured JSON and native function calling separately. Its test function is never executed. Expose this route through APIM; a model-list response does not verify these capabilities.

`OLLAMA_MAX_CONCURRENCY=4` limits concurrent Agentic proposal, ontology-review and companion-generation requests per process and operation endpoint. `OLLAMA_FAILURE_THRESHOLD=3` and `OLLAMA_CIRCUIT_COOLDOWN_SECONDS=30` temporarily reject inference after repeated upstream transport, rate-limit or server failures. These limits are local to each process, not a distributed gateway quota. Legacy sync LLM integrations retain their own transport controls. Set `OLLAMA_REQUIRE_HTTPS=true` after verifying the actual HTTPS gateway operation; it blocks HTTP requests including an explicit chat override. The default remains false for compatibility with the supplied HTTP APIM export. Changing this flag does not create an HTTPS operation in APIM.

Ontology recommendations now receive a bounded sample of inspected terms and candidate-validation evidence. Structured review questions must cite supplied IRIs, and unsupported citations or extra approval fields are rejected. These questions do not prove ontology consistency or semantic equivalence; formal reasoning remains a separate validation step. Non-streaming inference logs include model, elapsed time and available token counts without prompts, evidence, answers or credentials. Automated contract checks cover schema validation, grounding, unknown tools, HTTPS policy, concurrency and circuit behavior; customer-data semantic accuracy and live gateway capability must still be evaluated before enabling native proposals.

For uncertain product publication or Semantic Bridge publication, **Verify downstream receipt automatically** performs a read-only receipt lookup and verifies the saved request identity and artifact/selection evidence. A missing or mismatched receipt never authorizes replay. Other tools still require explicit downstream evidence. Terminal workflows can show **Review reversible operations**: completed product-publication steps can be compensated through steward-approved product revocation with a stable request ID and a required reason. This retains packages and audit history and delivers revocation to the catalog through the outbox. Operations without a supported inverse are listed explicitly; graph writes are never deleted speculatively. A compensated workflow cannot resume with obsolete step outputs.

Update APIM from the deployed Agentic OpenAPI so it exposes POST `/api/v1/workflow-runs/{run_id}/reconcile-receipt`, GET `/api/v1/workflow-runs/{run_id}/compensation-plan` and POST `/api/v1/workflow-runs/{run_id}/compensate`, in addition to the existing workflow controls and run-list route. Restart the API and workers after deploying these files; existing processes retain their loaded code and configuration.

Admin, Data Catalog and Data Products use the shared product collection reader, with 15-second visible-page refresh and bounded pagination. Product publication triggers an immediate collection refresh. Catalog headings distinguish the API total from loaded rows; partial retrieval remains visible. Retained packages awaiting catalog registration are identified separately from registered catalog versions.

In Data Flow, select a completed run with retained output artifacts and choose **Create product from retained run evidence**. Data Products reloads that run through the pipeline API, retains its artifact references and run lineage, and uses the same preview/publication service as schema-design drafts. The steward must enter an approved semantic release and validate the publication contract before publishing. This packages review evidence; it does not automatically certify quality or publish graph data. Failed or unfinished runs and runs without retained output references cannot supply this draft.

The landing-page ontology registry merges the native ontology catalog and the ingestion registry by immutable identity. If only one source responds, its rows remain usable and a Partial ontology list warning identifies the unavailable source. Retry registries to verify completeness. If both fail, the UI reports a load error instead of claiming the registry is empty. Schema-design drafts on Data Products show the same ontology-source warning.

Data Products follows explicit service pagination rather than assuming the first 100 records are the complete list. Deploy matching backend and frontend files to enable this behavior. An older capped endpoint without pagination metadata shows a completeness warning. Catalog and product detail requests have explicit timeouts; malformed payloads, authorization errors and transport failures are shown as errors, not as successful empty lists. Catalog ordering tolerates historical records without updated_at.

### Check existing configuration after upgrading

For an already installed application, run this read-only audit from the repository root before installation or restart:

```powershell
Set-Location E:\App\PMem
.\configure-depo.ps1 -CheckExisting
```

It reports settings absent from the server or frontend environment file and rejects conflicting populated VITE_/REACT_APP_ aliases. It preserves both files, hides values and does not generate or synchronize keys. Review missing settings against config/deployment.env.example and frontend/.env.example. The ordinary generator does not upgrade existing files; do not use -Force to update customer settings.

Server setting changes require backend restart. Browser build settings require rebuilding the frontend. Runtime routing changes require restarting the frontend launcher. Central application-key replacements require deliberate synchronization and browser reconnection. Database migration remains an installation/startup schema step; this audit does not run it. Gateway verification uses DEPO_ROUTING_MODE=gateway. New frontend configurations leave the Agentic URL empty for centrally resolved routing and use a one-minute default request timeout. If an older generated file contains LLM_REQUEST_TIMEOUT_SECONDS twice, retain one entry with the intended value before retrying the audit.

### Analytics evidence: deployment checkpoints and publication

Use this sequence after updating an existing installation or completing the first installation. Schema design evidence contains an entity/column/relationship model and review-only SQL. It does not create or load customer fact/dimension tables. Business grain, KPI formulas, units and history policies require an approved definition before warehouse implementation.

1. Deploy matching backend and frontend files. Run the existing schema initialization and service-start sequence earlier in this guide. Rebuild the frontend after updating React files. Existing product/catalog records remain intact.
   For an existing installation with dependencies already installed, stop the application before replacing files, then run these commands from the repository root. Migration 009 adds the product, catalog and job pagination indexes. The schema verifier now checks their definitions and validity. Do not alter earlier migration files.

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
.\infra\windows\stop-depo-services.ps1
# Copy the reviewed release files into this repository directory now.
.\infra\postgres\update-postgres-schema.ps1 -EnvFile .\.env.local
.\infra\windows\build-depo-frontend.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .\.env.local
```

   Stop if a command reports failure. A first installation must use the prerequisite and dependency installation sequence earlier in this guide before these checks.
2. From the repository root on the application VM, run the read-only checks below. Replace the example repository directory if yours differs.

```powershell
Set-Location E:\App\PMem
.\infra\windows\test-depo-analytics-services.ps1 -EnvFile .\.env.local -RequireWorker
```

For gateway routing, use the same selected environment file and add `-Gateway`:

```powershell
.\infra\windows\test-depo-analytics-services.ps1 -EnvFile .\.env.local -Gateway -RequireWorker
```

Checkpoint: PostgreSQL verification and all three protected list APIs pass. Empty lists are valid for a new installation. The worker check confirms execution readiness, not successful execution of a customer job. If the read key differs from the central credential store, follow the deliberate synchronization/rotation procedure in this guide. Do not disable authentication to hide the failure.

3. In **Admin**, connect the central browser session with write access, or test and apply `INGESTION_WRITE_TOKEN` and `DATA_PRODUCT_APPROVAL_TOKEN`. Keys stay out of the frontend build and product package.
4. Open **Data Products**. Select an imported schema under **Schema design drafts**. For a multi-file XSD, expand **Inspect an XSD with dependency files**, select the root XSD and dependency files, and enter one relative path per dependency in the displayed order. Example: root `QIFDocument.xsd`, dependency `types/Part.xsd` referenced by `schemaLocation="types/Part.xsd"`. Select **Inspect schema set**. Paths must match the XSD include/import references, remain inside the schema set and use `.xsd`. The closure has a 63-dependency/25-MiB limit. Remote downloads and parent-directory traversal are rejected.
5. Review the resulting blockers and retained draft. A blocked structural model is evidence for review, not an executable schema. Publishing a design-evidence product does not waive those blockers.
6. Complete product ID, name, new semantic version, owner, steward, classification and approver. Enter an existing **approved semantic asset ID and release version** from Metadata Registry. An imported ontology alone is not proof of an approved semantic release.
7. Select **Validate publication contract**. This validates fields and retained references. The publication service checks the authoritative approved release when publishing.
8. Select **Approve and publish evidence**. Check its delivery receipt. `published` means catalog registration completed. `pending_catalog_registration` means the retained package and approved product await the outbox worker. Use the existing retry-catalog endpoint to reconcile delivery, rather than publishing a changed payload for the same version.
9. Refresh **Data Catalog**, inspect the same product/version, and verify the manifest retains `product_kind=schema-design-evidence` and `analytics_readiness=requires_materialization_and_business_definition`.

#### API contracts and safe retries

The ingestion endpoint is `POST /api/v1/schema-conversions/inspect`. Multipart fields:

| Field | Meaning |
| --- | --- |
| `file` | Root XSD or another supported engineering source |
| `dependencies` | Repeated dependency XSD uploads |
| `dependency_paths` | JSON array of relative paths in upload order, e.g. `["types/Part.xsd"]` |

A governed `schema-analytics-product` job accepts a retained root source and optional retained dependency map. For example, submit the following input to `POST /api/v1/pipeline/jobs/definitions/{job_id}/{version}/run` after that job version is approved and enabled. Replace the artifact IDs with IDs returned by inspection. Authorization uses `DATA_JOB_EXECUTION_TOKEN` or the corresponding delegated browser scope.

```json
{
  "artifact_id": "sha256:<root-source-digest>",
  "schema_dependencies": { "types/Part.xsd": "sha256:<dependency-source-digest>" },
  "approved_by": "engineering-operator"
}
```

The worker reconstructs the local dependency closure from retained artifacts. The resulting durable output manifest preserves product kind, analytics readiness, domain and artifact references. It never executes the review-only SQL.

`POST /api/v1/data-products/preview` and `/publish` accept artifact objects such as `{"artifact_id":"sha256:..."}`. Publication requires `lifecycle_state="published"`, a safe product ID, semantic version, ownership fields, approved semantic-release references and an approver. The browser supplies the appropriate credential in the header, not in the package.

Product versions are immutable even while catalog delivery is pending. Keep the same idempotency key and exact payload after an uncertain response. A changed payload with that key returns HTTP 409. Use a new version for deliberate content changes. Product state and its approval evidence commit together in PostgreSQL. Filesystem package creation precedes that transaction, so an interrupted request may leave an immutable package that the identical retry can recover.

Older ZIP manifests without `publication_digest` cannot prove retry identity. Download and retain their evidence, inspect the existing product record, and publish reviewed changes under a new version. Do not delete published packages or rewrite migration history to bypass this check.

List APIs now accept `limit` and `offset`, and return `total`, `limit`, `offset` and nullable `next_offset`: `/api/v1/data-products`, `/api/v1/catalog/products` and `/api/v1/pipeline/jobs/runs`. Catalog additionally accepts `domain`. Follow `next_offset` until null. Concurrent changes between pages can affect completeness; refresh before treating the results as a fixed audit snapshot.

Approved-release checks call the configured `SEMANTIC_REGISTRY_URL` with the server `GRAPH_READ_TOKEN`. For APIM, the configured gateway subscription header also applies. Preserve Authorization forwarding on that route. API 401/403 indicates authorization failure, 409 indicates immutable-content/concurrency conflict, 422 indicates invalid contract or release evidence, and 503 indicates a required service/control plane is unavailable. These are different from an empty successful list.

### Schema evidence publication recovery checkpoints

Upload a root XSD using a plain filename (for example `QIFDocument.xsd`). Supply included/imported XSD files using their relative schema locations, such as `types/Part.xsd`. Both OWL conversion and the analytics structural report use this schema set. Paths outside the uploaded set are rejected.

If publication returns a validation or authorization rejection, correct the fields or reconnect in Admin, then validate the contract again. For a timeout or server failure, use **Retry same publication**: the request identity and payload remain unchanged until the outcome is known.

Recovery verifies the existing ZIP, its manifest, member list and artifact checksums. A corrupt package is rejected; restore the original package from backup before retrying. Do not delete an existing customer product version to bypass this check.

### Data-job recovery and update checkpoints

`retry_policy.max_attempts` bounds both normal retries and execution after a worker crash. An expired lease increments the attempt when reclaimed. When the limit has already been consumed, the worker records failure without running the handler again. Inspect retained results and external effects before requesting explicit replay. Telemetry write failures do not discard a claimed run.

Schema analytics jobs accept a maximum of 25 MiB for the root schema and its dependency closure. The worker checks sizes before reading, then uses a bounded read. Larger schemas require a separately reviewed processing path. RDF reports return the full distinct-predicate count while charts list only the top 50 predicates.

For an existing installation, retain the existing environment file and central keys. Stop the frontend and backend before replacing application files. From the repository root, after copying the matching release files, run:

```powershell
Set-Location E:\App\PMem
.\install-depo.ps1 -EnvFile .\.env.local -Profile Production -SkipDependencyInstall
.\infra\windows\start-depo-frontend.ps1 -EnvFile .\.env.local
.\infra\windows\test-depo-analytics-services.ps1 -EnvFile .\.env.local -RequireWorker
```

`-SkipDependencyInstall` preserves installed packages and still rebuilds the frontend. Use it only when the release dependency locks have not changed. If they changed, omit the switch. `-SkipFrontend` explicitly omits frontend installation and build. A missing dependency or failed build stops installation before service startup.

The root installer accepts `-ReplaceExistingCredentials` for deliberate replacement of central keys from the selected file. Existing keys remain unchanged by default. Use that switch only after reviewing the intended replacements, then reconnect browser sessions in Admin. Successful read-only analytics checks confirm authorization, pagination and worker readiness. Verify one approved job through completion and inspect its retained output before customer acceptance.

### Custom Ollama REST operation

For a custom endpoint exposing native Ollama generation, retain the operation and select custom-key authentication:

```dotenv
USE_LLM=ollama
# Root retains the APIM API suffix. The operation belongs in OLLAMA_API_URL.
OLLAMA_BASE_URL=https://azdtapimanager.azure-api.net/ollama
# Native generation operation; sends model, prompt and optional system fields.
OLLAMA_API_URL=https://azdtapimanager.azure-api.net/ollama/api/generate
# Optional tool-chat route, only after verifying APIM exposes POST /api/chat:
# OLLAMA_CHAT_API_URL=https://azdtapimanager.azure-api.net/ollama/api/chat
# Discovery separately calls GET https://azdtapimanager.azure-api.net/ollama/api/tags.
# A missing tags route does not establish whether generation works.
OLLAMA_API_KEY=<existing-custom-api-key>
OLLAMA_API_KEY_HEADER=api-key
LLM_MODEL_NAME=llama3:latest
EMBED_MODEL_NAME=nomic-embed-text:latest
ONTOLOGY_AGENT_LLM_ENABLED=true
COMPANION_LLM_ENABLED=true
```

Use the model actually installed on the server. Companion and ontology LLM initialization select `/api/generate` for that explicit operation. A root URL defaults to `/api/chat`. Model discovery uses `/api/tags`; a 404 leaves generation unverified. Embeddings separately require a compatible embedding route. The gateway must accept the configured header. Code cannot remove an upstream subscription requirement.

Deploy the updated files to the customer VM, apply these entries to its existing root `.env.local` without duplicates, then stop and start backend services using `manage-depo.ps1`. Ollama keys are outside the PostgreSQL application-key store. No frontend rebuild is required for these server settings alone.

### Ollama generation and tool-chat capability

Run the PowerShell diagnostic on the application VM using the same environment
file as the services. It prints routes, status and model availability without
printing keys or upstream response bodies. Remote keyed URLs must use HTTPS.
Run the saved `.ps1` file; do not paste its contents line by line at the console.
`$PSScriptRoot` is supplied when PowerShell executes a saved script. Keep
`runtime-config.ps1` beside it in `infra\windows`.

```powershell
Set-Location 'E:\App\PMem'
# Read-only model-list check:
.\infra\windows\test-depo-ollama.ps1 -EnvFile .\.env.local
# Also send a small prompt to the configured /api/generate or /api/chat operation:
.\infra\windows\test-depo-ollama.ps1 -EnvFile .\.env.local -ProbeGeneration -TimeoutSeconds 60
# Optional separate native chat completion test (does not verify tool calls):
.\infra\windows\test-depo-ollama.ps1 -EnvFile .\.env.local -ProbeGeneration -ProbeChat -TimeoutSeconds 60
```

Discovery and generation are tested independently. A model-list 404 remains a
failed diagnostic even when generation succeeds; repair APIM's tags route to
make the application readiness check pass. The script does not edit `.env.local`,
register APIM operations, install models or restart services.

These URLs illustrate the native routes for the APIM suffix used in the
examples. They have not been verified against the live gateway. Import or
repair the corresponding operations before expecting the checks to pass.

| Setting or check | Example URL | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `https://azdtapimanager.azure-api.net/ollama` | API root without an operation suffix |
| `OLLAMA_API_URL` for generate | `https://azdtapimanager.azure-api.net/ollama/api/generate` | Native POST text generation |
| `OLLAMA_API_URL` for chat | `https://azdtapimanager.azure-api.net/ollama/api/chat` | Alternative native POST chat generation |
| `OLLAMA_CHAT_API_URL` | `https://azdtapimanager.azure-api.net/ollama/api/chat` | Optional native POST tool-chat route |
| Derived model-list check | `https://azdtapimanager.azure-api.net/ollama/api/tags` | GET installed models; not a generation URL |

Choose one generation operation. Update existing entries instead of appending
duplicates. The local default in `config/deployment.env.example` remains
`http://127.0.0.1:11434`; its commented APIM examples show the alternative.
Use the server's exact installed model name, such as `llama3:latest`. The model
name is a request field, not part of the URL. See
[Ollama APIM setup](../../infra/azure-apim/README.md#ollama-model-discovery-and-generation)
and the supplied [OpenAPI contract](../../infra/azure-apim/ollama.openapi.json).

Companion summaries and ontology review suggestions can use native `/api/generate`. Tool-calling chat uses a separate `ChatOllama` client and requires native `/api/chat` plus a model supporting tool calls. A generate-only endpoint does not provide that capability. If the proxy exposes chat separately, configure `OLLAMA_CHAT_API_URL` with its API root or full `/api/chat` URL. Leave it blank when chat is unavailable. Text generation remains usable while tool workflows report unavailable. Never point the chat setting to `/api/generate`.

Unstructured Ollama initialization preserves an explicit generation operation, including inherited main configuration. Its model is independent. Image/vision use cases require a compatible multimodal model and request contract; text-generation configuration alone does not verify vision support. Embeddings require their own native embedding route.

Authentication selection: `api-key` is the custom REST default. `Authorization` sends a bearer key. `Ocp-Apim-Subscription-Key` applies only to the optional subscription-authenticated example. Neither a hostname nor the DEPO routing switch selects the Ollama authentication contract. The gateway must accept the selected header.


### Agent role architecture

### Session persistence and lifecycle

#### Browser access and durable Companion conversations

Access delegation and conversation persistence have separate lifetimes. In Admin, select the required scopes and use **Connect registered services** once. The browser receives an opaque delegated session; raw administrator and service keys are not saved in browser storage. Same-tab refresh restores that delegation and the Companion conversation ID. The Companion restores the latest 20 completed turns from PostgreSQL after verifying conversation ownership. Neo4j agent memory is optional for this history restoration.

Add these optional settings to the repository-root `.env.local`, then restart backend services and rebuild the frontend:

```dotenv
# Access expires after at most 15 minutes without renewal.
DEPO_BROWSER_SESSION_IDLE_SECONDS=900
# Active users can renew until this fixed sign-in deadline (8 hours).
DEPO_BROWSER_SESSION_MAX_SECONDS=28800
AGENTIC_MAX_PROMPT_BYTES=262144
# A conversation becomes idle after 30 minutes; its owner can resume it.
AGENT_SESSION_IDLE_SECONDS=1800
# Conversation identity remains resumable for 24 hours from creation.
AGENT_SESSION_MAX_SECONDS=86400
# Completed turn retention is independent of access-token expiry.
AGENT_MEMORY_RETENTION_DAYS=30
```

The browser attempts renewal shortly before access expiry only when recent keyboard or pointer activity occurred. Activity near expiry also retries a skipped or failed renewal, with a ten-second minimum between attempts. Background polling alone does not extend sign-in. Renewal uses `POST /auth/browser-session/renew`, validates current PostgreSQL credential snapshots, preserves the originally granted scopes and never moves the absolute sign-in deadline. Logout, revocation, key rotation and expiry prevent further use. A failed network renewal never automatically retries a write. Admin reconnect replaces delegated access without firing sign-out or deleting the conversation bookmark; the server verifies ownership again before restoring history.

`AGENTIC_MAX_PROMPT_BYTES` bounds UTF-8 prompt payloads sent to the model (default 256 KiB; accepted range 16 KiB–1 MiB). Oversized evidence is rejected rather than silently truncated. Companion streaming honors the validated frontend `VITE_CHAT_STREAM_TIMEOUT` setting, in milliseconds, including values above five minutes. Configure gateway timeouts to accommodate the chosen request budget.

On access expiry, reconnect in Admin to resume the bookmarked conversation. On explicit sign-out, browser credentials and conversation bookmarks are cleared; retained server history remains subject to retention. Closing the tab clears same-tab persistence. Existing delegations created before this release require one new Admin connection to obtain renewable-session metadata.

If Azure API Management is enabled, import the updated OpenAPI contracts and expose `POST /auth/browser-session/renew` on the ontology API. Forward the bearer Authorization header. The agentic API also exposes `GET /api/v1/chat/sessions/{session_id}/history`; it verifies the requesting owner before returning completed turns. No PostgreSQL migration is required for these additions: they use the existing registry and retained Companion job records.

#### Runtime cleanup settings

After deploying these lifecycle changes, stop and start the backend services once to activate the cooperative Windows runtime:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-services.ps1
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
```

Workers stop before APIs. Newly launched processes receive a local stop request and drain through their existing SIGINT handlers. The stop helper waits 60 seconds before forced termination; old processes without the cooperative runtime retain the force-stop behavior. A forced stop cannot undo writes: reconcile interrupted runs before retrying mutations.

Optional settings in the repository-root `.env.local` (restart services after changing them):

```dotenv
DEPO_AGENT_MAINTENANCE_SECONDS=300
DEPO_AGENT_SHUTDOWN_SECONDS=30
DEPO_SCHEDULER_POLL_SECONDS=10
DEPO_SCHEDULER_SHUTDOWN_SECONDS=30
DEPO_READINESS_TIMEOUT_SECONDS=3
GRAPHVIS_CACHE_TTL_SECONDS=60
CHAT_CONTEXT_MESSAGE_LIMIT=5
```

The scheduler retains tracking if it cannot finish within its shutdown timeout and does not stop Spark beneath an active scheduler. Maintenance failures are isolated by cleanup operation. Browser delegation renewal preserves Companion ownership for the same server-assigned actor; different actors remain isolated. Legacy chat context defaults to five messages and can be increased up to `CHAT_SESSION_MESSAGE_LIMIT`.

For long-running jobs, set `$env:DEPO_SHUTDOWN_GRACE_SECONDS = '120'` in the PowerShell session before running the stop script (accepted range: 5–600 seconds). Set a value longer than the application drain time. Do not share actors between users who require separate conversation histories.

See [Agent architecture and use of the 26 roles](../../docs/AGENT_TOOL_MAPPING.md) for the runtime role/tool mapping, workflow handoffs, mutation recovery and deployment boundaries. Approved mutating `/runs` requests use retained workflows; `wait_for_completion=false` returns a queued workflow ID in worker mode. Sync REST and LangChain Ollama calls use the shared per-process admission and circuit policy. These controls do not constitute live APIM capability verification.


### ReqIF update and verification

Deploy the ingestion, CEIM and graph backend files together with the rebuilt frontend. Restart the services after deploying. No PostgreSQL migration is introduced by this ReqIF update.

In Admin, connect service credentials. Open Import, select Import instance graph, then attach a `.reqif` or `.reqifz` source. ReqIFZ must contain exactly one ReqIF document; attachments are retained in the original archive. Multiple ReqIF documents must be imported separately. The governed import requires an approved and enabled data-job definition. Completion of normalization or validation alone does not publish the graph: complete the governed publication step before checking the ReqIF page.

The ReqIF page provides Previous and Next controls. Search and CSV export apply to the displayed page. Invalid identifiers, duplicate identifiers, unresolved requirement references, DTD/entity declarations and oversized archives stop import with an error. Full requirement text is preserved. Validation currently covers XML structure, identifiers and references; it does not certify compliance against the complete ReqIF XSD. Source files remain retained evidence; CSV is not a round-trip ReqIF export.


### XMI and SysML update checkpoints

Deploy ingestion, ontology conversion and graph service updates together with the rebuilt frontend, then restart the services. No PostgreSQL migration is introduced by these parser fixes.

For model instances, open Import, explicitly select Import instance graph and attach `.xmi` or `.mdxml`. These files use the governed SysML v1 adapter and require an approved data job. For ontology creation, select Create ontology instead; do not treat ontology conversion as instance-job execution. SysML v2 repository import continues to use the configured project and immutable commit.

Verify comments are accepted, duplicate IDs and unresolved cross-file references show errors, and the MBSE filter on the ReqIF page includes published SysML v1/v2 requirements. Cross-file references require a model resolver, which standalone import does not provide; they are rejected instead of being linked to a same-named local ID. Multiplicity values are preserved as source evidence; full SysML/KerML semantic compilation is not provided. Native `.sysml`/`.kerml` text parsing remains unsupported.


XMI ontology identity update: generated node and reference URIs now encode the original identifier instead of replacing punctuation with underscores. This prevents distinct model IDs from merging. Existing retained ontologies are not rewritten automatically. Generate and review a new ontology version from the original XMI source, then publish it through the normal approval flow. References to changed generated URIs must be reviewed when switching versions.
# Optional MBSE plugin: execution credentials and readiness

Install this optional component after the main DEPO services are ready and the
root `.env.local` keys match the PostgreSQL credential store. It uses a separate
runtime. From PowerShell, replace the example ingestion IP with your actual service:

```powershell
Set-Location E:\App\PMem
powershell -NoProfile -ExecutionPolicy Bypass -File .\plugins\mbse_plugin\scripts\manage-plugin.ps1 -Action Install
powershell -NoProfile -ExecutionPolicy Bypass -File .\plugins\mbse_plugin\scripts\manage-plugin.ps1 -Action Configure -EnvFile E:\App\PMem\.env.local -IngestionUrl http://10.0.2.16:8014/api/v1
powershell -NoProfile -ExecutionPolicy Bypass -File .\plugins\mbse_plugin\scripts\manage-plugin.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\plugins\mbse_plugin\scripts\manage-plugin.ps1 -Action Verify
```

Stop at the first failure. Start confirms local authenticated readiness; Verify
checks the upstream `DATA_JOB_EXECUTION_TOKEN` without submitting a job. Governed
imports still require an approved job/version and return a durable run ID.
After central key rotation, use Stop, then `-Action SyncCredentials -EnvFile
E:\App\PMem\.env.local`, then Start and Verify. SyncCredentials does not change
PostgreSQL keys. Protect `plugins/mbse_plugin/.runtime/config.json`, which holds
plaintext service credentials. The plugin binds to loopback; gateway exposure is
configured separately. See `plugins/mbse_plugin/README.md` for exact sync commands
and the offline SMW/Cameo capability boundaries.


### AP242 mapping upgrade checkpoint

The AP242 CEIM mapping pack is version `0.2.0`. After deploying this release, review and approve the AP242 data-job definition against the new mapping version/digest before importing again. Existing normalized batches retain their old mapping evidence; regenerate them from the retained source rather than editing provenance or bypassing approval. No PostgreSQL schema migration is required for this mapping-pack change.

Dimensions now retain `lower_tolerance` and `upper_tolerance` as offsets; these are not absolute `lower_limit`/`upper_limit` values. Consumers must use a resolved nominal value and compatible units before calculating absolute limits. Supported referenced SI and conversion-based units are retained; an empty unit means unresolved, not an implicit millimetre. Assembly HAS_PART relationships follow the relating product definition to the related product definition, with occurrence evidence retained.

Malformed records, duplicate identifiers, non-finite numbers, unresolved Part-28 references and empty governed semantic imports are rejected. Full XSD/Schematron/CAD conformance validation and Part-21-to-Part-28 conversion remain outside the implemented extraction boundary. Set `AP242_REFERENCE_ROOT` explicitly when using reference-repository diagnostics; there is no developer-machine path fallback.

### Generated Turtle cache on installation and upgrade

Generated OWL/Turtle cache files are stored under `ARTIFACT_STORAGE\ttl_cache`.
For `ARTIFACT_STORAGE=C:\DEPO\data\artifacts`, this is
`C:\DEPO\data\artifacts\ttl_cache`. All services must use the same durable
storage configuration and their service account needs read/write permission.
The local development default is `data\artifacts\ttl_cache` under the repository.

Older releases wrote to `backend\ttl_cache`. The new service can read that
location when the durable cache has no matching task. Before replacing an old
installation, retain its TTL files. Copy them on the application VM without
replacing newer durable files (example from the repository root):

```powershell
$source = 'E:\App\PMem\backend\ttl_cache'
$destination = 'C:\DEPO\data\artifacts\ttl_cache'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
if (Test-Path -LiteralPath $source) {
    Get-ChildItem -LiteralPath $source -Filter '*.ttl' -File | ForEach-Object {
        $target = Join-Path $destination $_.Name
        if (-not (Test-Path -LiteralPath $target)) {
            Copy-Item -LiteralPath $_.FullName -Destination $target
        }
    }
}
```

Use the destination matching your actual `ARTIFACT_STORAGE`; restart services
with that configuration. Verify retrieval of an existing generated ontology
before removing legacy copies. No PostgreSQL migration is required for this
cache-path change. Cache write failures now fail the operation rather than
reporting success while losing its generated output.

## Registry and data-product upgrade sequence

New installations apply migration `010_credential_integrity.sql` automatically
through the installer. Existing installations must apply it before starting this
release. Migrations 001-009 have not been changed. Migration 010 adds validated,
named credential checks and restores credential defaults. Invalid existing rows
cause the migration to roll back; review the reported constraint with your DBA
rather than deleting credential records or bypassing validation.

For an existing Windows installation, after placing the new release files:

1. Back up the database and package storage according to your customer procedure.
2. In root `.env.local`, preserve any existing `DATA_PRODUCT_STORAGE`. If the old
   release used its default package directory, set this explicitly before restart:

```dotenv
DATA_PRODUCT_STORAGE=E:\App\PMem\data\products
```

Do not move retained packages without a coordinated update to their PostgreSQL
storage references. Existing product records keep their stored download paths.
For a new customer, the default is `ARTIFACT_STORAGE\products`; for example,
`ARTIFACT_STORAGE=C:\DEPO\data\artifacts` creates packages under
`C:\DEPO\data\artifacts\products\packages`. The service account needs read/write
access and this directory must survive application redeployment. Alternatively,
set `DATA_PRODUCT_STORAGE=C:\DEPO\data\products` to select a separate durable root.

3. From the application VM, run the following commands in order. Stop at any error:

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-frontend.ps1
.\infra\windows\stop-depo-services.ps1 -EnvFile .\.env.local
.\infra\postgres\update-postgres-schema.ps1 -EnvFile .\.env.local
.\infra\postgres\test-postgres-schema.ps1 -EnvFile .\.env.local
.\infra\windows\build-depo-frontend.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
.\infra\windows\start-depo-frontend.ps1 -EnvFile .\.env.local
```

4. Reconnect in Admin. Check **Services & catalogs** against your configured
   local VM or gateway URLs. A configured row is not proof of a healthy service.
   **Agents & workflows** and the registry summary now use the same validated
   agent definitions as execution. Invalid catalogs fail agent readiness.
5. Use **Import OpenAPI JSON** for a local metadata preview (OpenAPI 3.0/3.1,
   maximum 5 MiB). It does not execute operations, trust imported server URLs,
   install tools or import secrets. Use the existing service-contract import in
   **API access** to discover credential profiles for configured service roots.
6. Open a retained data product and verify its package download. New catalog
   registrations reject credential fields; existing nested credential fields
   are omitted from read responses. This redaction does not erase old database
   contents: a DBA must review any previously stored sensitive metadata.


### Browser session recovery and service availability

Admin connection creates a bounded delegated session. In gateway deployments, its APIM subscription key is retained with that session in browser sessionStorage for same-tab refresh. Raw application API keys remain memory-only. Disconnect clears the stored session and gateway key; session expiry removes the stored bundle. Use the customer reverse proxy when browser-readable gateway credentials are prohibited.

Unavailable service probes are reported in Admin while healthy services remain usable. Authentication rejections still prevent connection. Renewal retries transient failures every 10 seconds while the session remains valid and recently active. It never extends an expired session. Credential changes cancel pending API-client requests and discard late responses; cancelling a browser request does not undo server writes. Inspect the retained run before retrying a write.


### Existing environment files missing deployment settings

From the repository root run ` .\configure-depo.ps1 -CheckExisting` to list missing settings without changing values. Compare the root file with `config/deployment.env.example`. Do not use `-Force` to repair an existing customer file: it replaces configuration and can generate different keys. Complete the database URL, application host, allowed origins, durable artifact path and application keys using customer-approved values, then run `.\infra\deployment\test-depo-deployment.ps1 -EnvFile .\.env.local -Profile Production -SkipEndpointChecks`. No services need to be running for this configuration check.


### Update an existing configuration without replacing customer values

Run these commands in PowerShell on the application VM. The first command selects the repository folder; adjust `E:\App\PMem` if your installation uses another location.

```powershell
Set-Location E:\App\PMem
.\configure-depo.ps1 -UpdateMissing
.\configure-depo.ps1 -CheckExisting
```

`-UpdateMissing` appends settings absent from the current server and frontend files. It preserves existing values, recognizes frontend aliases and the Ollama API URL, and does not generate or rotate credentials. It requires the existing root `.env.local`; if the frontend file is missing, it creates `frontend/.env.local` from the current template settings. It cannot discover customer database addresses, application roles, passwords, public service addresses or allowed browser origins. Complete any customer placeholders in the root `.env.local` using your actual infrastructure values before continuing.

```powershell
.\diagnose-depo.ps1 -Phase Prerequisites
```

After the configuration and dependencies are ready, follow the installation or redeployment sequence above. Live endpoint validation fetches the running services' OpenAPI documents and rejects JSON object bodies without named fields or an explicitly documented dynamic-record contract. A static API inventory or a passing schema test does not certify database connectivity or successful CRUD workflows.

### JSON API request fields after this update

The ontology, graph, agent, catalog, product, CEIM, pipeline, modeling, ingestion and OSLC JSON bodies now have named request schemas. Inspect `/openapi.json` on the service owning the operation to see its field names, required fields and types. Send JSON booleans such as `false`, not strings such as `"false"`. Omitted optional settings retain the existing service defaults. Source records and job/tool extension inputs remain dynamic where their selected profile or operation defines the fields; approval, policy and downstream validation still apply.
# Loaded ontology reports and OSLC coverage

After starting the services and connecting API access in Admin, open Reports and choose a registered ontology in **Report ontology**. Choose the actual loaded QIF, AP242 or ReqIF ontology; these standards are not separate hardcoded report populations. Click **Refresh reports** after importing or publishing changes.

The **Loaded ontology — OSLC coverage** panel reads `GET /api/v1/graph/ontology-report/{ontology_id}` from the graph service using the existing graph read credential or central browser session. An API gateway must forward this route and authentication to the graph service, alongside its existing graph routes. Deploy the updated backend, rebuild the frontend and restart the services when adding this endpoint.

The panel counts all matching graph records, outgoing links (including links to other ontologies), and RM/AM/CM/QM classifications using the same metadata rules as OSLC queries. Categories can overlap; do not sum them as a distinct total. Unclassified records are shown separately and are not automatically invalid. An uploaded schema without published graph records can legitimately show zero records. These counts do not establish inspection results, requirements compliance or manufacturing outcomes. Pipeline telemetry elsewhere on Reports remains system-wide.

If the panel reports unavailable data, verify Admin API access, the registered ontology and graph service connectivity. A missing gateway route or an older graph service also makes this panel unavailable; it does not mean the ontology contains zero records.


## Current environment configuration reference

### Admin maintenance controls

In Admin → API access, enter the current administrator key and select **Enable Admin maintenance for this session**, then connect registered services. Read-only access alone does not authorize cleanup. Maintenance buttons remain disabled until this scope is connected. **Delete Old XSD Schemas** separately requires ingestion write access through workflow scopes or the registered ingestion key.

**Clear Cache** invalidates application caches without deleting graph data. **Reset Graph Only** deletes graph data and recreates indexes and required publication constraints while retaining uploaded files. Partial registry reconciliation is displayed as a warning after reset; inspect service logs before republishing. **Full Schema Cleanup** also removes indexes, constraints and legacy ontology upload metadata. After full cleanup, run from the repository root before publishing again:

```powershell
.\infra\windows\test-depo-neo4j.ps1 -EnvFile .\.env.local -Bootstrap
.\infra\windows\test-depo-neo4j.ps1 -EnvFile .\.env.local -Production
```

Use the configured Neo4j database and a role permitted to create schema. Cleanup targets that database; do not execute a destructive reset merely to test connectivity. An error from schema creation or PostgreSQL reconciliation must be corrected before treating the operation as complete.

For current `.env.local` ownership, copy-and-paste update commands, central credential synchronization and Ollama REST settings, use the [environment configuration reference](../../deliverables/DEPO_Environment_Configuration_Reference.md#applying-environment-configuration-in-sequence). Use the selected root server file consistently; never copy its secrets into public frontend variables.

QIF XSD conversion expands local model groups and attribute groups before OWL
translation. Attribute-group cycles and unresolved references fail explicitly;
required/optional attribute declarations remain available to the translator.
Deploy the updated backend/Services/xsd_semantics.py and restart ingestion after
this source update. A successful source XSD compile does not certify all generated
OWL/SHACL constraints or downstream registration/publication.

### Optional advanced XSD folder upload with automatic companion paths

Use Import -> Create ontology -> Select complete XSD folder. For QIF select
`E:\App\PMem\docs\xsd`, including both QIFApplications and QIFLibrary. Choose
`QIFApplications/QIFProduct.xsd` under Root schema, then click Check folder and
add root. The browser checks the dependency closure, prepares the root in memory,
and fills companion paths automatically. Complete the ontology metadata, choose
OWL, and start registration. Do not queue each companion as its own ontology.
Missing files, external references, invalid XML and folder escapes are reported
before upload. This preflight does not certify all OWL conversion semantics or
service availability; registration and graph publication still require backend
checks and a confirmed publication receipt. Re-select the folder after a reload.
The standalone preparation script remains available for API clients.

### Default XSD import: direct file selection

Use Add Files, select one or multiple XSDs, enter the ontology name and prefix,
and click Start. Multiple XSDs selected together produce one schema-set entry
and one ontology registration; the selected files are companions of an entry
schema generated in memory. Folder selection is optional. If dependencies are
missing, the Optional: resolve missing XSD companions section opens. Select the
parent folder containing those schemas, then Resolve companions and retry.
The app preserves the existing ontology details and maps paths automatically.
For QIF select docs/xsd as that parent folder. Do not select a root again for a
failed direct upload. Advanced folder-first selection remains available.
Same namespace schemas use includes; differing namespaces use imports. Conflicting
schema declarations fail validation rather than being silently overwritten.

Before OWL translation, the backend compiles the uploaded XSD schema set offline
with lxml. Conflicting declarations and invalid schema references fail before
ontology registration. This checks XSD validity; it does not claim that every
XSD constraint has an equivalent OWL or SHACL representation.

Import job history is saved in the browser and remains after refresh. Use Clear
finished/failed history to dismiss terminal upload rows; this does not delete
registered ontologies or backend execution records. Active jobs and uncertain
publication outcomes remain for reconciliation. Use the horizontal scrollbar to
reach all columns. Processing details displays the known state, stage, start time,
task identifier and full message. Engineering schema processing currently returns
a final result; the UI must not imply live per-stage progress it has not received.

### Build a clean customer source package

Do not ZIP the complete development workspace. After committing the intended
release files, build from tracked source files with the packaging script:

```powershell
Set-Location E:\App\PMem
.\backend\.dt_venv\Scripts\python.exe .\infra\deployment\build-release-package.py --output .\release-dist\DEPO-customer-release.zip
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
```

Choose a new output filename if the ZIP already exists. This includes required
ontology code and baseline TTL files, but excludes .codex evidence, runtime logs,
customer uploads, caches, dependencies and local environment files. It also
excludes Git references without packaged source, such as external/sirius-web.
Empty Python __init__.py files are package markers and must remain. Git does not
track empty folders; required runtime directories are created by application
startup or first use. Existing customer data must not be deleted when updating.

Namespace-aware type identities are implemented in the shared XSD conversion
engine, not in a QIF-only adapter. Colliding user types from separate namespaces
remain distinct; explicit XSD primitive references stay primitive references.
This applies to any supported local XSD set. Unsupported schema constructs still
produce explicit errors or conversion limitations rather than full-conformance
claims.

For the dedicated QIF workflow, select the reference schema folder centrally in
the root .env.local when the customer uses a specific QIF distribution:

```dotenv
QIF_SCHEMA_DIR=E:\App\PMem\data\QIF3.0-2018\xsd
```

Restart the schema-sets service after changing this setting. With no explicit
setting, the service prefers data/QIF3.0-2018/xsd when present and otherwise uses
the tracked docs/xsd reference. An explicit missing folder does not silently fall
back to another distribution. Customer schema directories are not automatically
included by the tracked-source release packager.

### Backend source update and stale-process checkpoint

Deploy the complete matching release. Updating the browser bundle alone does not
update ingestion or ontology conversion code. Startup checks converter capability
and fingerprints backend Python files. A running process with a missing or changed
fingerprint must be stopped before it can be reused. This is expected once when
upgrading from a release that predates fingerprint tracking.

```powershell
Set-Location E:\App\PMem
.\infra\windows\stop-depo-services.ps1
# Deploy the complete matching backend and infra release files here.
.\backend\.dt_venv\Scripts\python.exe -B .\backend\depo_platform\release_code_check.py
if ($LASTEXITCODE -ne 0) { throw 'Backend code update is incomplete.' }
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
```

The check is offline and needs no database credentials. It detects old/mixed XSD
converter code; it does not certify every API behavior. Preserve .env.local and
customer data when copying releases. Do not delete code fingerprint files to
bypass the restart checkpoint.

### XSD registration and approval checkpoint

New XSD imports are registered as drafts. When publication is selected, the
workflow reports approval required. Review and approve the retained ontology in
Ontology Junction before publishing it. Policy/quality checks are not approval.

The engineering graph call uses GRAPH_PUBLICATION_TIMEOUT_SECONDS (default 180).
ENGINEERING_WORKFLOW_TIMEOUT_SECONDS bounds the entire workflow (derived from downstream stage budgets when omitted,
maximum 3600). The browser allows 3660 seconds for that endpoint. If a response
is lost, inspect the retained registration and graph receipt before retrying.

Timeout defaults are composed from downstream stages. With unset settings,
agent runs allow 1440 seconds and engineering workflows allow 1350 seconds.
SERVICE_REQUEST_TIMEOUT_SECONDS defaults to 90 seconds across ingestion clients.
The deployment template sets explicit 1800-second agent and 1500-second engineering deadlines.

Publication jobs retain deadlines and retry schedules across restarts. Queue and
overall defaults are 600 and 2430 seconds. Set
`ONTOLOGY_PUBLICATION_WORKER_CONCURRENCY` (default 2, range 1-8) to bound concurrent
publications per service process; advisory locks serialize each ontology. Only
confirmed idle staging checkpoints resume automatically, with backoff and at most
three attempts. Expired uncertain writes require receipt reconciliation before a
new submission. Short explicit workflow budgets produce configuration warnings.
REST and MCP tools share the remaining workflow deadline. MCP numeric progress is
retained in the pending workflow step; MCP processes remain isolated per invocation.

Optional scanned-document OCR is separated from the default runtime. Fresh standard
installs omit EasyOCR, PyMuPDF and pytesseract. Text-based PDF and Office import
remain in the base profile. To enable scanned-PDF OCR in an existing virtual environment,
run from the repository root:

```powershell
& .\backend\.dt_venv\Scripts\python.exe -m pip install --require-hashes -r .\backend\requirements-lock.txt -r .\backend\requirements-ocr-lock.txt
```

Development installations include `requirements-ocr.txt`. Existing environments are
not automatically uninstalled or pruned. Shared transitive dependencies remain pinned;
this change does not claim that PyTorch or the full scientific stack is removed.
Semantica 0.6.7 declares PyTorch, Transformers, spaCy and other scientific packages
as mandatory dependencies. They cannot be removed safely while the ontology
generation, reasoning and context services still import Semantica.
Agent LLM composition continues to use LangChain/LangGraph with the shared Ollama
admission policy. REST contract validation, durable PostgreSQL workflows and deterministic
ontology publication remain separate responsibilities. Optional Azure provider imports
are deferred until their settings are available.

GraphRAG embedding refresh reads source nodes in pages of 100, bounds each source's
neighborhood, and writes one embedding batch at a time. Staged resources, retained
identities and publication records are excluded from indexing and graph-vector
retrieval. Normal refresh compares content/model hashes, so changed sources are
re-embedded and unchanged sources are skipped. Existing chunks without hashes are
upgraded on the next embedding run. Run the existing embedding command explicitly
after publication or model changes; this does not add an automatic indexing worker:

```powershell
& .\backend\.dt_venv\Scripts\python.exe -m backend.Services.graph_embeddings
```

Label-scoped legacy vector retrieval filters before exact cosine ranking through
the timed Neo4j query gateway. This can cost more than indexed unfiltered search
on large scopes. Empty retrieval does not call the LLM. Missing graph/document
indexes recover independently on demand, with a 30-second retry cooldown.
Companion remains bounded ontology keyword retrieval; it is not silently changed
to the legacy vector pipeline.
An explicitly configured shorter run/workflow deadline remains authoritative;
increasing an inner request timeout does not extend it. Agent execution requests
in the browser allow 3660 seconds unless a caller supplies a shorter timeout.
Invalid, non-finite and out-of-range timeout settings fail agentic preflight.
Readiness probes use their own short database budgets, separate from import and
publication limits. Restart services and rebuild the frontend after deploying.
Gateway/proxy deadlines must also cover synchronous operations, or use the
retained background workflow/publication APIs and poll their status.

For token-authenticated workflows, the caller authorizes the selected plan at
submission. Both worker and in-process execution then use scoped server
credentials; browser session expiry or logout does not cancel that authorized
work. Configure all required server credential profiles before submission.
Server credential revocation/rotation, explicit cancellation and the original
execution deadline remain effective. Reconnect to inspect the retained run;
an interrupted submission must be reconciled before starting another task.
Entra execution retains its gateway-token requirements.

Deploy the matching backend files, rebuild the frontend and restart services.
These changes require no new database migration.


### Complete publication from the Import workflow

After registration, expand **Review, approve and publish this ontology to Neo4j**
beneath the imported file row. Enter the approver identity, submit for review,
approve, then publish. **View in Ontology Junction** opens the selected ontology
in a new tab for inspection; return to the workflow to approve and publish.
The same controls remain available in Ontology Junction.
While the publication request is active, the panel displays Publishing to Neo4j.
A verified receipt updates the import row to Published with graph counts.
An uncertain outcome requires verifying publication before retrying.

Connection refused on ports 8010-8019 means the configured service addresses are
not accepting connections. On the application VM, run from the repository root:

```powershell
Set-Location E:\App\PMem
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -ge 8010 -and $_.LocalPort -le 8019 } |
    Select-Object LocalAddress, LocalPort, OwningProcess
.\infra\windows\start-depo-services.ps1 -EnvFile .\.env.local
```

If startup fails, correct the first reported error before retrying. If listeners
exist, compare their address with the browser request host and root routing
configuration; restarting frontend after root routing changes regenerates its
runtime configuration.


### Verify Full Schema Cleanup

Full Schema Cleanup is destructive. Its response must report `success: true`,
`status: SUCCESS`, and `registry_verification.ingestion` and
`registry_verification.catalog` with `status: empty` and `remaining: 0`.
A `partial` result is not a completed cleanup: inspect `graph_cleanup_message`,
`metadata_failed`, and `registry_verification`. After graph data deletion,
metadata cleanup is attempted even if removing graph indexes/constraints fails.
Read-back verification covers the cleanup service's configured PostgreSQL catalog
and ingestion storage. All services must use the same database/schema and shared
ontology storage; it does not certify differently configured service instances.
Clear Cache only invalidates caches and does not delete registrations.

Full cleanup now takes an exclusive PostgreSQL maintenance lock; guarded ontology
registration, engineering ingestion and publication take shared locks. A busy
cleanup returns HTTP 409 without starting deletion. Allow active jobs to finish
and stop scheduling new imports before retrying. All service instances must be
updated together and use the same PostgreSQL control plane for this coordination.
The no-PostgreSQL fallback coordinates only one process. External database writers
are outside this lock; final graph read-back reports remaining records as failure.


### XSD upload and companion recovery sequence

1. Open Import and select Create ontology. Click Add Files once. Select one XSD,
   or select several XSDs to combine them into one ontology registration.
2. Complete the ontology name and prefix, select OWL generation, then click Start.
3. If dependencies are missing, use Resolve XSD dependencies on that upload row.
   Select the parent folder containing the root and its companion directories.
   Click Resolve companions and retry; the same row and ontology details are reused.
4. Manual companion selection and path editing are under Advanced in that recovery
   panel. Companion selections belong to the selected row, not later uploads.
5. Close dependency recovery when finished. Removing the row also closes its recovery
   panel. Files must be selected again after a browser reload.
6. After registration, expand the row's review, approval and publication controls.

Run all starts the queued upload rows. It does not select new companion files or
approve ontology publication.


### Diagnose a long ontology publication

While the publication is active, avoid repeating Publish. The panel displays
elapsed seconds. On the application VM, inspect these logs:

```powershell
Set-Location E:\App\PMem
Get-Content .\logs\windows-services\ontology.err.log -Tail 80
Get-Content .\logs\windows-services\graph.err.log -Tail 100
```

Publication timing messages identify `retained_rdf_prepare`, `retained_rdf_ready`,
`parse`, `canonicalize`, `prepare`, `neo4j_write`, and `completed`. Compare elapsed
seconds for the same ontology ID. Canonicalization preserves blank-node retry
identity and can be expensive on complex RDF. `GRAPH_PUBLICATION_TIMEOUT_SECONDS`
bounds each RDF preparation subprocess, the downstream HTTP request, and the
Neo4j transaction. An RDF preparation worker is terminated if its deadline expires. Resource and relationship batches
are sent inside one transaction, so a successful receipt confirms the full write.
If a request fails or its outcome is uncertain, verify the receipt before retrying.

Receipt checks retain Publishing while a bounded attempt is active. Expired or
uncertain dispatched attempts require receipt reconciliation before another write.
Preparation failures before graph dispatch can be retried after correcting the
artifact or deadline. Lifecycle locks are scoped to each ontology, so one slow
publication does not hold a process-wide lock for unrelated ontologies.


### Recover from a failed or uncertain publication

1. In the ontology row, open its publication panel and choose Verify publication.
2. Publishing means the server attempt is active; status refreshes automatically.
   Wait rather than sending another publication.
3. Unverified disables Publish. Restore PostgreSQL/Neo4j connectivity or API
   credentials, then verify again. Do not clear the receipt record manually.
4. A graph receipt read that confirms no active graph publisher and no receipt
   releases a failed attempt for retry. Active RDF preparation remains protected.
5. Not published allows an approved ontology to be retried with its original
   publication identity. Published shows the current verified receipt and counts.
6. A preparation failure before graph dispatch can be corrected and retried.
   A stale instance-link preview must be regenerated and approved again.

Deploy matching ontology and graph services together: graph receipt responses now
identify active publishers and explicitly confirm idle missing receipts. Agent
merge publication tools use a longer operation-specific HTTP wait; the original
workflow execution deadline still applies. This release adds PostgreSQL migration 011 and two Neo4j performance indexes; apply them during redeployment.


### Redeploy an existing Windows installation with slow Ollama

Place the complete matching release into E:\App\PMem, preserving root .env.local,
frontend/.env.local and durable data. With the existing backend and frontend
dependencies installed, copy and paste this command in PowerShell:

```powershell
Set-Location E:\App\PMem
.\infra\windows\update-depo-windows.ps1 -EnvFile 'E:\App\PMem\.env.local' -LlmTimeoutSeconds 300
```

The updater raises Ollama's request timeout to at least 300 seconds, the agent
tool timeout to at least Ollama plus 30 seconds, and the agent run budget to at
least 900 seconds. Higher valid existing budgets are preserved. Only those three
settings are updated; API keys and connection settings are preserved. The backend
accepts LLM_REQUEST_TIMEOUT_SECONDS from 1 through 900. Ollama diagnostics use the
same environment value unless -TimeoutSeconds is explicitly supplied.

The updater validates backend/frontend configuration and Python, Node, npm and
dependency-lock prerequisites before editing timeouts or stopping services.
Token authentication with PostgreSQL credential storage requires
a nonempty `ADMIN_API_KEY`; Production also requires at least 32 characters. Existing
keys remain unchanged. Fill customer placeholders before running the update.

The updater stops the frontend and backend services, delegates PostgreSQL migration
011 and Neo4j index provisioning/validation to the existing installer, builds the
frontend, and restarts it. It does not stop an external PostgreSQL VM. Dependencies
are reused by default; add -InstallDependencies if the new release changes them.
Timeout settings are preserved unless `-LlmTimeoutSeconds` is explicitly supplied.
The delegated installer builds the frontend once. Root routing overrides include
explicitly empty gateway and aggregate URLs, so obsolete frontend aliases cannot
restore them. Reimporting an environment file clears settings imported previously
by these launchers when the selected file now omits them; unrelated shell settings
are preserved.
A failed stage stops the update and reports the error; correct it and rerun the
same command. Credential mismatches require restoring the current keys or deliberate
rotation; redeployment does not automatically rotate keys.

For a database-only upgrade, without rebuilding or starting services:

```powershell
Set-Location E:\App\PMem
.\infra\postgres\update-postgres-schema.ps1 -EnvFile 'E:\App\PMem\.env.local'
.\infra\windows\test-depo-neo4j.ps1 -EnvFile 'E:\App\PMem\.env.local' -Bootstrap
.\infra\windows\test-depo-neo4j.ps1 -EnvFile 'E:\App\PMem\.env.local' -Production
```

PostgreSQL verification expects 11 migrations and 9 operational indexes. Neo4j
verification requires both new indexes ONLINE with their expected definitions.
Provisioning needs schema privileges; normal runtime checks are read-only.
For Ollama generation testing after redeployment, use:

```powershell
.\infra\windows\test-depo-ollama.ps1 -EnvFile 'E:\App\PMem\.env.local' -ProbeChat
```

An external gateway's own request timeout must also allow the configured Ollama
budget; this application cannot change the gateway policy.

Slow-Ollama frontend waits have also been aligned: ontology-agent review and model
probe requests allow up to 20 minutes by default; the QIF agent review no longer
uses its former hardcoded 120-second limit. Chat streaming defaults to 20 minutes.
These are browser wait limits, not permission to exceed backend workflow deadlines.
Rebuild the frontend through the updater to apply them.

### Architecture safeguards on redeployment

The legacy direct graph-prefix merge now rejects writes. Use Ontology Junction's
merge preview, review the evidence, and approve that exact preview. The import
page's merge action opens this governed flow.

Engineering conversion and merge semantic validation use separate processes with
deadlines. Optional root environment settings are
`ENGINEERING_CONVERSION_TIMEOUT_SECONDS=180` (maximum 900),
`MERGE_VALIDATION_TIMEOUT_SECONDS=180` (maximum 900), and
`DEPO_POSTGRES_POOL_SIZE=8` (range 1–32, per service process).
Conversion also respects the enclosing engineering workflow budget. Increase
conversion budgets for measured conversion delays; Ollama uses its separate
generation settings. Restart backend services after changing these values.

Interactive **Merge two ontologies** previews retain a background job in PostgreSQL.
Mappings and proposed changes become available after preparation, while SHACL and
OWL-RL validation continues in the ontology service. Approval remains disabled
until validation completes without conflicts. Use **Resume retained review for
these selections** after refreshing the page; select the same source, target and
mapping pairs. Changing a pair requires a new preview. A failed job is retained;
review its message and generate a fresh preview after correcting the cause.
`MERGE_BACKGROUND_TIMEOUT_SECONDS=1800` (maximum 7200) bounds background reasoning
independently of HTTP request timeouts. One background merge runs per service
process; PostgreSQL advisory locks prevent duplicate execution of a job across
processes. A service restart resumes retained preparation checkpoints. Approval
rechecks source digests, the exact proposed graph, validation code/dependencies,
and SHACL artifacts; changed evidence requires a new review. This feature uses
the existing PostgreSQL registry and requires no additional Windows service.
Generated default editorial SHACL checks target submitted declarations in both
inline and retained artifact form; inferred built-in vocabulary is not required
to carry source labels or comments. Custom SHACL target semantics are preserved.

Workflow manifests use the existing PostgreSQL registry table when a database is
configured. Existing file manifests remain readable and are adopted on their next
write; this introduces no additional schema migration. Local file mode uses an
operating-system lock to prevent concurrent writers from losing manifest entries.
Artifacts retain separate usage references when the same bytes serve different
workflows. PostgreSQL control-plane connections are pooled; advisory locks use
dedicated connections in addition to the configured pool capacity.

Preserve existing storage directories during upgrades. All services accessing
workflow or ontology files must share the same durable storage and configured
paths. PostgreSQL-backed manifests do not make local artifact files available on
another VM. Legacy ontology metadata and the governed catalog still require their
existing migration/adoption flow; this update does not silently rewrite IDs.

Ontology publication retains matching projection edges and deletes only edges
absent from the new revision, within one transaction. Identity restoration is
batched at 1,000 resources. Blank-node canonicalization runs only for graphs that
contain blank nodes. No additional schema migration is required for these changes;
keep the existing publication and resource identity constraints provisioned.
Restart backend services after deploying the updated publisher. Verify a first
publication and a changed-source republication before customer release.

`GRAPH_PUBLICATION_TIMEOUT_SECONDS` is a per-stage budget. With its default 180
seconds, graph dispatch allows 570 seconds for graph preparation, writing and activation;
the enclosing ontology publication allows 780 seconds including retained-source
preparation and transport overhead. Engineering and agent workflow deadlines
still take precedence. Configure any reverse proxy timeout to cover the operation
you invoke. A network timeout means an unverified outcome, requiring receipt
verification before another publication attempt.

Agent merge preview and draft creation also include the merge validation budget:
with default settings their tool wait is 210 seconds; merge-and-publish allows
990 seconds. The original agent execution deadline remains authoritative.
Neo4j preflight now verifies constraint labels, properties, entity type and
uniqueness, not just names. An existing incompatible constraint requires database
administrator reconciliation; bootstrap deliberately does not drop constraints.
Publication IDs cannot use the internal `__lock__` value. Receipt verification
does not overwrite a newer in-progress attempt. Display labels prefer English,
then untagged values, then other languages, with a stable lexical tie-break.

For a PostgreSQL `ConnectionTimeout`, run this on the application VM:

```powershell
& 'E:\App\PMem\infra\postgres\test-postgres-connectivity.ps1' -EnvFile 'E:\App\PMem\.env.local' -NetworkCheck
```

The TCP stage reports DNS failure, refusal, timeout or reachability for the selected
database endpoint, then runs the normal login check if TCP succeeds. TCP success
alone does not verify PostgreSQL authentication or TLS. Correct listener/firewall
or routing issues on the database and application VMs; for reachable TCP with a
login timeout, inspect PostgreSQL logs and the matching SSL settings. The bounded
connection timeout remains `DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS` (1–60 seconds).


Metadata governance uses authenticated audit actors. Existing installations retain
`DEPO_METADATA_STORAGE=neo4j`. To adopt PostgreSQL governance, freeze metadata writes
and call administrator-authenticated `POST /api/v1/metadata-registry/migrations/postgres`
with `{"asset_ids":["existing-asset-id"]}` in batches of at most 100 IDs. Verify all
required assets and their retained legacy history before setting
`DEPO_METADATA_STORAGE=postgres` and restarting ontology services. Adoption does not
change storage mode or delete existing data. Earlier completed assets remain retained
if a later asset conflicts. Do not switch back while projection events are pending.

In PostgreSQL mode, asset, audit and outbox updates commit together with revision
checks. Clients can send `expected_revision` on updates. An independent ontology
service loop projects pending events to Neo4j; graph failures retain events for retry.

Semantic Bridge source evidence now uses private ingestion API
`POST /api/v1/bridge/source` and the registered server ingestion credential. Deploy
agentic and ingestion updates together. Agentic no longer reads ingestion files locally.
Vocabulary publication retains its artifact and publication identity and verifies graph
receipts on retry. Legacy publications without identities require reconciliation.
Business ContextGraph and live Neo4j context expose separate representation fields;
these APIs do not claim that the two graphs are automatically synchronized.

Export all ten microservice OpenAPI contracts with the installed backend runtime:

```powershell
& .\backend\.dt_venv\Scripts\python.exe .\scripts\export_service_openapi.py
```

The exporter imports service apps and validates generated contracts without listeners.
For running services, pass `--live-template 'http://YOUR-SERVICE-HOST:{port}'`, replacing
the hostname, or a gateway URL template ending in `/{apim_path}`. Gateway credentials
must already be injected into the process environment. Completed bundles contain a
`manifest.json` with all services, contract hashes and Git revision/dirty state.
Validation failure produces no completed bundle. APIM import remains a separate
customer deployment step; exporting does not modify APIM.

Optional OCR installation is available through the supported Windows entry point:

```powershell
.\install-depo.ps1 -EnvFile '.env.local' -EnableOcr
```

Omit `-EnableOcr` for text-only installations. The switch forwards through both
Windows installers and validates the optional hashed lock before installation.
Development installs already include OCR. `-SkipDependencyInstall` skips installing
OCR too. Tesseract OCR additionally requires its native executable; EasyOCR model
files must be provisioned as described above. Missing Tesseract no longer disables
the independent EasyOCR PDF-rendering dependencies. Existing installations are
not automatically pruned; use a fresh environment to measure the smaller profile.

Engineering workflow publication now submits a durable job using the ontology
publication API with `background=true`. For an already approved source, the
engineering API returns `status=publication_queued` and `publication_job`, including
`job_id` and `ontology_id`. This confirms acceptance only. Poll
`GET /api/v1/ontologies/{ontology_id}/publication` until a current published receipt
is verified. The Create ontology UI opens this tracking panel automatically.
Drafts still require normal lifecycle review before publication. The ontology
publication worker must be running. Clients that previously required an immediate
`published` engineering response must handle the queued response and poll status.

Semantic Bridge preserves the selected ontology version ID through source lookup
and verifies target scope during the Neo4j transaction. Mapping evidence reads
both legacy DOMAIN/RANGE edges and published RDF domain/range predicates. Bridge
transactions use the configured GRAPH_PUBLICATION_TIMEOUT_SECONDS (default 180
seconds), bounded by the current operation deadline when present, with automatic
Neo4j driver transaction retries disabled. An interrupted response still requires
receipt reconciliation before retrying the retained publication selection.

Reviewed merge-and-publish now also queues the durable ontology publication job.
Its response can contain `publication_status=queued` and `publication.job_id`;
the Semantic Bridge UI tracks completion through the same publication panel.
Keep the ontology publication worker running and deploy the matching frontend.

Bridge previews support `candidate_offset` (default 0) and retain a `partition`
with `total_candidates` and `next_offset`. The UI offers **Prepare next mapping
batch** after the current automatic workflow completes. Each batch contains at
most 2,000 candidates and retains its own selection and graph receipt. Review
held candidates separately. An inactive ontology invalidates the source snapshot.
Relationship domain/range and attribute datatype evidence must be established
before automatic publication; missing evidence is held for review. Remembered
mappings remain recommendations and cannot raise confidence to obtain approval.

Merge preview parsing, union preparation and semantic checks run in a terminable
worker under `MERGE_VALIDATION_TIMEOUT_SECONDS`. Apply and policy checks also
parse retained Turtle in a bounded worker. Combined merge source bytes must fit
`ONTOLOGY_MAX_UPLOAD_BYTES`; partition larger merges. PostgreSQL merge locks are
scoped to the preview or application identity so unrelated merges can proceed.
Workflow pages expose receipt verification and recovery when the server permits
them. Verify the previous executor has stopped when requested before reconciling.


### Metadata delivery recovery and database deadlines

With `DEPO_METADATA_STORAGE=postgres`, the ontology service projects retained metadata
revision events into Neo4j. Each event has its own PostgreSQL acknowledgement transaction.
A failed event remains pending and its outbox scheduling timestamp is deferred by 30 seconds;
other events can proceed. Audit event creation timestamps remain unchanged. Inspect ontology
service logs for `Metadata projection deferred` and the retained event ID when failures repeat.
Projection takes the shared ontology maintenance lock, so graph cleanup cannot overlap it.
A graph reset requeues retained metadata events; while the ontology service runs, governed
metadata and its history are rebuilt in Neo4j. Ontology and Bridge publications still require
their normal publication workflow after reset.

Workflow operation budgets cap shared graph queries, agent memory queries, PostgreSQL pool
waiting and statements. SQL budgets are recalculated before each cursor dispatch. Connections
used with an operation deadline are closed after use to avoid leaking session timeout settings.
A new PostgreSQL connection requires at least two seconds of remaining budget because libpq
has a minimum connection timeout. Existing independent configuration limits remain upper bounds.

New Semantic Bridge publications retain per-candidate `DepoBridgeMapping` evidence connected
to their publication, source and target. Current semantic relationships can be updated by a
later approval without removing this historical evidence or adding duplicate instance links.
Earlier publications created before this change retain their existing receipts; detailed
historical mapping evidence is recorded for new publications only.

PostgreSQL metadata writes validate the complete resulting revision, including fields retained
from earlier revisions. Updates that remove an approved asset's steward or approval evidence,
or create an invalid effective date window, return HTTP 409 without creating an audit event
or an outbox event. Correct the fields or use the lifecycle transition endpoint first.
Neo4j Bridge publication accepts both UNIQUENESS and NODE_PROPERTY_UNIQUENESS constraint
type names and still verifies node entity type, label and publication identity property.

### Operational data store and data mart views

The approved `xml-analytics-materialize` job retains the original XML and builds an
append-only, versioned structural operational data store (ODS). Entity and link inserts
use bounded batches within the same transaction; identity allocation carries explicit
row ordinals so batch response order cannot change parent/child links. Repeating an
identical document reconciles its retained receipt instead of loading duplicate rows.

In Data Products, open **Load validated XML into PostgreSQL analytics** and use the
**Data mart view designer**. Load fields using the registered XSD ontology ID that
matches the retained XSD artifact, select an entity, and define either an aggregate
fact view or a dimension. The generated definitions appear in the editable business
view JSON. Property selectors use the model's exact `sql_name`; unambiguous old local
names remain accepted. An attribute and element sharing a name require exact identities.

Dimension definitions use `kind=dimension`, `grain=business-key`, explicit `keys` and
`attributes`, and `history_policy=immutable`. They create distinct views over the ODS.
Null keys and conflicting attributes under one key reject the entire new load and its
receipt. These are natural-key dimension views, not a shared surrogate-key warehouse.
Aggregate fact views use `kind=fact`, `grain=entity-instance`, explicit `group_by` fields
and count/sum/avg/min/max measures. They aggregate all documents in the selected ODS
entity table. Cross-entity joins, conformed dimensions and slowly changing dimension
policies require a separately reviewed model and are not inferred from XSD structure.

The default `constraint_policy=strict` retains all review blockers. To load supported
facets and fixed values, explicitly select `constraint_policy=validated-source` (the UI
checkbox). The complete XML still undergoes formal XSD validation; equivalent PostgreSQL
facet constraints are not generated. Precision decimals are stored as NUMERIC to avoid
rounding or rejecting XSD-valid integral values. Choices, repeated groups, temporal and
source-identity policies remain blocked. XML using `xsi:type` is rejected before row
extraction because a polymorphic relational mapping is not implemented. The original
source can be retained, but the job will not claim successful instance materialization.

Changing business-view definitions or the materialization policy for an existing ODS
may require a new schema prefix. Existing projections are not altered automatically.
The pipeline OpenAPI input schema describes the supported measure, view and policy fields.
The view designer binds definitions to the retained root XSD artifact. A report from
another registration cannot supply fields for the selected source. Legacy registrations
without a retained source artifact must be imported again before using the designer.
View receipts expose `output_columns`, mapping each SQL output alias to its source
property and role, including fact group keys and dimension keys.

A committed ODS load can have `evidence_status=pending` if artifact storage fails.
The run remains completed and product publication stays blocked. Use **Rebuild analytics
evidence** in the XML loader, or the authenticated
`POST /api/v1/pipeline/jobs/runs/{run_id}/reconcile-analytics` operation. This rebuilds
evidence from the retained committed receipt without loading XML again. A database
outage that prevents retaining the run itself still requires operational reconciliation.

The XML loader retains the submission identity in browser session storage. After a
network failure, find the retained run in Data Flow history and refresh it before
submitting again. If history confirms no matching run exists, explicitly acknowledge
that check to prepare another task. No XML write is automatically retried.

### API authorization and diagnostics

With environment-based credential storage, admin routes require `ADMIN_API_KEY`.
Keyless development access requires both `DEPO_ALLOW_INSECURE_LOCAL_AUTH=true`
and a loopback client address. Any production or staging marker in `DEPO_ENV`,
`APP_ENV`, `ENVIRONMENT` or `DEPLOYMENT_ENV` disables that bypass. PostgreSQL
credential storage continues to require a verified registered key or authorized
maintenance session.

Unexpected API errors return a generic JSON error and `X-Request-ID`; use that
ID to inspect server logs. Allowed browser origins retain CORS headers on these
errors. Credential discovery uses `/auth/admin-access` for the administrator key,
`/auth/access` for read access, and `/auth/credential-check` for workflow profiles.
Regenerate service OpenAPI documents and reimport them into APIM after this update
so helper-based approval requirements and supported credential checks are current.

`scripts/frontend_api_contract.py` checks static frontend calls against the owning
service and HTTP method. Run it in the installed backend environment with all
service dependencies available. The report lists unresolved dynamic expressions
for separate runtime testing; it cannot certify those calls. Empty inventories
fail validation. Unowned routes are reported instead of being silently accepted
through another service's matching route. Unused aggregate-only health, AP242
search/report and alignment-option client wrappers have been removed; use the
service-specific APIs already consumed by the current pages.

The UI includes safe server request IDs in shared API error messages and service
credential diagnostics. Quote that ID when locating the corresponding backend log.
Retained pipeline runs open through the pipeline status API; agent/workflow runs
continue through their own status APIs. Recommendation forms consume discovered
approval metadata to mark required approver fields before execution. The backend
still validates the actual credential scope and approval for every operation.

### Customer upgrade: performance and service runtime release

For an existing Windows deployment, place the complete matching release in the
application directory while retaining root `.env.local`, frontend `.env.local`,
artifact storage and database contents. Keep the previous release and a verified
database/artifact backup available before the maintenance window. Run from the
repository root; do not run both installers or recreate the database.

```powershell
# Read-only checks: no service shutdown, migrations or configuration changes.
.\update-depo.ps1 -EnvFile 'E:\App\PMem\.env.local' -PreflightOnly

# During the maintenance window: dependencies, pending migrations, frontend
# rebuild, service restart, authenticated route checks and release preflight.
.\update-depo.ps1 -EnvFile 'E:\App\PMem\.env.local' -InstallDependencies
```

The updater delegates to `infra/windows/update-depo-windows.ps1` and the existing
installer. It preserves credential profiles, does not rotate keys, and skips
baseline seeding on upgrade. Timeout changes require an explicit
`-LlmTimeoutSeconds` argument. Use `-SkipFrontend` only when frontend build and
hosting are managed separately. Add `-EnableOcr` with `-InstallDependencies` if
this deployment requires OCR. Changing `DEPO_SERVICE_RUNTIME_MODE` to `isolated`
requires `-InstallDependencies` to create the thirteen selected runtimes;
omitting the setting retains the existing shared runtime.

Migration **012_ontology_catalog_pagination** adds an index supporting active
ontology catalog pages. Existing migrations 001–011 remain immutable. The
migration runner applies pending versions transactionally under its advisory
lock, verifies recorded checksums and checks the resulting schema. Index creation
can hold a table lock and take time on large registries; apply it in this stopped
service maintenance window with the owning migration role. No ontology or
customer data is deleted. No Neo4j schema changes are required by these performance
fixes; existing graph schema compatibility checks remain enabled.

If an upgrade fails after shutdown, inspect the named failing stage and service
logs, correct the cause and rerun the same command. Services may remain stopped.
Do not automatically restart older application code against a newer schema;
coordinate rollback with the retained release and reviewed database backup.
`-PreflightOnly` checks existing database compatibility and privileges but does
not prove that every pending migration or live customer workflow will succeed.

After startup, verify the customer's retained ontology publication without
resubmitting a publication write:

```powershell
$ontologyId = Read-Host 'Retained ontology ID to verify'
.\infra\windows\test-depo-browser-session.ps1 -EnvFile 'E:\App\PMem\.env.local' -OntologyId $ontologyId -RequirePublished
```

This checks current authenticated ontology routes and the published graph receipt.
Customer gateway access, large ontology publication and browser acceptance still
require validation in the deployed environment.


### Publication deadlines and uncertain outcomes

QIF and CEIM graph dispatch use the shared graph publication budget: RDF preparation + staged writes + activation + 30 seconds of transport allowance (570 seconds with default settings). This is an overall caller budget, not one long Neo4j transaction; graph staging transactions are capped at 30 seconds and check the remaining operation deadline.

A client timeout or disconnect cannot undo an already dispatched commit. The caller performs one bounded read-only receipt lookup using the ontology and publication IDs. A verified receipt confirms completion; an unavailable, active, or missing receipt leaves the outcome unverified. Do not automatically repeat the publication. QIF retains this state across restart and its verification action reads the receipt without issuing another publication. CEIM returns the publication identity and receipt URL in its structured unavailable response.


### Worker admission, cancellation and graph read isolation

Pipeline runs retain an absolute deadline from submission (default 900 seconds, configured by DEPO_PIPELINE_JOB_TIMEOUT_SECONDS). Queue waits and automatic retries consume that same budget. Heartbeats cannot extend it. Spark actions use an attempt-specific job group; the deadline or loss of the lease cancels that group and fences later PostgreSQL writes. Native Python work stops at execution checkpoints; cancelling a request does not undo a completed external commit.

The schema-set worker accepts at most QIF_MAX_PENDING_TASKS queued/running tasks (default 16). Additional requests receive HTTP 503 with Retry-After; retained manifests remain discoverable. Preparation deadlines start at intake, and approved publication has a separate execution budget. Service restart preserves those deadlines. Shutdown stops admission, cancels unstarted futures and prevents further stages in active work. Pure XSD inspection, validation and generation run through the same registered agent tools in a child process; timeout, cancellation or shutdown terminates and reaps that process. An already dispatched graph commit must be verified by its receipt.

Catalog outbox delivery uses DATA_PRODUCT_OUTBOX_CONCURRENCY independent workers (default 4, maximum 16) and DATA_PRODUCT_OUTBOX_BATCH_TIMEOUT_SECONDS (default 30 seconds). Timed-out or deferred rows remain pending, with the existing idempotent version key and retry schedule. A batch finishing does not imply every catalog delivery succeeded; inspect published, pending and deferred counts.

Exact-ontology projection/analytics reads use a per-ontology reader lock and the cleanup exclusion lock. Publication drains those readers before mutation; an interrupted replacement of ontology A does not block an exact projection of ontology B. Cross-ontology searches and legacy graph queries retain the global barrier to avoid partial results. Old activation markers without the scoped-drain guarantee remain conservatively blocked until verified recovery. Deploy services together and restart the complete service set; mixed old/new publication workers are not supported during this locking-protocol upgrade.

QIF defaults to `QIF_TASK_STORAGE=local`: one process owns its task directory through an OS lock. For replicas, explicitly select `QIF_TASK_STORAGE=shared`, set absolute `QIF_TASK_ROOT` and `ARTIFACT_STORAGE` paths on shared persistent volumes, and use the same PostgreSQL database and schema. PostgreSQL session advisory locks serialize each task execution and task-state update. Every worker checkpoint verifies that its execution session is still alive; uncertain publication intents remain retained for receipt reconciliation. Sources stay under the QIF task and generated ontology registration uses HTTP.

The API and workflow worker manage bounded MCP process pools. Discovery and calls within the same operation context reuse one initialized session and serialize requests. Different operation contexts receive separate processes even when their public correlation IDs match. Discovery follows at most 100 pages under the response byte limit. Timeouts or protocol failures discard the session without replaying tool calls. Idle sessions expire after `AGENTIC_MCP_IDLE_SECONDS` (default 60); capacity is `AGENTIC_MCP_MAX_SESSIONS` (default 4, maximum 32). Busy capacity rejects new calls before dispatch. API/worker shutdown terminates pooled children. Standalone callers without a managed pool retain bounded one-shot behavior.

Before changing QIF storage mode, stop all QIF processes. Preserve existing task/artifact contents when copying them to the shared volumes, then configure every replica consistently and restart. Startup records shared-volume identities in the existing PostgreSQL registry and `.qif-storage-id` marker files. Subsequent replicas must match both identities; a separate local disk fails startup. Preserve these markers during volume migration and restore; correcting a mismatch requires fixing the mounts, not deleting data. No new PostgreSQL table migration is needed. A shared filesystem with atomic file replacement and reliable cross-host visibility is required. Validate failover against customer PostgreSQL and shared storage before enabling replicas.

The agentic inference implementation uses the pinned LangChain-core Runnable/PromptTemplate interfaces behind the existing native Ollama REST configuration. No new enablement flag is required: existing Companion/ontology-agent feature flags still apply. Custom APIM URLs, credential headers, generation/chat separation and `OLLAMA_STREAMING_ENABLED` remain authoritative. Model discovery and inference probes remain separate operations. Optional model-library loading is deferred off the API event loop; cold-start initialization consumes the operation budget. No dependency lock or package reduction was claimed by this change. Validate configured chat, generation, structured/tool and streaming operations separately against customer APIM.

### Updating ontology semantic inventories

The semantic-inventory update uses existing PostgreSQL JSONB catalog records; it requires no new tables or credentials. Newly registered ontologies receive versioned semantic statistics. For existing records, invoke the authenticated `POST /api/v1/ontologies/migrations/legacy/analytics` operation with selected `ontology_ids`. It refreshes statistics without approving or publishing artifacts. Use the existing governed publication workflow to refresh Neo4j kinds and RDF type properties. Stored RDF predicates remain authoritative; this update does not execute imported SWRL rules or invent missing axioms.


### Windows setup and lifecycle audit logs

Use `Setup-DEPO.cmd` for install/update/repair, start, stop or restart. Its PowerShell bypass applies only to the launched process and does not change the machine execution policy.

Each setup, installation and lifecycle action prints its audit-log path immediately. Logs are retained after failure and retry:

- Application actions: `logs/installation/runs/<action>-<timestamp>-<run-id>.log` and the matching `.jsonl` file beneath the application folder.
- The supplied upgrade launcher also logs package validation and copy failures beneath `logs/installation/runs` beside its package folder (the directory containing `Setup-DEPO.cmd`).
- Dependency installer output remains under `logs/installation`; service stdout and stderr remain under `logs/windows-services`.

The text log captures PowerShell output, warnings, errors and failure location/stack information. JSONL records include UTC time, run ID, action and a final `succeeded` or `failed` event. Native nonzero exits fail the action. Inspect the earliest failure before any cleanup messages; an absent listener after cleanup does not identify the original cause. Retrying creates a separate run log and retains previous evidence.

Known credential values from the process environment and `.env.local`, PostgreSQL URL passwords and bearer tokens are redacted in action logs. Review logs before sharing because arbitrary application output may contain other sensitive data. Parser errors, invalid launcher arguments, or failures before the logging helper loads can still appear only in the command window. These action logs supplement service logs; they do not replace application request/audit records or capture browser errors.

Windows shutdown archives PID files under `logs/windows-services/stale-tracking` when the inspected PID belongs to a different module. The unrelated process is left running. Missing executable/command-line information or a matching service module using an unapproved runtime still stops setup and retains tracking for diagnosis.

Native Python import/OpenAPI and ontology-upgrade checks retain informational stderr without treating it as a PowerShell failure. Their stdout remains separate for JSON parsing; nonzero exit codes still fail setup.


### Automatic ontology prefixes

In Add Files, only the ontology name is required metadata. The prefix is an optional display-alias override; changing it does not rewrite source namespace IRIs. XSD imports preview the alias from `targetNamespace`. Other supported formats can leave the field blank for server-side namespace discovery during registration. If no namespace can be discovered, registration uses the `ontology` fallback alias.

The QIF and multi-XSD workflows also accept a blank prefix and derive it from a shared declared target namespace, rather than a hardcoded standard/profile prefix. If the selected schemas declare multiple target namespaces, the API asks for an explicit alias for the combined ontology. Supply an override and retry; imported source namespaces remain unchanged. A saved explicit prefix remains an override when resuming an import.


Windows npm dependency installation and frontend builds retain stderr warnings (including deprecation notices) without failing a successful command. `npm ci` retries only after a nonzero exit, up to three attempts. Each attempt retains stdout and stderr in `logs/installation/npm-ci-<run-id>.log`; the setup action log also retains that output. Exhausted install attempts or a nonzero build exit still fail setup. Dependency health probes inspect exit codes, rather than treating warning output as proof of failure.

Import job summary totals cover all workflows and retain restored failures even when a job is no longer active. Stage counts and progress arrows cover only the selected workflow. Five parsed instances awaiting load approval are not active jobs; they require explicit review and an approver before loading. XSD publication offers OWL; SHACL guidance applies to shape validation in register-only mode.

Ontology Junction retains each registered version by immutable ontology ID, including versions sharing a prefix. Open a draft using its exact target link and verify the selected version. With no active selection, taxonomy is not loaded automatically. Missing target IDs show an unavailable selection rather than silently opening another ontology. The OWL Browser class inventory excludes datatypes, restrictions, expressions, properties and individuals; the hierarchy explicitly labels its limited preview count separately from the loaded class count.

For a repair package, validate frontend dependency completeness against an installed-tree copy with only the package overlay applied, then run its production build and targeted tests. A successful source-checkout build alone does not establish that the repair contains every required helper/export. The ontology selector repair includes `frontend/src/utils/ontologyPresentation.js`, which exports the shared class predicate used by the OWL browser.

### Discovering ingested data and analytics plans

Data Catalog includes an Ingested data inventory sourced from the retained ingestion task registry, plus links to registered ontology versions. These records are visible before a governed data product is published. Import status is retained task evidence, not an independent graph reconciliation. Use Import to review graph loading and approvals. Inventory read failures are displayed separately from empty collections.

In Data Products, select an imported schema draft to inspect its analytics schema, entity tables, grain, generated SQL and blockers. The XSD report is a review-only structural plan. Dimensions and KPI business definitions require explicit keys, measure expressions, units, aggregation and history rules in an approved XML analytics job in Data Flow. Existing graph imports do not automatically populate warehouse tables or publish product packages.

### Semantic Bridge agent troubleshooting

A vocabulary dictionary or mapping-list timeout is reported independently of Semantic Bridge. Instance mapping controls and ontology merge review remain available. Merge mode reads retained RDF through the governed agent and does not wait for the vocabulary-list request. Source/target term inventory errors remain visible inside each inventory.

Ontology merge proposals use lexical-context-v1 scoring for terms with identical declared kinds: 50% normalized label/token and text similarity, 30% character trigrams, 10% definitions, and 10% role-aware domain/range or attached-property context. Missing context contributes zero. The proposal threshold is 55%; scores are heuristic similarity, not calibrated confidence or semantic equivalence. Ambiguous alternatives are flagged. Each source considers at most 100 candidates, common index buckets above 200 terms are omitted, total comparisons are limited to 100,000, and at most 200 proposals are returned; limited searches are identified in the review. Proposals never authorize automatic consolidation. Select a pair, generate a fresh preview, and review semantic validation before approval. Review source/target definitions, domains and ranges before selecting a consolidation. The merge preview is required before approval. Instance linking uses the Governor/Steward workflow to retain candidates, explain held decisions and publish only policy-approved mappings. The separate ontology agent review is visible beside automation and shows its retained evidence on completion. A model recommendation does not itself authorize publication.


## Installer audit corrections — 2026-10-20

First-run connection values are validated and serialized before key generation. Configuration is generated in an isolated directory inside the release, parsed, and moved into root `.env.local` only after success; failed staging is removed so a rerun can prompt again. Existing configuration is retained. Passwords are hidden and unsupported multiline or ambiguous quoting is rejected without echoing the value. Portable PostgreSQL status accepts the expected stopped-server exit code; start failures still stop installation, and informational native stderr is logged without replacing the exit-code decision.

Use `Setup-DEPO.cmd` from File Explorer, or `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\setup-depo.ps1 -Action Setup` from the release root. For routine operation choose Start/Stop/Restart in that launcher. Stop and Restart stop tracked application processes; database servers remain running. These are process launchers, not Windows-service registration for all PMem APIs. PostgreSQL service startup may require an elevated Windows session; process ownership checks remain mandatory. Keep the exact error and `logs/installation/runs` log when requesting support.


Direct `setup-depo.ps1`, root `install-depo.ps1`, and `manage-depo.ps1` invocations establish process-scoped execution-policy Bypass before loading helpers. This protects nested script loading only after the entry script starts. If Windows blocks that entry script itself, use `Setup-DEPO.cmd` or an explicit `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ...` command. Organization Group Policy remains authoritative and can require an approved signed release; no launcher changes machine-wide policy.


### Large ontology regeneration and merge reviews

After deploying converter updates with Setup-DEPO.cmd (option 1), generate a **new review draft** from the original schemas. Existing publications are retained until an approved replacement is published. Generated XSD association nodes carry source-file provenance and descriptions identifying them as projection constructs; a declared XSD version is preserved in the ontology header.

QIF global references resolve before property classification. Unresolved types stop conversion. List-valued properties retain XML lexical text with explicit limitations: source XSD validation is still required for item types, ordering, facets, identity constraints and compositor semantics.

In **Ontology Junction → Semantic Bridge → Merge two ontologies**, choose the exact source and target versions, enter the reviewer, and review the merge plan. Large reviews run in the background; **Resume retained review for these selections** restores saved proposals and validation after a restart. Vocabulary reads have a cancellable 90-second budget and a read-specific retry action. A retry does not approve or restart a merge.

Inspect source namespaces, any normalized element/type IRI collisions, proposed identity consolidations and validation findings before approving. Similarity scores are heuristic evidence, not proof of equivalence. Generated metadata checks and custom semantic constraints are reported separately. Warnings remain blocking under the configured policy; full OWL-RL checks do not establish full OWL-DL consistency.

The combined inputs and retained output must fit the configured ontology size limits. Converter-generated descriptions use compact text to avoid unnecessary payload growth. Do not delete environment files or databases to resolve a size or validation failure.

After **Approve merge and publish**, wait for the graph publication receipt and verify its ontology ID, artifact/publication digest, current status, resource count and relationship count. If the response is uncertain, resume or reconcile the same saved review rather than creating another publication.

Detailed diagnostic evidence and validation measurements are recorded in [the remediation audit](../../docs/audits/enterprise-remediation-2026-10-20.md).

Service principals may approve versioned ontology operations without an email address. The versioning adapter retains the authenticated identity and uses an internal reserved-domain representation where required by its library. An author-format failure is a software error; do not replace credentials or request approval again. After deploying a validation-policy change, regenerate the review receipt before resuming publication. Verify the current Neo4j publication receipt before reporting completion.


### Agent goal investigations and retained evidence

Agent recommendations now include **Investigate a goal with the agent**. Load the agents, select an agent with read tools, describe the investigation, and select **Start read-only investigation**. Use retained source and ontology IDs in the page context. The configured model first decomposes the goal, then selects registered reads. Failed read observations are retained for subsequent decisions; compatible alternative tools or revised inputs may be selected within the original scope. A model-assisted conclusion must cite completed, untruncated observations and remains reviewable evidence.

This mode requires `AUTH_MODE=token`, `AGENTIC_EXECUTION_MODE=worker`, a running workflow worker, and working inference for the selected Ollama/OpenAI/Mistral model. Model configuration alone does not verify inference or cloud quota. The existing service credential setup provisions the worker profiles; users do not enter a new approver for a read investigation. A changed tool contract, credential grant, model recipient, or selected scope blocks continued execution.

PostgreSQL namespaces `agentic_goal_runs_v1` and `agentic_goal_heartbeats_v1` retain goal plans, sanitized observations, decisions, ownership and execution activity using the existing registry schema. No separate database is required. This scratchpad does not depend on optional Neo4j conversation memory. `AGENT_MEMORY_ENABLED=false` disables that separate graph memory feature, not workflow or goal persistence. Do not enable optional graph memory merely to repair a goal; verify its scope and storage health separately if that feature is desired.

`AGENT_GOAL_MAX_DECISIONS` defaults to 8 (allowed 3–16), including plan revisions and completion decisions. At most three plan revisions and sixteen pending goals are accepted. The existing agent run deadline applies across recovery; a restart never resets the budget or repeats completed reads. Interrupted read goals are reclaimed by the worker. **Cancel investigation** fences the executor; an active read may finish, but no further action is accepted. Plans and observations remain available in the panel; the browser retains the latest goal ID as a convenience bookmark. Terminal evidence is retained in PostgreSQL for audit.

This runner does not generate executable code, select arbitrary URLs, change identities after an authorization failure, approve equivalence, or publish graph mutations. Those operations continue through governed workflows and verified write receipts. Custom agents must explicitly classify read tools and provide discoverable input schemas before they can participate. The panel displays plan revisions, failed attempts, successful evidence and cited conclusions separately.

Document import now preserves Word paragraphs and nested table cells in source order, and PowerPoint text, tables and grouped shapes. Table cells carry source-location markers in extracted text. PDF native/OCR text remains page-based; visual figure understanding and scanned table structure are not claimed. Ontology review uses one retained artifact snapshot for intake, structure review and bridge planning. Artifact matching no longer indexes only the first 500 terms per kind, and restored instance metadata no longer silently samples only the first 1,000 rows. Existing publication receipts and previously ingested documents are not migrated; re-import affected source documents to regenerate missing evidence.

After applying this update, restart the backend services, workflow worker and frontend through the existing Setup-DEPO launcher. The installer retains database data and environment credentials. Test an investigation with a known source ID, verify a deliberately failed read can use a compatible registered alternative, and inspect its retained observations before relying on the result.

## Customer installation acceptance checklist

Release packaging must include Setup-DEPO.cmd, its guided setup and checkpoint helpers, dependency locks and migrations. Build the customer artifact from the reviewed release commit; validate that artifact with `infra/deployment/test-installation-package.ps1`. A local assembled patch package does not prove the Git release is complete.

Before customer rollout, test the release on a clean Windows machine, including a checkout path with spaces and a restricted execution policy. Verify first install, unchanged rerun, interrupted dependency installation/resume, a rejected upgrade with the existing application still available, database connectivity failures, migration failure recovery, credential preservation and redacted audit logs. Exercise Start, Stop and Restart plus a browser import-to-publication workflow. Validate database/artifact backup and restore separately.

Installation success means the installer completed its checks and started the configured services. An ontology upgrade-review notice means corrected drafts need lifecycle review; it is not an installation error. Graph publication is complete only after its durable publication job succeeds and graph verification passes. LLM readiness additionally requires a real request to the configured provider; an HTTP 429 or unavailable Ollama model does not count as successful agent inference.

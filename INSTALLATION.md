# DEPO installation and release guide

This is the single installation guide for the DEPO frontend, backend, PostgreSQL,
Neo4j, Spark and PySpark. Run commands from the repository root on Windows.

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

Create a database, a least-privilege application login, and its schema. The
second command prompts securely for the application password instead of writing
it into PowerShell history. Replace only the server administrator account when
it differs from `postgres`.

```powershell
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c 'CREATE ROLE depo_app LOGIN;'
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c '\password depo_app'
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c 'CREATE DATABASE depo OWNER depo_app;'
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -d depo -c 'CREATE SCHEMA semantic AUTHORIZATION depo_app;'
```

In the root `.env.local` created in section 2, set
`DEPO_DATABASE_URL=postgresql://depo_app:URL_ENCODED_PASSWORD@127.0.0.1:5432/depo?sslmode=disable`
for this local setup. For a managed or customer database, ask the DBA to create
the equivalent login, database and schema; use `sslmode=verify-full` and the
customer CA certificate. Never paste a real password into PowerShell history or
source control.

Neo4j may run on-premises, on a private VM, as a hosted self-managed server, or
in Neo4j Aura. Use the provider's actual database name. Production requires
certificate-verified TLS: `neo4j+s://` or direct `bolt+s://`. Bootstrap may use
`+ssc` or plaintext only on a controlled local network. Configure the advertised
Bolt address, certificate chain and application database account. The application
installer does not install or operate either database server.

### 1.2 Install optional Apache Spark and PySpark

Install Spark only when the Data Pipeline service will execute Spark jobs. This
release requires the Apache Spark **4.1.2** binary distribution built with
Scala **2.13**, JDK **21**, and its bundled PySpark/Py4J archives. Spark 4 uses
Scala 2.13; obtain the approved 4.1.2 archive from the [Apache Spark release
page](https://spark.apache.org/releases/spark-release-4-1-2.html) and verify
its checksum/signature according to the [Apache download instructions](https://spark.apache.org/downloads/).

1. Install the customer-approved JDK 21. Open a new PowerShell window and run
   `java -version`; it must report version 21.
2. Create the installation and data folders below. Copy the approved
   `winutils.exe` helper into `C:\DEPO\runtime\hadoop\bin`. It is required by
   the Windows runtime check and must come from the customer's approved Hadoop
   helper bundle.
3. Save the verified Spark archive as
   `C:\DEPO\downloads\spark-4.1.2-bin-hadoop3.tgz`, then extract it.

```powershell
New-Item -ItemType Directory -Force C:\DEPO\downloads, C:\DEPO\runtime, C:\DEPO\data\spark-output, C:\DEPO\runtime\hadoop\bin | Out-Null
# Copy the customer-approved helper to this exact location before continuing:
# C:\DEPO\runtime\hadoop\bin\winutils.exe
tar -xf C:\DEPO\downloads\spark-4.1.2-bin-hadoop3.tgz -C C:\DEPO\runtime
Get-Item C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\bin\spark-submit.cmd,
  C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\python\lib\pyspark.zip,
  C:\DEPO\runtime\hadoop\bin\winutils.exe
```

Do not run a separate `pip install pyspark`; the service uses the PySpark and
Py4J libraries included in this Spark distribution. Add the resulting paths to
the root `.env.local` in section 2.3, then run the Spark smoke test in section
5. Spark jobs remain governed by the Data Pipeline service and cannot write
Neo4j directly.

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

### 2.1 Create the root server file

From the repository root, run this command once. It copies the server template
and generates distinct API-key values without printing them:

```powershell
if (-not (Test-Path .env.local)) {
  powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1
}
```

Open the new root `.env.local` and edit these values in order:

1. Set `DEPO_DATABASE_URL` to the PostgreSQL connection URL and
   `DEPO_DATABASE_SCHEMA=semantic` (or the customer-approved schema).
2. Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS` and `NEO4J_DATABASE`. Aura
   exports named `NEO4J_USERNAME` and `NEO4J_PASSWORD` are also accepted by
   the Spark connector, but use the canonical `NEO4J_USER` and `NEO4J_PASS`
   names in this file so every service and script has one consistent setting.
3. Set `ALLOWED_ORIGINS=https://<customer-frontend-host>` and
   `OSLC_BASE_URL=https://<customer-api-host>`.
4. Keep `AUTH_MODE=token`. This delivery uses API keys; it does not require
   Entra or GitHub Actions. Do not replace the generated token values unless
   the customer secret-management process supplies approved replacements.
5. Leave all `DEPO_SPARK_*` values out until step 2.3 unless Spark is part of
   this installation.

The shared parser rejects duplicate keys before changing the process
environment. Edit a key in place; never append another line with the same key.

### 2.2 Create the frontend browser file

Create this file once, then set the public API gateway URL **before** running
the frontend build. A browser can read every `VITE_*` value, so this file must
contain no credentials.

```powershell
if (-not (Test-Path .\frontend\.env.local)) {
  Copy-Item .\frontend\.env.example .\frontend\.env.local
}
notepad .\frontend\.env.local
```

For a customer deployment, set this single line and leave the individual
service URLs commented unless the customer deliberately exposes separate
gateway routes:

```text
VITE_API_GATEWAY_URL=https://api.customer.example
```

For a local developer installation, leave `VITE_API_GATEWAY_URL` empty. The
frontend then uses the local service ports listed in `infra/deployment/services.json`.

### 2.3 Add optional Spark settings to the root server file

For Spark, merge only the required values from `config/spark.env.example` into
the existing **root** `.env.local`. Do not create `spark.env.local`.
Add these values after the database and Neo4j settings:
`DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`, `DEPO_HADOOP_HOME`,
`DEPO_SPARK_OUTPUT_ROOT` and `DEPO_SPARK_MASTER`.

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
  DEPO_PIPELINE_SCHEDULER_ENABLED = 'false'
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

Set feature flags to `true` only after the Spark smoke test passes. Edit existing
keys instead of appending duplicates; duplicate keys fail validation.

### 2.4 Confirm the two files before installation

Run this check. It must show the root server file and the frontend browser file;
it must not show a `backend/.env.local` or a `spark.env.local`.

```powershell
Get-Item .\.env.local, .\frontend\.env.local | Select-Object FullName, Length, LastWriteTime
```

## 3. Install the applications

Install Python 3.11+, Node.js 24+ and npm 10.2+. The installer creates the fixed
`backend/.dt_venv`, installs backend dependencies, runs `npm ci`, and builds the
frontend into `frontend/dist`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1 -CheckPrerequisites
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1
if ($LASTEXITCODE -ne 0) { throw 'Application installation failed.' }
```

Use `-Development` when installing test dependencies and `-SkipFrontend` only
for a backend-only development install. The installer does not provision either
database or Spark.

## 4. Initialize and verify PostgreSQL

Start the customer PostgreSQL service or managed database first. Apply migrations
and verify the complete application contract:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action InitializeDatabase -EnvFile .env.local
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\initialize-depo-schema.ps1 -EnvFile .env.local -CheckOnly
```

The check covers eight tables, one view, forty required columns/types and the
recorded migration versions. The executable table scripts are in
`infra/postgres/migrations/`, one versioned SQL file per migration. The complete
column reference is in `infra/postgres/SCHEMA.md`; that file is a schema reference, not a competing
installation guide. Do not edit migration history or drop customer tables to
hide a mismatch.

## 5. Verify Neo4j and Spark

After installing the backend environment, verify Neo4j authentication, TLS and
the configured database with a read-only query:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-neo4j.ps1 -EnvFile .env.local -Production
```

When Spark is enabled, run the actual DataFrame smoke job. To test the optional
Neo4j Spark connector, add `-Neo4jConnector`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local -Neo4jConnector
```

## 6. Start and validate

Start the ten APIs and the outbox worker. Spark, the event scheduler and the
Neo4j connector are opt-in and require Spark runtime validation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -Profile Production
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Validate -EnvFile .env.local -Profile Production
```

For Spark-enabled operation, add `-EnableSpark`; add
`-EnablePipelineScheduler` or `-EnableNeo4jSparkConnector` only when required.
Serve `frontend/dist` through the customer's HTTPS web server and configure its
API proxy to the internal services. The browser UI supports Bridge preview,
mapping review, approval, job telemetry, graph exploration and evidence-backed
agentic retrieval. Private publication credentials remain server-side.

For a temporary local browser check, serve the built directory with Vite:

```powershell
Push-Location frontend
npm.cmd run preview -- --host 127.0.0.1 --port 4173
Pop-Location
```

Open `http://127.0.0.1:4173`. A customer deployment must use its managed HTTPS
web server, certificate and reverse-proxy configuration.

## 7. Production acceptance

Run the release preflight after a successful start:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action ReleasePreflight -EnvFile .env.local -Profile Production
```

Record the approved runtime inventory, dependency lock, frontend build, database
schema check, Neo4j read/write acceptance, backup/restore drill, Spark smoke test
when enabled, all service readiness checks, API-key rejection tests, browser
workflow, process supervision, reboot recovery, monitoring and rollback evidence.
Live customer provisioning and recovery evidence is required before release.

For service ownership and API ports, use `infra/deployment/services.json`. For
operational support, use the scripts under `infra/windows/`; they are referenced
by the commands above and are not separate installation guides.

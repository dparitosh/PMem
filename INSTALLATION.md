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

Record that exact service name. You will set
`DEPO_POSTGRES_MODE=service` and `DEPO_POSTGRES_SERVICE_NAME=<that-name>` in
the root `.env.local` in section 2.1, which allows the lifecycle launcher to
start and check the local database. For a managed or remote PostgreSQL server,
keep `DEPO_POSTGRES_MODE=external` and leave the service name blank.

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

Install Spark only when the Data Pipeline service will execute Spark jobs. The
application validates one fixed layout: **Spark 4.1.2**, **Scala 2.13**, **JDK
21**, the bundled PySpark/Py4J libraries, and the Windows Hadoop helper. Follow
the commands below from an Administrator PowerShell window.

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

# Obtain winutils.exe from the customer-approved Hadoop helper package and copy it here.
# Do not download an unverified winutils.exe from an arbitrary public repository.
Copy-Item 'C:\Path\From\Approved\Hadoop\Helper\winutils.exe' 'C:\DEPO\runtime\hadoop\bin\winutils.exe'

Get-Item "$sparkHome\bin\spark-submit.cmd",
  "$sparkHome\python\lib\pyspark.zip",
  "$sparkHome\jars\spark-core_2.13-4.1.2.jar",
  'C:\DEPO\runtime\hadoop\bin\winutils.exe',
  "$jdkHome\bin\java.exe"
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

Continue with the database initialization in section 4, then start services in
section 6 with `-EnableSpark`. Spark jobs remain governed by the Data Pipeline
service and cannot write Neo4j directly. Add `-EnableNeo4jSparkConnector` only
after the regular smoke test passes and the Neo4j connector check in section 5
succeeds.

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
   `DEPO_DATABASE_SCHEMA=semantic` (or the customer-approved schema). For the
   local Windows service installed in section 1.1, also set
   `DEPO_POSTGRES_MODE=service` and `DEPO_POSTGRES_SERVICE_NAME` to the exact
   Windows service `Name`. For a managed or remote database, retain
   `DEPO_POSTGRES_MODE=external` and leave `DEPO_POSTGRES_SERVICE_NAME` empty.
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
} | Format-List
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

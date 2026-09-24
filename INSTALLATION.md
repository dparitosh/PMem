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

If PostgreSQL is hosted on another VM, do **not** install PostgreSQL or set a
Windows PostgreSQL service name on the DEPO application VM. Ask the DBA to
create the database, role, and `semantic` schema on the database VM, permit the
application VM's private IP on port `5432`, and provide the CA certificate.
Configure the application VM as follows:

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
DEPO_DATABASE_URL=postgresql://depo_app:URL_ENCODED_PASSWORD@postgres-db.internal.example:5432/depo?sslmode=verify-full
```

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
SELECT current_database(), current_user, current_schema();
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'semantic'
ORDER BY table_name;
```

The first query must show `depo`, `depo_app`, and the expected schema. The
second confirms that the application schema is reachable. A pgAdmin connection
proves PostgreSQL network access and credentials only; continue with the ODBC
test below when another Windows application requires ODBC.

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
the customer root CA if offered. Use a System DSN for a Windows service. Do not
export the DSN with a plaintext password.

Test the DSN without putting the password in command history:

```powershell
$secure = Read-Host 'PostgreSQL password' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
try {
  $cn = [System.Data.Odbc.OdbcConnection]::new("DSN=DEPO_PG_REMOTE;UID=depo_app;PWD=$plain;")
  $cn.Open(); $cmd = $cn.CreateCommand()
  $cmd.CommandText = 'select current_database(), current_user, current_schema()'
  $reader = $cmd.ExecuteReader()
  while ($reader.Read()) { '{0} / {1} / {2}' -f $reader.GetValue(0), $reader.GetValue(1), $reader.GetValue(2) }
  $reader.Close(); $cn.Close()
} finally {
  $plain = $null
  if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
```

The DEPO backend uses `DEPO_DATABASE_URL` through `psycopg`; ODBC is optional
for external Windows tools. If no driver appears, check that the 64-bit driver
was installed. A timeout indicates DNS, firewall, or port `5432` access; an SSL
error indicates a CA or hostname mismatch; an authentication error requires
the DBA to check role, password, and schema grants.

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

Run the Spark setup in this order. Do not jump directly to the final installer:

| Order | Run | Continue with |
| --- | --- | --- |
| 1 | Step A | Confirm `java -version` starts with `21` |
| 2 | Step B | Confirm both files exist under `C:\DEPO\downloads` |
| 3 | Step C | Confirm the SHA-512 and GPG checks pass |
| 4 | Step D | Confirm `spark-submit.cmd`, `pyspark.zip`, the Spark core JAR, and approved `winutils.exe` exist |
| 5 | Section 2.3 | Copy the verified paths into the root `.env.local` |
| 6 | Section 3 | Run the application installer with `-EnableSpark` |
| 7 | Section 4, then Section 5 | Initialize PostgreSQL, then test the Spark runtime and optional Neo4j connector |

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

## 3. Run the single Windows installation command

After PostgreSQL, Neo4j, optional Spark, and both `.env.local` files are ready,
run **one** PowerShell command from the repository root. This is the supported
customer installation path; do not run the individual migration, startup, or
validation scripts by hand.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo-windows.ps1 -EnvFile .env.local -Profile Production
```

For a Spark deployment, use this command instead. Add the connector and
scheduler switches only when those customer capabilities are required:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo-windows.ps1 -EnvFile .env.local -Profile Production -EnableSpark
# Optional: -EnableNeo4jSparkConnector -EnablePipelineScheduler
```

The installer performs these stages in this fixed order and stops at the first
failure:

1. Validates Python, Node.js, npm, and the frontend lockfile.
2. Creates `backend/.dt_venv`, installs backend dependencies, runs `npm ci`,
   and builds `frontend/dist`.
3. Validates root `.env.local` and the ten-service deployment configuration.
4. Applies and verifies PostgreSQL migrations.
5. Verifies Neo4j TLS, authentication, and database access.
6. When enabled, validates Spark/JDK/Hadoop paths and runs the DataFrame smoke
   job before services are started.
7. Starts the ten APIs and outbox worker, validates all endpoints, and seeds the
   approved baseline assets and data jobs.
8. Runs release preflight, including schema, Neo4j, Spark, and production
   configuration checks.

The command is safe to run again after correcting a failure: package installs,
migrations, validation, and baseline seeding use their existing idempotent
contracts. It does not create or overwrite `.env.local`, PostgreSQL accounts,
Neo4j accounts, Spark files, or customer secrets.

## 4. Complete customer deployment

The successful installer leaves the browser build in `frontend/dist`. Serve that
directory through the customer HTTPS web server and route its API gateway to the
internal ten services. Do not expose service ports directly to browser clients.

Record the installer output, approved runtime inventory, dependency lock,
database schema result, Neo4j evidence, Spark smoke result when enabled,
backup/restore drill, browser acceptance, process supervision, reboot recovery,
monitoring, and rollback evidence in the customer release record.

For service ownership and ports, use `infra/deployment/services.json`. The
scripts under `infra/windows/` are implementation stages used by the one
installer, not separate installation instructions.

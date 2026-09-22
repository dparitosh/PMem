# DEPO installation and release guide

This is the single installation guide for the DEPO frontend, backend, PostgreSQL,
Neo4j, Spark and PySpark. Run commands from the repository root on Windows.

## 1. Provision the customer dependencies

PostgreSQL is required. Use PostgreSQL 16 or the customer-approved supported
patch. Create a database, an application login and a schema owned by that login.
The login needs DDL privileges in its schema for the first migration and least
privilege after the schema is established. Configure TLS with `sslmode=verify-full`,
the trusted CA and a backup/restore procedure.

For a new local Windows instance, run these commands after PostgreSQL is
installed. Replace the sample password and paths with customer-approved values.

```powershell
$pgBin = 'C:\Program Files\PostgreSQL\16\bin'
$env:Path = "$pgBin;$env:Path"
psql -U postgres -h 127.0.0.1 -c "CREATE ROLE depo_app LOGIN PASSWORD 'REPLACE_WITH_A_STRONG_PASSWORD';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE depo OWNER depo_app;"
psql -U postgres -h 127.0.0.1 -d depo -c "CREATE SCHEMA semantic AUTHORIZATION depo_app;"
psql 'postgresql://depo_app:URL_ENCODED_PASSWORD@127.0.0.1:5432/depo?sslmode=verify-full' -c 'select current_database(), current_user;'
```

For a managed or existing database, ask the DBA to perform the equivalent
steps. Never paste a real password into PowerShell history or source control.

Neo4j may run on-premises, on a private VM, as a hosted self-managed server, or
in Neo4j Aura. Use the provider's actual database name. Production requires
certificate-verified TLS: `neo4j+s://` or direct `bolt+s://`. Bootstrap may use
`+ssc` or plaintext only on a controlled local network. Configure the advertised
Bolt address, certificate chain and application database account. The application
installer does not install or operate either database server.

Spark is optional. When enabled, use the approved Apache Spark 4.1.2 distribution
with Scala 2.13, JDK 21 and the matching PySpark and Py4J archives. Do not install
a second unrelated `pip install pyspark` for this packaged distribution. On
Windows, provision the approved Hadoop helper bundle containing `winutils.exe`.
Spark jobs remain governed by the Data Pipeline service and cannot write Neo4j
directly.

## 2. Create configuration

Generate one server configuration and keep it at the repository root:

```powershell
if (-not (Test-Path .env.local)) {
  powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1
}
Copy-Item .\frontend\.env.example .\frontend\.env.local -ErrorAction SilentlyContinue
```

Edit `.env.local` with the PostgreSQL URL/schema, `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASS`, `NEO4J_DATABASE`, service URLs, API keys and allowed browser origin.
Use `AUTH_MODE=token`; this delivery does not require Entra or GitHub Actions.
Keep server secrets out of `frontend/.env.local`; browser variables are public.
The shared parser rejects duplicate keys before changing the process environment.

For Spark, merge only the required values from `config/spark.env.example`:
`DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`, `DEPO_HADOOP_HOME`,
`DEPO_SPARK_OUTPUT_ROOT` and `DEPO_SPARK_MASTER`.

Example for an installation under `C:\DEPO\runtime`:

```powershell
@(
  'DEPO_SPARK_HOME=C:\DEPO\runtime\spark-4.1.2-bin-hadoop3',
  'DEPO_JAVA_HOME=C:\Program Files\Java\jdk-21',
  'DEPO_HADOOP_HOME=C:\DEPO\runtime\hadoop',
  'DEPO_SPARK_OUTPUT_ROOT=C:\DEPO\data\spark-output',
  'DEPO_SPARK_MASTER=local[2]',
  'DEPO_SPARK_ENABLED=false',
  'DEPO_SPARK_NEO4J_ENABLED=false',
  'DEPO_PIPELINE_SCHEDULER_ENABLED=false'
) | Add-Content .env.local
```

Set feature flags to `true` only after the Spark smoke test passes. Edit existing
keys instead of appending duplicates; duplicate keys fail validation.

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

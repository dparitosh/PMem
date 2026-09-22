# Application and plugin installation

The DEPO application and optional MBSE plugin are independent processes. Install
and configure them separately; start DEPO before using plugin imports.

## DEPO application

Follow the [single installation sequence](../INSTALLATION.md)
from the repository root. It covers prerequisite checks, server and browser
configuration, combined backend installation/frontend build, service startup
and validation. Configure public browser endpoints before the build.

The installer uses `backend/.dt_venv` and `frontend/node_modules`, and produces
`frontend/dist`. `-Development` includes Python test dependencies. PostgreSQL,
Neo4j and optional Java/Spark runtimes are provisioned separately. For a
remote/shared PostgreSQL database, use `-SkipPostgres` on lifecycle Start.

The application has no GitHub Actions installation dependency. Optional plugins
below have their own packages and are not installed by the DEPO installer.

## Pipeline execution configuration

### Spark runtime and smoke test

Use Spark 4.1.2 (Scala 2.13), Java 21, and the application Python runtime.
Install the official Spark binary distribution and a trusted Java distribution
on the execution host. The application installer does not download them.
Verify vendor checksums/signatures before extracting; provision the Windows
Hadoop helper from your approved runtime source, not an unverified executable.
Merge needed settings from `config/spark.env.example` into `.env.local`; the example
file is not loaded automatically. Preserve existing graph credentials and replace
the runtime-path placeholders with approved installation paths. Set `DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`,
`DEPO_HADOOP_HOME`, `DEPO_SPARK_OUTPUT_ROOT`, and `DEPO_SPARK_MASTER` for the host.

```powershell
# The smoke script loads the selected server configuration.
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local
if ($LASTEXITCODE -ne 0) { throw 'Spark smoke test failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -EnableSpark -EnablePipelineScheduler -EnableNeo4jSparkConnector
```

The connector switch requires Spark. Connector dependency resolution needs
access to an approved Maven repository/cache. Omit the connector switch when
graph reads through Spark are not needed. API health alone does not prove a
Spark job executed: `configured` means runtime files exist, `initialized` means
a session exists, and `unavailable` means required runtime files are missing.
Use smoke-job output and durable run/quality evidence for execution acceptance.

### Frontend integration and startup

The backend lifecycle script does not start a web server. After dependency
installation, configure browser-safe service URLs/origins in `frontend/.env.local`.
For local testing, the pipeline defaults to `http://127.0.0.1:8019`; gateway
deployments use `VITE_API_GATEWAY_URL` or an explicit
`VITE_DATA_PIPELINE_SERVICE_URL`. Never embed an admin key in frontend settings.

```powershell
# Separate terminal, from the repository root:
cd frontend
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
npm.cmd run dev -- --host 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000/#/data-flow` and verify health, definitions, run
details, quality and lineage. Replay additionally requires an authorized
execution identity through the gateway. This command is for local development;
customer deployments must serve `frontend/dist` with their managed static web
server and configured HTTPS/gateway authentication. Stop the local web server
with Ctrl+C. Do not expose Vite's development server as the customer web server.

Enable Spark with `-EnableSpark` on the lifecycle Start command after installing
the supported Spark/Java runtime. Use `-EnablePipelineScheduler` to enable
scheduled replay; this is separate from HTTP job execution. Configure
`DEPO_SPARK_MASTER` for the chosen runtime; its default is `local[2]`.

Job execution is still synchronous. The handler registry centralizes contracts
and trusted execution strategies; it does not introduce an asynchronous worker.
Do not configure agents to expect HTTP 202 or a durable submission queue yet.
Cluster execution also requires shared artifact access; changing the master URL
alone does not make local artifact paths available to remote executors.

New handlers belong in trusted deployed Python packages and are registered during
startup through `backend.data_pipeline_service.handlers.registry`. Deploy the
same registrations to every service process before approving definitions that
reference them. Version job definitions when contracts or behavior change.

External agents communicate through the configured API gateway. The optional
DT manifest compatibility endpoint does not execute or connect those agents.
For outbound OSLC retrieval, set `OSLC_REMOTE_BASE_URL` to the gateway base before
`/oslc`, and supply `OSLC_REMOTE_TOKEN` when required. The external DT client's
`PMEM_OSLC_GATEWAY_URL` instead ends in `/oslc`; these settings are distinct.

## MBSE plugin (MBSE, Teamcenter/SMW, Cameo preparation)

Run from `plugins/mbse_plugin` within the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Install
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Configure -IngestionUrl http://127.0.0.1:8014/api/v1
# Edit .runtime\config.json if the application uses token authentication.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Verify
```

This creates a separate venv and starts the plugin on `127.0.0.1:8020`. It contains
the MBSE importer/viewer, offline Teamcenter/SMW mapping preview, and Cameo MDK
configuration checks. It does not install Cameo, MDK, MMS, Teamcenter or Java.
Its `.runtime\config.json` contains a plaintext local token; protect that directory
and do not commit it. HTTPS, gateway exposure and secret-manager injection are
deployment responsibilities.

For a wheel, pass `-WheelPath` to the Install action. Keep the previous wheel for
rollback and run Verify after every upgrade.

## Native Cameo MDK

Native MDK installation is separate from this Python plugin. Install the official
compatible plugin ZIP through Cameo's Resource/Plugin Manager, restart Cameo, and
verify Model Development Kit is listed as installed. Then prepare the draft config:

```powershell
.runtime\venv\Scripts\python.exe -m mbse_plugin.cameo_mdk configure --config .runtime\cameo.json
.runtime\venv\Scripts\python.exe -m mbse_plugin.cameo_mdk verify --config .runtime\cameo.json
```

These checks record local paths and declared versions; they do not claim MDK/MMS
compatibility or perform synchronization.

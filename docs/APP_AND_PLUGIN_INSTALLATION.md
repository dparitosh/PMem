# Application and plugin installation

The DEPO application and optional MBSE plugin are independent processes. Install
and configure them separately; start DEPO before using plugin imports.

## DEPO application

Run from `D:\Githuv_repo\PMem`:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1
powershell -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1 -OutputPath .env.local -AuthMode token
# Edit .env.local with PostgreSQL, Neo4j, origins and customer endpoints.
powershell -ExecutionPolicy Bypass -File .\infra\deployment\test-depo-deployment.ps1 -EnvFile .env.local -Profile Bootstrap -SkipEndpointChecks
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -Profile Bootstrap
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Validate -EnvFile .env.local -Profile Bootstrap
```

The installer creates `backend\.dt_venv`, installs `backend\requirements.txt`,
and runs frontend `npm ci`. It does not install PostgreSQL, Neo4j, Java or Spark.
Pass `-SkipPostgres` to the lifecycle Start command for a remote/shared database
(it is not an installer parameter). Production deployments require
the production profile and release preflight. Disabled auth is loopback-only demo
mode.

Prerequisites: an available Python interpreter (`py`, or installer `-Python`),
Node.js satisfying `frontend/package.json` (currently >=24), npm >=10.2,
and configured PostgreSQL and graph database connectivity. Installation does
not upgrade these system dependencies automatically.

## Pipeline execution configuration

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

Run from `D:\Githuv_repo\PMem\plugins\mbse_plugin`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Install
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Configure -IngestionUrl http://127.0.0.1:8014/api/v1
# Edit .runtime\config.json if the application uses token authentication.
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Start
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Verify
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

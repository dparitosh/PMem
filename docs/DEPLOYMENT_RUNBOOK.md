# DEPO Deployment Runbook

This is the customer production runbook. The executable commands and current
service inventory are maintained in `infra/deployment`; do not expose
development ports to users.

## 1. Prepare the host

1. Install supported Python, Node.js, PostgreSQL, and Neo4j according to the
   target topology.
2. Create a least-privilege PostgreSQL application role and the `semantic`
   schema.  Confirm the database backup and restore procedure.
3. Create a least-privilege Neo4j role, target database, and backup procedure.
4. Generate `.env.local` with `infra/deployment/new-depo-deployment-config.ps1`;
   keep credentials out of source control.
5. Set customer hostnames in `ALLOWED_ORIGINS` and `OSLC_BASE_URL`.

## 2. Configure the environment

Required: `DEPO_DATABASE_URL`, `DEPO_DATABASE_SCHEMA`, Neo4j connection
settings, artifact storage, and service URLs.  For production additionally set
`AUTH_MODE=entra`, Entra configuration, and Azure API Management settings.

Set `CEIM_SERVICE_URL` to the private CEIM service address when agent workflows
need canonical normalization. The Windows launcher defaults it to local port
`8018` for development.

For CEIM graph publication, configure `GRAPH_SERVICE_URL` to the private graph
service endpoint and `CEIM_PUBLISH_APPROVAL_TOKEN` in the secret store.  A
publication calls `POST /api/v1/ceim/publications/graph`; it first performs
CEIM SHACL validation, requires an approver identity, and then delegates the
write to the graph service.  Do not use this endpoint for exploratory or
unreviewed source data.

`AUTH_MODE=disabled` is only acceptable for a loopback-only developer demo.

## 3. Build and verify before deployment

```powershell
cd D:\Githuv_repo\PMem
npm ci --prefix frontend
npm run build --prefix frontend
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action ReleasePreflight -EnvFile .env.local -Profile Production
```

For a restricted internal bootstrap deployment, use `-Bootstrap` instead of
`-Production`.  It is not a public-internet profile.

## 4. Start DEPO services

```powershell
cd D:\Githuv_repo\PMem
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local
```

The service set is schema sets (`8010`), ontology (`8011`), agentic (`8012`),
graph (`8013`), ingestion (`8014`), OSLC (`8015`), catalog (`8016`), data
products (`8017`), CEIM (`8018`), and the data-pipeline API (`8019`).  Use the service manager or scheduled
process supervisor in customer environments; the script is a direct-process
Windows deployment aid.

## 5. Publish the frontend and gateway

1. Host `frontend/dist` behind the approved HTTPS frontend hostname.
2. Register only approved OpenAPI/OData service operations in Azure API
   Management.
3. Terminate TLS and validate Entra access tokens in APIM.
4. Keep all DEPO service ports private; APIM is the sole public ingress.

## 6. Smoke test

1. Check `/healthz` on each private service.
2. Load the frontend through its customer hostname.
3. Import a small governed ontology and verify catalog, ontology, and graph
   views.
4. Verify one OSLC request, one read-only graph traversal, and one approved
   CEIM graph-publication workflow using a non-production test ontology id.
5. Record the deployed versions, configuration revision, checks, and rollback
   point.

## 7. Optional Spark execution plane

Spark is for scheduled or streamed high-volume data processing. The data-pipeline
service keeps Spark lazy and disabled by default; it initializes one local
`SparkSession` only for an enabled data job. The interactive endpoint
`POST /api/v1/pipeline/jobs/transform` is bounded to 50,000 records and returns
quality results plus ECharts-ready JSON. Configure batch jobs to write governed
artifacts and provenance through existing ingestion and graph-publication APIs.
Validate the smoke test before enabling it for a customer workload.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1

# Enables the local Spark execution plane for the data-pipeline service.
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -EnableSpark

# Also enables the supervised scheduler for approved jobs with a configured
# retained replay input and bounded retry policy.
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -EnableSpark -EnablePipelineScheduler
```

## 8. Rollback

1. Stop the new service processes and restore the previous application build.
2. Revert the deployment configuration revision.
3. Restore PostgreSQL/Neo4j only when the approved rollback plan requires it.
4. Re-run health, API, and ontology smoke tests before reopening access.

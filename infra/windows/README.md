# Windows direct-service operations

This is an operations reference for an installed application. For a clean
machine, complete the [installation sequence](../deployment/README.md) first,
including browser configuration before the frontend build.

Run the commands from the repository root. DEPO does not require Docker. Generate `.env.local` using the deployment guide and
`config/deployment.env.example`, then start services:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\start-depo-services.ps1
```

Run PowerShell as Administrator only when PostgreSQL service control requires it.
Set `DEPO_POSTGRES_MODE=external`, `service` or `portable`. Service mode starts
only `DEPO_POSTGRES_SERVICE_NAME`; portable mode uses explicitly configured
`DEPO_POSTGRES_BIN_DIR` and `DEPO_POSTGRES_DATA_DIR`. The launcher validates the
`semantic` PostgreSQL schema, and runs each DEPO microservice as a hidden local
Python process. Override those locations with `-PostgresBinDir` and
`-PostgresDataDir`. Stop them with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\stop-depo-services.ps1
```

Add `-StopPostgres` only when PostgreSQL is dedicated to DEPO and should also
be stopped. For a remote/shared database, use `-SkipPostgres` on start.

Before a customer release, run the production preflight after creating the
customer `.env.local`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-release.ps1 -Production
```

The preflight rejects the local administrator PostgreSQL URL, localhost CORS,
missing Entra authentication, non-HTTPS OSLC URLs, and insecure or unreachable
Neo4j production connections.

For an initial customer rollout without Entra or TLS, use the constrained
bootstrap profile:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-release.ps1 -Bootstrap
```

Bootstrap requires token-protected approvals plus working PostgreSQL and Neo4j,
but does not require Entra or TLS. Run it only on a restricted customer network.
`AUTH_MODE=disabled` is allowed only for an explicit loopback-only local demo.
For a clean machine, install runtime dependencies once from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1
```

The installer checks Python 3.11+, Node 24+ and npm 10.2+, creates
`backend\.dt_venv`, installs backend requirements, runs frontend `npm ci` and
builds `frontend/dist`. Use `-Development` for test dependencies or
`-CheckPrerequisites` for checks without installation. The Python environment
path is fixed to match all lifecycle scripts. Configure public browser settings
before building; follow the [complete sequence](../deployment/README.md).
The installer does not install PostgreSQL, Neo4j, Java, or Spark.

# Windows operations

Follow the [canonical installation guide](../deployment/README.md) for frontend,
backend, API-key configuration and startup. Use the [customer acceptance record](../deployment/CUSTOMER_RELEASE.md)
for production delivery. No GitHub Actions or Entra setup is required.

| Script | Purpose |
| --- | --- |
| install-depo.ps1 | Prerequisites, shared backend environment, frontend install/build |
| initialize-depo-schema.ps1 | Apply migrations and verify tables/columns; `-CheckOnly` avoids writes |
| start-depo-services.ps1 | Start ten APIs and outbox worker; validate enabled Spark runtime |
| stop-depo-services.ps1 | Stop tracked application processes |
| test-depo-release.ps1 | Database/schema and profile-specific release checks |
| test-depo-neo4j.ps1 | Verify connectivity to the selected Neo4j database |
| test-depo-spark.ps1 | Execute PySpark smoke job; `-Neo4jConnector` tests connector |

Prefer `infra/deployment/invoke-depo-lifecycle.ps1` for Start/Stop/Validate,
InitializeDatabase and ReleasePreflight. It also provisions baseline jobs/assets.
Server settings live in root `.env.local`; browser-only settings live in
`frontend/.env.local`. Do not duplicate server secrets in backend env files.

Database provisioning: [PostgreSQL](../postgres/README.md), [tables/columns](../postgres/SCHEMA.md),
[Neo4j](../neo4j/README.md). Optional compute: [Spark/PySpark](../spark/README.md).

The direct launcher is not a process supervisor. Customer operations must supply
restart/reboot recovery, TLS ingress, monitoring and backups. Administrator access
is needed only for operations such as controlling the selected PostgreSQL service.
Zeppelin is an optional operator utility, outside the supported application install;
its paths must be supplied explicitly.

# Windows direct-service operations

DEPO does not require Docker. Configure `.env.local` from
`.env.postgres.example`, then run PowerShell as Administrator:

```powershell
.\infra\windows\start-depo-services.ps1
```

The script starts either an installed PostgreSQL Windows service or the default
standalone installation at `D:\codevita\postgresql-16`, validates the
`semantic` PostgreSQL schema, and runs each DEPO microservice as a hidden local
Python process. Override those locations with `-PostgresBinDir` and
`-PostgresDataDir`. Stop them with:

```powershell
.\infra\windows\stop-depo-services.ps1
```

Add `-StopPostgres` only when PostgreSQL is dedicated to DEPO and should also
be stopped. For a remote/shared database, use `-SkipPostgres` on start.

Before a customer release, run the production preflight after creating the
customer `.env.local`:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\test-depo-release.ps1 -Production
```

The preflight rejects the local administrator PostgreSQL URL, localhost CORS,
missing Entra authentication, non-HTTPS OSLC URLs, and insecure or unreachable
Neo4j production connections.

For an initial customer rollout without Entra or TLS, use the constrained
bootstrap profile:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\test-depo-release.ps1 -Bootstrap
```

Bootstrap requires token-protected approvals plus working PostgreSQL and Neo4j,
but does not require Entra or TLS. Run it only on a restricted customer network.
`AUTH_MODE=disabled` is allowed only for an explicit loopback-only local demo.

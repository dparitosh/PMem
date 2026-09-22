# Neo4j setup

Configure Neo4j in the server `.env.local` at the project root. Use the
[combined installation guide](../infra/deployment/README.md) to generate that
file and install the application. Do not create another backend environment file.

Set these values in root `.env.local`:

```dotenv
NEO4J_URI=neo4j+s://<customer-graph-host>
NEO4J_USER=<application-user>
NEO4J_PASS=<password>
NEO4J_DATABASE=<database>
```

Use the URI and TLS settings supplied by the database administrator. PostgreSQL
and Neo4j are provisioned separately from application dependencies.

From the project root, verify the selected configuration:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-neo4j.ps1 -EnvFile .env.local
```

This is a live connection check and requires the installed backend environment
and a reachable graph database. Add `-Production` for production connection
requirements. The script loads the selected file before connecting.

Start services with the same file through
`infra/deployment/invoke-depo-lifecycle.ps1`. Restart services after changing
credentials. Browser configuration in `frontend/.env.local` must contain only
public endpoints, never database credentials.

See [configuration behavior](NEO4J_CENTRALIZED_CONFIG.md) for Python callers and
legacy compatibility details.

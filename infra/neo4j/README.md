# Neo4j provisioning: on-premises and off-premises

Choose one graph deployment. The application installer installs the Python
driver, not a Neo4j server. The lifecycle scripts never install, start or stop
Neo4j. Both models use the same four root `.env.local` settings and graph service.

| Deployment | Production URI | Who operates the database |
| --- | --- | --- |
| On-premises Windows server or private VM | `neo4j+s://graph.customer.example:7687` or direct `bolt+s://graph.customer.example:7687` | Customer DBA |
| Off-premises self-managed server | Same verified-TLS URI patterns, with reachable advertised addresses | Customer/cloud operations |
| Neo4j Aura | Provider-issued `neo4j+s://…databases.neo4j.io` URI | Aura plus customer access/backup administration |

Production validation consistently requires certificate-verified TLS (`+s`).
Self-signed acceptance (`+ssc`) and plaintext `bolt://` / `neo4j://` are limited
to the Bootstrap profile. A private CA must be trusted by the Python service
account and, if used, the Spark JVM. Do not disable verification to make the
connection work. URI scheme behavior is documented in the
[Neo4j driver connection guide](https://neo4j.com/docs/python-manual/current/connect-advanced/).

## On-premises or self-managed installation

1. Select a customer-approved Neo4j version/edition and its supported Java
   runtime. Record them with the release; this repository pins a driver range,
   not a certified server distribution. Obtain the signed/vendor-verified package.
2. Extract it into a permanent binary location. Keep database files, configuration,
   certificates and backups in persistent customer-owned directories.
3. Configure the native database credentials through the DBA's protected setup
   procedure. Assign an application account and the actual database name; edition
   and licensing determine available database/role administration features.
4. Register the server using its `bin\neo4j windows-service install` command and
   configure the service account, startup and recovery policy. Apply configuration
   changes with the vendor's service update/restart procedure. See the
   [Windows installation guide](https://neo4j.com/docs/operations-manual/current/installation/windows/).
5. Configure the Bolt listener and advertised hostname. Application hosts must
   resolve and reach advertised routing addresses. Restrict database access to
   the application network; Browser/administration access is separate.
6. Configure the Bolt SSL policy and set `server.bolt.tls_level=REQUIRED`. Use a
   certificate matching the hostname, with its chain and protected private key.
   Follow the selected server version's
   [SSL configuration guide](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/).
7. Start the database, then run the application connection check below. Record
   backup/restore, restart and publication-permission acceptance evidence.

## Aura / hosted database

Create or select the customer's instance, wait until it is running, and use its
connection details. Map provider names `NEO4J_USERNAME` and `NEO4J_PASSWORD` to
this application's `NEO4J_USER` and `NEO4J_PASS`. Set `NEO4J_DATABASE` to the actual
database supplied by the provider/DBA; do not derive it from an instance ID or
assume that every instance has the same database name. Aura does not require a
local Neo4j server or a local Java installation for ordinary Python API access.

## Application configuration and verification

```dotenv
NEO4J_URI=neo4j+s://<graph-host>:7687
NEO4J_USER=<application-login>
NEO4J_PASS=<application-password>
NEO4J_DATABASE=<actual-database-name>
```

Store credentials only in the root server configuration or secret manager.
After installing backend dependencies, run from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-neo4j.ps1 -EnvFile .env.local -Production
if ($LASTEXITCODE -ne 0) { throw 'Neo4j verification failed.' }
```

This verifies authentication and a read in the configured database using
`RETURN 1`; it does not scan customer nodes or publish data. Graph publication
additionally needs the application account to create constraints and write
nodes/relationships. The graph service creates its publication constraints;
test an approved publication on an acceptance dataset before release. A successful
read check alone does not demonstrate these write privileges. PostgreSQL owns
relational tables; Neo4j stores graph nodes, properties, relationships and indexes.

If Spark's optional Neo4j connector is enabled, also run the
[connector smoke test](../spark/README.md); Python driver connectivity does not
verify the JVM's network and certificate trust configuration.

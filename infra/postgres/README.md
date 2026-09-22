# PostgreSQL provisioning

PostgreSQL is required. The application installer installs its Python driver,
not the database server. Use a customer-managed PostgreSQL instance or provision
a dedicated Windows installation before starting DEPO. PostgreSQL 16 is the
release baseline; use a customer-approved supported patch and record its exact
version in the acceptance record.

## Customer-managed database

Have the DBA provision a database, an application login and a schema owned by
that login. The application currently creates/migrates its own tables and views,
so it needs DDL privileges in that schema; a read/write-only role is insufficient.
Do not grant superuser, role-management, replication or database-creation rights.
Configure root `.env.local`:

```dotenv
DEPO_POSTGRES_MODE=external
DEPO_DATABASE_URL=postgresql://depo_app:<URL-encoded-password>@<database-host>:5432/depo?sslmode=verify-full
DEPO_DATABASE_SCHEMA=semantic
```

Install the customer's trusted PostgreSQL CA certificate for libpq (or set
`PGSSLROOTCERT` to its absolute path). TLS hostname verification must match the
database certificate. Configure firewall/HBA rules for the application hosts,
password authentication, backups and restore testing with the DBA. Never put
database passwords into frontend settings or command arguments.

## Local Windows database

Obtain the PostgreSQL 16 Windows installer or binary archive through the
[official PostgreSQL Windows download page](https://www.postgresql.org/download/windows/).
Verify the vendor signature/checksum and retain the approved package/version in
the release inventory. Use the vendor installer under the customer's software
deployment process; it can create the cluster and Windows service. Do not run
`initialize-depo-postgres.ps1` on a cluster created by that installer.

For an approved binary-only distribution, use an interactive PowerShell terminal
under the designated database account. Choose absolute paths appropriate to the
customer; the following are examples, not defaults:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\initialize-depo-postgres.ps1 -BinDir C:\DEPO\runtime\postgresql\bin -DataDir C:\DEPO\data\postgresql
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed.' }
```

This calls `initdb` with SCRAM authentication and prompts for the administrator
password. It refuses an existing data directory and never prints/stores the
password. Configure `postgresql.conf` and `pg_hba.conf` for the chosen port,
listen address, TLS certificates and application account before starting the
cluster. See [initdb documentation](https://www.postgresql.org/docs/16/app-initdb.html)
and [access rules](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html).

Start the provisioned cluster with the vendor service or, for portable operation,
the explicit cluster directory. Keep the log outside the data directory:

```powershell
& 'C:\DEPO\runtime\postgresql\bin\pg_ctl.exe' start -D C:\DEPO\data\postgresql -l C:\DEPO\logs\postgresql.log -w -t 60
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed.' }
```

Create the parent log directory first and grant access to the database account.
For continuous production operation, configure a customer-managed Windows
service with startup/recovery settings; portable process startup alone is not
reboot/crash supervision.

## Initial application database

Run the supplied SQL interactively against a fresh instance as its administrator:

```powershell
& 'C:\DEPO\runtime\postgresql\bin\psql.exe' -X -h localhost -p 5432 -U postgres -d postgres -W -f .\infra\postgres\create-depo-database.sql
if ($LASTEXITCODE -ne 0) { throw 'Database provisioning failed. Inspect existing objects before retrying.' }
```

It creates `depo_app`, prompts for its password using `\password`, creates `depo`
and the `semantic` schema. Existing objects cause failure rather than resetting
credentials. It is first-installation provisioning, not a migration or repair
script. For different names or managed services, have the DBA supply equivalent
objects and permissions instead. Retain any partially created objects after a
failure for DBA inspection; do not drop customer data automatically.

Choose exactly one startup mode in root `.env.local`:

| Mode | Additional settings | Behavior |
| --- | --- | --- |
| `external` | Database URL/schema | DEPO never starts or stops PostgreSQL |
| `service` | `DEPO_POSTGRES_SERVICE_NAME` | Starts only the named Windows service |
| `portable` | `DEPO_POSTGRES_BIN_DIR`, `DEPO_POSTGRES_DATA_DIR` | Starts only the specified initialized cluster |

No service is discovered by selecting the first installed PostgreSQL instance.
`-SkipPostgres` also prevents local database startup. Normal DEPO shutdown leaves
the database running. `stop-depo-services.ps1 -StopPostgres -EnvFile .env.local`
is for a dedicated DEPO database only and rejects external mode.

After application installation, run lifecycle Start and ReleasePreflight using
the chosen profile. These perform application schema migrations/registry writes
and live connectivity checks. Record backup/restore evidence before release.

## Application schema

After installing the application, follow [schema initialization and the complete table/column reference](SCHEMA.md). The application installer does not create a PostgreSQL login or database.

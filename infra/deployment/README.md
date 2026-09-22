# DEPO deployment automation

This folder is the deployment entry point. It keeps the service inventory,
environment validation and lifecycle commands together. The scripts do not
provision cloud infrastructure or grant permissions. Configuration scripts
generate secrets into local environment files without printing them.

## Service inventory

For a new customer server, first complete [PostgreSQL provisioning](../postgres/README.md)
and, when included, [Spark/PySpark provisioning](../spark/README.md). Use the
[customer release acceptance record](CUSTOMER_RELEASE.md) to track live checks
and outstanding delivery gates.

`services.json` is the authoritative inventory: ten HTTP services, one outbox
worker and the required health/OpenAPI/OData endpoints. It explicitly includes
CEIM and Data Pipeline, preventing an incomplete gateway registration.

## Install from the project root

Run all commands from the repository root. On a clean Windows machine, install
Python 3.11 or newer (3.11 is the recommended baseline), Node.js 24+ and npm
10.2+. Check them before installing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1 -CheckPrerequisites
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite checks failed; stop here.' }
```

The single installer owns both applications. It creates `backend/.dt_venv`, runs
frontend `npm ci`, and builds `frontend/dist`. All lifecycle scripts use this
fixed Python environment; custom virtual-environment paths are not supported.
Use `-Development` to include Python test dependencies, or `-SkipFrontend` for
backend-only installation. `-CheckPrerequisites` makes no installation changes.
It does not install PostgreSQL, Neo4j, Java or Spark. Provision PostgreSQL and Neo4j separately;
for remote/shared PostgreSQL, pass `-SkipPostgres` to lifecycle Start. Use
`-Python <python-executable>` if the Windows `py` launcher is unavailable.
Use the same `-Python` argument for the check and installation commands. Package
installation requires access to approved Python and npm registries or mirrors.
Git and GitHub Actions are not required to run the supplied installation scripts.

Server templates are maintained in [`config/`](../../config/README.md). The
configuration generator uses `.env.local`, matching the lifecycle
commands below.

## Configure, install and build

Generate server configuration and copy the public browser template only for a
new setup. The commands preserve existing configuration files:

```powershell
if (-not (Test-Path -LiteralPath .env.local)) {
  powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1
  if ($LASTEXITCODE -ne 0) { throw 'Configuration generation failed; stop here.' }
}
if (-not (Test-Path -LiteralPath frontend/.env.local)) {
  Copy-Item -LiteralPath frontend/.env.example -Destination frontend/.env.local
}
```

Stop here and edit both files before running the installer:

| File | Required edits |
| --- | --- |
| Root `.env.local` | PostgreSQL URL/schema, Neo4j URI/user/password/database, allowed browser origins, OSLC URL and authentication profile |
| `frontend/.env.local` | Public gateway URL or explicit service URLs reachable by the user's browser |

Use `AUTH_MODE=token` and distinct generated API keys for both bootstrap and
production. Production requires HTTPS origins/OSLC URL and keys of at least 32
characters. Entra is optional and is not required for this deployment. The current
deployment validator requires `neo4j+s://` in the Production profile. Replace all
required placeholders. Keep the server filename `.env.local`: alternate output
names are rejected before writing configuration.

Then install both applications and build the configured frontend:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo.ps1
if ($LASTEXITCODE -ne 0) { throw 'Installation or frontend build failed; stop here.' }
```

The generator creates a unique 384-bit token for every bootstrap token and
does not print them. Preserve those generated values when editing connection,
authentication and endpoint settings. Do not commit this file. The file uses plain
text environment variables because each service must read them at runtime;
production deployments should inject equivalent values from the customer secret
manager, vault or managed-identity mechanism instead of distributing `.env`.

For `AUTH_MODE=entra`, set `DEPO_TRUSTED_GATEWAY_IPS` to the private addresses
of the API gateway/reverse proxy. Services reject forwarded Entra identity
headers from every other source. Keep service listeners private; this setting
is a trust-boundary allowlist, not a replacement for network isolation.

## Validate and operate

The commands below show Bootstrap startup. Use `-Profile Production` consistently
for configuration validation, Start and Validate when deploying with Entra.
`-SkipEndpointChecks` validates configuration without connecting to services.
Start launches services, validates endpoints and then provisions baseline assets
and jobs; use `-SkipBaselineProvisioning` when those assets are managed separately.
For remote/shared PostgreSQL add `-SkipPostgres` to Start. For a local installation
without a Windows service, supply `-PostgresBinDir` and `-PostgresDataDir` rather
than relying on automatic discovery. Set `DEPO_POSTGRES_MODE` explicitly to
`external`, `service` or `portable`. Existing deployments must add this setting;
service mode also requires the exact `DEPO_POSTGRES_SERVICE_NAME`. The default
template uses external mode and never starts/stops a database automatically.

### Admin maintenance key (existing installations)

Run from the repository root. This preserves all existing settings and preserves
an existing key unless `-Rotate` is explicitly supplied:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\set-depo-admin-key.ps1 -EnvFile .env.local
```

New `.env.local` configurations receive this key automatically. It is a separate
384-bit credential for `X-API-Key` on protected admin operations; it does not
replace the normal service authentication token. Restart backend services with
the same environment file after generating or rotating it. Existing clients
must use the new value following rotation.

Do not paste the key into tickets, logs, chat, Git, or `VITE_*` / `REACT_APP_*`
settings: those frontend settings are public browser-bundle contents. For customer
UI maintenance, use a trusted gateway that authenticates and authorizes the
administrator before injecting the backend key. Local operators can load the key
from `.env.local` for a maintenance request without printing it. Missing keys must
not be worked around by disabling authentication.

Deployment-injected environment variables take precedence over legacy
`backend/.env` defaults. If a key is rejected after rotation, verify the listener
belongs to the restarted service and uses the selected environment file; do not
copy conflicting keys across multiple environment files.

The environment file is plaintext, not encrypted. Restrict access using Windows
file permissions; production installations should inject the key from a secret
manager. `-ExecutionPolicy Bypass` applies only to this PowerShell process and does
not disable API authentication or permanently change system execution policy.

```powershell
# Validate settings and the manifest without requiring running services
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\test-depo-deployment.ps1 -EnvFile .env.local -Profile Bootstrap -SkipEndpointChecks
if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed; stop here.' }

# Start services, then validate all health, readiness, OpenAPI 3.0.3 and OData contracts
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -Profile Bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Service startup or validation failed; inspect logs before continuing.' }

# Run local or customer-network contract validation after a restart
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Validate -EnvFile .env.local -Profile Bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Endpoint validation failed.' }

```

Release preflight connects to PostgreSQL and Neo4j. It performs a PostgreSQL
registry write/migration check; it is not an offline or read-only check. Use the
profile matching the installation (`Bootstrap` or `Production`):

```powershell

# Validate production requirements before release
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action ReleasePreflight -EnvFile .env.local -Profile Production
if ($LASTEXITCODE -ne 0) { throw 'Production preflight failed.' }
```

Shutdown is a separate operation, not the final step of installation:

```powershell

# Stop only DEPO child processes
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Stop
```

For Apache Spark, add `-EnableSpark`; add `-EnablePipelineScheduler` only when
Spark is enabled. Spark executors still cannot write to the graph directly.

## Frontend

The lifecycle command starts backend processes only. The installer has already
built `frontend/dist` using the browser settings prepared above. After later
browser configuration changes, run `npm.cmd run build` from `frontend/`. Serve `frontend/dist` through
the customer's managed HTTPS web server. For local development, run
`npm.cmd run dev -- --host 127.0.0.1 --port 3000` in a separate terminal.
Browser configuration must never contain server credentials. See the
[frontend guide](../../frontend/README.md).

## Troubleshooting and acceptance

- Missing Python/npm: install the prerequisites, open a new shell and rerun
  `-CheckPrerequisites`; use `-Python` for an interpreter not on PATH.
- An incompatible existing virtual environment: preserve any local work, recreate
  `backend/.dt_venv` with the supported Python, and rerun the installer.
- Package or build failure: stop at the failing command; do not start a partial
  installation. Check registry access and the installer output.
- Startup failure: inspect `logs/` and validate the selected database settings.
  Start may have launched some processes before failing; use Stop before retrying.
- Wrong browser endpoints: edit `frontend/.env.local`, rebuild and redeploy the
  contents of `frontend/dist`.

Acceptance requires a successful dependency install/build, service endpoint
validation, profile-appropriate release preflight and a browser smoke test via
the configured web server/gateway. The isolated tests in
`test-config-generation.ps1` and `../windows/test-install-prerequisites.ps1`
exercise script behavior only; they do not certify a live deployment.

## Azure API Management

`infra/azure-apim/register-depo-apis.ps1` and
`test-depo-service-contracts.ps1` now register and test all ten HTTP services,
including CEIM and Data Pipeline, with their matching OData discovery APIs.
Run them from APIM's private network path after this folder's validation passes.

## Explicit local insecure demo

Only a loopback-only developer demonstration may run without API security.
The service code rejects non-loopback requests even in this mode. Create the
configuration explicitly, then validate it with the separate confirmation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1 -OutputPath .env.local -AuthMode disabled -ConfirmInsecureLocalDemo
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action ReleasePreflight -EnvFile .env.local -Profile Bootstrap -LocalInsecureDemo
```

Never use this mode on a LAN, VPN, cloud VM, APIM backend or customer network.

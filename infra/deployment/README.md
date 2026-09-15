# DEPO deployment automation

This folder is the deployment entry point. It keeps the service inventory,
environment validation and lifecycle commands together. The scripts do not
provision cloud infrastructure or grant permissions. Configuration scripts
generate secrets into local environment files without printing them.

## Service inventory

`services.json` is the authoritative inventory: ten HTTP services, one outbox
worker and the required health/OpenAPI/OData endpoints. It explicitly includes
CEIM and Data Pipeline, preventing an incomplete gateway registration.

## Configure a deployment

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1 -OutputPath .env.local
```

The generator creates a unique 384-bit token for every bootstrap token and
does not print them. Edit only the customer-managed PostgreSQL and Neo4j
credentials and deployment URLs. Do not commit this file. The file uses plain
text environment variables because each service must read them at runtime;
production deployments should inject equivalent values from the customer secret
manager, vault or managed-identity mechanism instead of distributing `.env`.

For `AUTH_MODE=entra`, set `DEPO_TRUSTED_GATEWAY_IPS` to the private addresses
of the API gateway/reverse proxy. Services reject forwarded Entra identity
headers from every other source. Keep service listeners private; this setting
is a trust-boundary allowlist, not a replacement for network isolation.

## Validate and operate

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
powershell -ExecutionPolicy Bypass -File .\infra\deployment\test-depo-deployment.ps1 -EnvFile .env.local -Profile Bootstrap -SkipEndpointChecks

# Start services, then validate all health, readiness, OpenAPI 3.0.3 and OData contracts
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local

# Run local or customer-network contract validation after a restart
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Validate -EnvFile .env.local

# Validate production requirements before release
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action ReleasePreflight -EnvFile .env.local -Profile Production

# Stop only DEPO child processes
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Stop
```

For Apache Spark, add `-EnableSpark`; add `-EnablePipelineScheduler` only when
Spark is enabled. Spark executors still cannot write to the graph directly.

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
powershell -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1 -OutputPath .env.local -AuthMode disabled -ConfirmInsecureLocalDemo
powershell -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action ReleasePreflight -EnvFile .env.local -Profile Bootstrap -LocalInsecureDemo
```

Never use this mode on a LAN, VPN, cloud VM, APIM backend or customer network.

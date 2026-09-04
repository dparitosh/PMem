# DEPO deployment automation

This folder is the deployment entry point. It keeps the service inventory,
environment validation and lifecycle commands together. The scripts do not
write secrets, provision cloud infrastructure or grant permissions.

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

## Validate and operate

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

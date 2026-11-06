<#
.SYNOPSIS
Read-only analytics/product/catalog API smoke checks after service startup.
.DESCRIPTION
Reads the selected environment file. Checks configuration, PostgreSQL schema,
protected list APIs and pagination. It never creates a product or starts a job.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local', [switch]$Gateway, [switch]$RequireWorker)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'process-control.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $values['GRAPH_READ_TOKEN']) { throw 'GRAPH_READ_TOKEN is required in the selected environment file.' }
$headers = @{ Authorization = "Bearer $($values['GRAPH_READ_TOKEN'])" }
if ($Gateway) {
  if ($values['DEPO_ROUTING_MODE'] -ne 'gateway') { throw '-Gateway requires DEPO_ROUTING_MODE=gateway.' }
  $routing = Resolve-DepoRouting $values
  $bases = @{ products=$routing['VITE_DATA_PRODUCT_SERVICE_URL']; catalog=$routing['VITE_CATALOG_SERVICE_URL']; pipeline=$routing['VITE_DATA_PIPELINE_SERVICE_URL'] }
  if ($values['DEPO_APIM_SUBSCRIPTION_KEY']) { $headers['Ocp-Apim-Subscription-Key'] = $values['DEPO_APIM_SUBSCRIPTION_KEY'] }
} else {
  $bindHost = if ($values['DEPO_SERVICE_HOST']) { $values['DEPO_SERVICE_HOST'] } else { '127.0.0.1' }
  $probeHost = Get-DepoProbeHost $bindHost
  $bases = @{ products="http://${probeHost}:8017/api/v1"; catalog="http://${probeHost}:8016/api/v1"; pipeline="http://${probeHost}:8019/api/v1" }
}
& (Join-Path $root 'infra/postgres/test-postgres-connectivity.ps1') -EnvFile $EnvFile
& (Join-Path $root 'infra/windows/initialize-depo-schema.ps1') -EnvFile $EnvFile -CheckOnly
$checks = @(
  @{ Name='products'; Route='/data-products?limit=1&offset=0'; Field='products' },
  @{ Name='catalog'; Route='/catalog/products?limit=1&offset=0'; Field='products' },
  @{ Name='pipeline'; Route='/pipeline/jobs/runs?limit=1&offset=0'; Field='runs' }
)
foreach ($check in $checks) {
  $base = $bases[$check.Name].TrimEnd('/')
  if ($base -notmatch '/api/v1$') { $base += '/api/v1' }
  try { $result = Invoke-RestMethod -Uri ($base + $check.Route) -Headers $headers -MaximumRedirection 0 -TimeoutSec 30 }
  catch { throw "Analytics check failed for $($check.Name). Check listener, route, current central read credential and service logs. Credentials and response bodies are hidden." }
  if ($null -eq $result.total -or $null -eq $result.limit -or $null -eq $result.offset -or -not $result.PSObject.Properties[$check.Field]) {
    throw "The $($check.Name) service lacks the expected pagination contract. Deploy matching backend files."
  }
  if ($result.offset -ne 0 -or $result.limit -ne 1 -or $result.total -lt 0 -or @($result.($check.Field)).Count -gt 1) {
    throw "The $($check.Name) service returned invalid pagination evidence."
  }
  Write-Host "PASS: $($check.Name) read authorization and pagination."
}
if ($RequireWorker) {
  $base = $bases.pipeline.TrimEnd('/')
  if ($base -notmatch '/api/v1$') { $base += '/api/v1' }
  try { $null = Invoke-RestMethod -Uri ($base + '/pipeline/execution-ready') -Headers $headers -MaximumRedirection 0 -TimeoutSec 30 }
  catch { throw 'Pipeline execution is not ready. Check worker heartbeat, PostgreSQL leases and execution mode.' }
  Write-Host 'PASS: pipeline execution readiness.'
}
Write-Host 'Read-only analytics service checks passed. Product publication and warehouse loading require separate approval.'

param(
  [string]$EnvFile = ".env.local",
  [switch]$Production,
  [switch]$Bootstrap,
  [switch]$LocalInsecureDemo
)

$ErrorActionPreference = "Stop"
if ($Production -and $Bootstrap) { throw 'Choose either -Production or -Bootstrap, not both.' }
if (-not $Production -and -not $Bootstrap) { $Bootstrap = $true }
if ($LocalInsecureDemo -and -not $Bootstrap) { throw 'Local insecure demo requires -Bootstrap.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
$required = @('DEPO_DATABASE_URL', 'DEPO_DATABASE_SCHEMA')
if ($Production) {
  $required += @('ALLOWED_ORIGINS', 'AUTH_MODE', 'OSLC_BASE_URL')
  if ($values['AUTH_MODE'] -notin @('token','entra')) { throw 'Production requires API-key authentication (AUTH_MODE=token) or a configured gateway identity profile.' }
  if ($values['AUTH_MODE'] -eq 'entra' -and (-not $values['DEPO_TRUSTED_GATEWAY_IPS'] -or $values['DEPO_TRUSTED_GATEWAY_IPS'] -match '<.*>')) { throw 'Gateway identity mode requires DEPO_TRUSTED_GATEWAY_IPS.' }
  & (Join-Path $root 'infra/deployment/test-depo-deployment.ps1') -EnvFile $EnvFile -Profile Production -SkipEndpointChecks
  if ($values['ALLOWED_ORIGINS'] -match 'localhost|127\.0\.0\.1') { throw 'Production ALLOWED_ORIGINS must use the customer HTTPS frontend URL.' }
  if ($values['OSLC_BASE_URL'] -notmatch '^https://') { throw 'Production OSLC_BASE_URL must be an HTTPS customer URL.' }
}
if ($Bootstrap) {
  $required += @('AUTH_MODE', 'NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASS', 'NEO4J_DATABASE')
  if ($values['AUTH_MODE'] -notin @('token', 'entra', 'disabled')) { throw 'Bootstrap requires AUTH_MODE=token, AUTH_MODE=entra or a loopback-only disabled-auth demo.' }
  if ($values['AUTH_MODE'] -eq 'disabled') {
    if (-not $LocalInsecureDemo) { throw 'AUTH_MODE=disabled requires -LocalInsecureDemo.' }
    if ($values['DEPO_ALLOW_INSECURE_LOCAL_AUTH'] -ne 'true' -or $values['DEPO_SERVICE_HOST'] -notin @('127.0.0.1', 'localhost', '::1')) { throw 'Disabled authentication requires DEPO_ALLOW_INSECURE_LOCAL_AUTH=true and DEPO_SERVICE_HOST=127.0.0.1, localhost or ::1.' }
  } elseif ($LocalInsecureDemo) { throw '-LocalInsecureDemo requires AUTH_MODE=disabled.' }
}
foreach ($name in $required) { if (-not $values[$name]) { throw "Missing required setting: $name" } }
if ($Production -and $values['DEPO_DATABASE_URL'] -match 'postgres:tcs12345') { throw 'Replace the local PostgreSQL administrator connection with a customer-managed least-privilege application account.' }

& (Join-Path $PSScriptRoot 'initialize-depo-schema.ps1') -EnvFile $EnvFile
if ($Production) {
  & (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') -EnvFile $EnvFile -Production
  if ($LASTEXITCODE -ne 0) { throw 'Neo4j production preflight failed.' }
}
if ($Bootstrap) {
  & (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') -EnvFile $EnvFile -Bootstrap
  if ($LASTEXITCODE -ne 0) { throw 'Neo4j bootstrap preflight failed.' }
}
Write-Host 'DEPO release preflight passed.'

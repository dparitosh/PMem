param(
  [string]$EnvFile = ".env.local",
  [string]$ManifestPath = "",
  [ValidateSet("Bootstrap", "Production")][string]$Profile = "Bootstrap",
  [switch]$SkipEndpointChecks
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $ManifestPath) { $ManifestPath = Join-Path $PSScriptRoot "services.json" }
if (-not (Test-Path $ManifestPath)) { throw "Service manifest is missing: $ManifestPath" }
$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($manifest.services.Count -ne 10) { throw "Expected 10 HTTP services in the deployment manifest." }
$ids = @($manifest.services | ForEach-Object { $_.id })
if (($ids | Sort-Object -Unique).Count -ne $ids.Count) { throw "Service manifest contains duplicate ids." }
if (($manifest.services | ForEach-Object { $_.port } | Sort-Object -Unique).Count -ne $manifest.services.Count) { throw "Service manifest contains duplicate ports." }
if (-not (($ids -contains "ceim") -and ($ids -contains "data-pipeline"))) { throw "Service manifest must include CEIM and Data Pipeline." }

$path = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path $path)) { throw "Missing environment file: $path" }
$values = @{}
Get-Content -LiteralPath $path | ForEach-Object { if ($_ -match '^\s*([^#=]+)=(.*)$') { $values[$matches[1].Trim()] = $matches[2].Trim() } }
$required = @("DEPO_DATABASE_URL", "DEPO_DATABASE_SCHEMA", "AUTH_MODE", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASS", "NEO4J_DATABASE", "ALLOWED_ORIGINS")
foreach ($name in $required) { if (-not $values[$name] -or $values[$name] -match '<.*>') { throw "Missing customer value for $name in $path" } }
if ($Profile -eq "Production") {
  if ($values.AUTH_MODE -ne "entra") { throw "Production requires AUTH_MODE=entra." }
  if ($values.ALLOWED_ORIGINS -match "localhost|127\.0\.0\.1") { throw "Production ALLOWED_ORIGINS must not use a loopback host." }
  if ($values.NEO4J_URI -notmatch '^neo4j\+s://') { throw "Production requires a secure Neo4j Aura or TLS URI (neo4j+s://)." }
  if (-not $values.DEPO_TRUSTED_GATEWAY_IPS -or $values.DEPO_TRUSTED_GATEWAY_IPS -match '<.*>') { throw "Production requires DEPO_TRUSTED_GATEWAY_IPS for trusted gateway identity forwarding." }
}
if ($Profile -eq "Bootstrap" -and $values.AUTH_MODE -notin @("token", "entra", "disabled")) { throw "Bootstrap requires AUTH_MODE=token, AUTH_MODE=entra or an explicit loopback-only disabled-auth demo." }
if ($values.AUTH_MODE -eq "disabled") {
  $hostName = if ($values.DEPO_SERVICE_HOST) { $values.DEPO_SERVICE_HOST } else { "127.0.0.1" }
  if ($Profile -ne "Bootstrap" -or $values.DEPO_ALLOW_INSECURE_LOCAL_AUTH -ne "true" -or $hostName -notin @("127.0.0.1", "localhost", "::1")) {
    throw "AUTH_MODE=disabled requires Bootstrap, DEPO_ALLOW_INSECURE_LOCAL_AUTH=true and a loopback-only DEPO_SERVICE_HOST."
  }
}
if ($values.AUTH_MODE -eq "token") {
  if (-not $values.ONTOLOGY_APPROVAL_TOKEN -or $values.ONTOLOGY_APPROVAL_TOKEN -match '<.*>') { throw 'Missing generated bootstrap token: ONTOLOGY_APPROVAL_TOKEN' }
  $tokenKeys = @("DATA_PRODUCT_APPROVAL_TOKEN", "AGENTIC_APPROVAL_TOKEN", "ARTIFACT_RETENTION_APPROVAL_TOKEN", "DATA_JOB_EXECUTION_TOKEN", "DATA_JOB_APPROVAL_TOKEN", "CEIM_PUBLISH_APPROVAL_TOKEN", "CEIM_RESOLUTION_APPROVAL_TOKEN", "SPEED_PATH_APPROVAL_TOKEN", "SPEED_EVENT_TOKEN", "SPARQL_FEDERATION_APPROVAL_TOKEN", "VOCABULARY_APPROVAL_TOKEN", "GRAPH_READ_TOKEN", "GRAPH_PUBLICATION_TOKEN", "INGESTION_WRITE_TOKEN", "CATALOG_SERVICE_TOKEN")
  foreach ($name in $tokenKeys) { if (-not $values[$name] -or $values[$name] -match '<.*>') { throw "Missing generated bootstrap token: $name" } }
}

if (-not $SkipEndpointChecks) {
  $hostName = if ($values.DEPO_SERVICE_HOST) { $values.DEPO_SERVICE_HOST } else { "127.0.0.1" }
  foreach ($service in $manifest.services) {
    foreach ($endpoint in $manifest.contract_endpoints) {
      $uri = "http://${hostName}:$($service.port)$endpoint"
      try { $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 10 } catch { throw "$($service.id) did not respond at ${uri}: $($_.Exception.Message)" }
      if ($response.StatusCode -ne 200) { throw "$($service.id) returned HTTP $($response.StatusCode) for $endpoint" }
    }
    $openapi = Invoke-RestMethod -Uri "http://${hostName}:$($service.port)/openapi.json" -TimeoutSec 10
    if ($openapi.openapi -ne "3.0.3") { throw "$($service.id) is not publishing OpenAPI 3.0.3." }
  }
}
Write-Host "DEPO deployment validation passed for $Profile using manifest $ManifestPath."

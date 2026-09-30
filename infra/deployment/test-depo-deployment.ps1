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
if ($manifest.workers.Count -ne 2) { throw "Expected the data-product outbox and data-pipeline workers in the deployment manifest." }
$ids = @($manifest.services | ForEach-Object { $_.id })
if (($ids | Sort-Object -Unique).Count -ne $ids.Count) { throw "Service manifest contains duplicate ids." }
if (($manifest.services | ForEach-Object { $_.port } | Sort-Object -Unique).Count -ne $manifest.services.Count) { throw "Service manifest contains duplicate ports." }
if (-not (($ids -contains "ceim") -and ($ids -contains "data-pipeline"))) { throw "Service manifest must include CEIM and Data Pipeline." }

$path = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path $path)) { throw "Missing environment file: $path" }
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
Assert-DepoNeo4jConfiguration -Values $values -Production:($Profile -eq 'Production')
if ($values.DEPO_POSTGRES_MODE -notin @('external','service','portable')) { throw 'Set DEPO_POSTGRES_MODE to external, service or portable.' }
if ($values.DEPO_POSTGRES_MODE -eq 'service' -and -not $values.DEPO_POSTGRES_SERVICE_NAME) { throw 'Service mode requires DEPO_POSTGRES_SERVICE_NAME.' }
if ($values.DEPO_POSTGRES_MODE -eq 'portable' -and (-not $values.DEPO_POSTGRES_BIN_DIR -or -not $values.DEPO_POSTGRES_DATA_DIR)) { throw 'Portable mode requires PostgreSQL binary and initialized data paths.' }
$sparkFlags = @('DEPO_SPARK_ENABLED','DEPO_SPARK_NEO4J_ENABLED','DEPO_SPARK_POSTGRES_ENABLED','DEPO_PIPELINE_SCHEDULER_ENABLED')
foreach ($name in $sparkFlags) {
  if ($values[$name] -and $values[$name] -notin @('true','false')) { throw "Invalid boolean setting: $name" }
}
$sparkEnabled = $values.DEPO_SPARK_ENABLED -eq 'true'
$neo4jSparkEnabled = $values.DEPO_SPARK_NEO4J_ENABLED -eq 'true'
$postgresSparkEnabled = $values.DEPO_SPARK_POSTGRES_ENABLED -eq 'true'
$schedulerEnabled = $values.DEPO_PIPELINE_SCHEDULER_ENABLED -eq 'true'
if (($neo4jSparkEnabled -or $postgresSparkEnabled -or $schedulerEnabled) -and -not $sparkEnabled) {
  throw 'Spark connectors and scheduler require DEPO_SPARK_ENABLED=true.'
}
if ($sparkEnabled) {
  Assert-DepoSparkRuntime $values.DEPO_SPARK_HOME $values.DEPO_JAVA_HOME $values.DEPO_HADOOP_HOME $values.DEPO_SPARK_OUTPUT_ROOT
  if ($postgresSparkEnabled) { Assert-DepoSparkPostgresConfiguration -Values $values }
  if ($neo4jSparkEnabled -and (-not $values.DEPO_SPARK_NEO4J_PACKAGE -or $values.DEPO_SPARK_NEO4J_PACKAGE -match '<.*>')) {
    throw 'DEPO_SPARK_NEO4J_PACKAGE is required when the Spark Neo4j connector is enabled.'
  }
}
$required = @("DEPO_DATABASE_URL", "DEPO_DATABASE_SCHEMA", "AUTH_MODE", "NEO4J_URI", "NEO4J_DATABASE", "ALLOWED_ORIGINS")
$neo4jAuthMode = if ($values.NEO4J_AUTH_MODE) { $values.NEO4J_AUTH_MODE } else { 'token' }
if ($neo4jAuthMode -ne 'none') { $required += @('NEO4J_USER', 'NEO4J_PASS') }
foreach ($name in $required) { if (-not $values[$name] -or $values[$name] -match '<.*>') { throw "Missing customer value for $name in $path" } }
$allowedOrigins = @($values.ALLOWED_ORIGINS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
foreach ($origin in $allowedOrigins) {
  $parsedOrigin = $null
  if (-not [Uri]::TryCreate($origin, [UriKind]::Absolute, [ref]$parsedOrigin) -or
      $parsedOrigin.Scheme -notin @('http','https') -or
      $parsedOrigin.GetLeftPart([UriPartial]::Authority) -ne $origin) {
    throw "Invalid ALLOWED_ORIGINS entry '$origin'. Use an exact origin such as http://127.0.0.1:3000 with no path or trailing slash."
  }
}
if ($Profile -eq "Production") {
  if ($values.AUTH_MODE -notin @('token', 'entra')) { throw 'Production requires API-key authentication (AUTH_MODE=token) or a configured gateway identity profile.' }
  if ($values.ALLOWED_ORIGINS -match "localhost|127\.0\.0\.1") { throw "Production ALLOWED_ORIGINS must not use a loopback host. This configuration is local/bootstrap; rerun with -Profile Bootstrap, or configure the customer's HTTPS frontend origin." }
  foreach ($origin in $values.ALLOWED_ORIGINS.Split(',')) {
    if ($origin.Trim() -notmatch '^https://') { throw 'Production ALLOWED_ORIGINS must contain HTTPS origins only.' }
  }
  if ($values.AUTH_MODE -eq 'entra' -and (-not $values.DEPO_TRUSTED_GATEWAY_IPS -or $values.DEPO_TRUSTED_GATEWAY_IPS -match '<.*>')) { throw "Gateway identity mode requires DEPO_TRUSTED_GATEWAY_IPS." }
  if ($values.DEPO_PIPELINE_EXECUTION_MODE -ne 'worker') { throw 'Production requires DEPO_PIPELINE_EXECUTION_MODE=worker so Spark jobs do not execute inside HTTP requests.' }
  if (-not $values.ARTIFACT_STORAGE -or -not [System.IO.Path]::IsPathRooted($values.ARTIFACT_STORAGE)) { throw 'Production requires an absolute ARTIFACT_STORAGE path accessible to the API and pipeline worker.' }
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
  foreach ($name in ($tokenKeys + 'ONTOLOGY_APPROVAL_TOKEN')) {
    if (-not $values[$name] -or $values[$name] -match '<.*>') { throw "Missing API key: $name" }
    if ($Profile -eq 'Production' -and $values[$name].Length -lt 32) { throw "Production API key must be at least 32 characters: $name" }
  }
}

if (-not $SkipEndpointChecks) {
  $hostName = if ($values.DEPO_SERVICE_HOST) { $values.DEPO_SERVICE_HOST } else { "127.0.0.1" }
  if ($hostName -in @('0.0.0.0','::')) { $hostName = '127.0.0.1' }
  if ($hostName.Contains(':') -and -not $hostName.StartsWith('[')) { $hostName = '[' + $hostName + ']' }
  foreach ($service in $manifest.services) {
    $corsChecked = $false
    foreach ($endpoint in $manifest.contract_endpoints) {
      $uri = "http://${hostName}:$($service.port)$endpoint"
      try { $response = Invoke-WebRequest -Uri $uri -Headers @{ Origin = $allowedOrigins[0] } -UseBasicParsing -TimeoutSec 10 } catch { throw "$($service.id) did not respond at ${uri}: $($_.Exception.Message)" }
      if ($response.StatusCode -ne 200) { throw "$($service.id) returned HTTP $($response.StatusCode) for $endpoint" }
      if (-not $corsChecked) {
        $corsOrigin = [string]$response.Headers['Access-Control-Allow-Origin']
        if ($corsOrigin -ne $allowedOrigins[0]) {
          throw "$($service.id) is running without ALLOWED_ORIGINS=$($allowedOrigins[0]). Restart the DEPO services after editing .env.local."
        }
        $corsChecked = $true
      }
    }
    $openapi = Invoke-RestMethod -Uri "http://${hostName}:$($service.port)/openapi.json" -TimeoutSec 10
    if ($openapi.openapi -ne "3.0.3") { throw "$($service.id) is not publishing OpenAPI 3.0.3." }
  }
}
Write-Host "DEPO deployment validation passed for $Profile using manifest $ManifestPath."

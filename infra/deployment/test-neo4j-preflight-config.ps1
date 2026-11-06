# Offline regression: invokes the real deployment preflight with synthetic settings.
# Does not open customer configuration, install dependencies or connect to a database.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$parent = Join-Path $root '.release-test-tmp'
$fixture = Join-Path $parent ('neo4j-preflight-' + [guid]::NewGuid().ToString('N'))
$previousUri = [Environment]::GetEnvironmentVariable('NEO4J_URI', 'Process')
try {
  New-Item -ItemType Directory -Path $fixture -Force | Out-Null
  $path = Join-Path $fixture 'selected.env'
  $lines = @(
    'AUTH_MODE=token', 'DEPO_POSTGRES_MODE=external',
    'DEPO_DATABASE_URL=postgresql://depo_app:fixture@127.0.0.1/depo', 'DEPO_DATABASE_SCHEMA=semantic',
    'NEO4J_URL=bolt+s://graph.example.com:7687', 'NEO4J_USERNAME=app', 'NEO4J_PASSWORD=fixture',
    'NEO4J_DATABASE=neo4j', 'ALLOWED_ORIGINS=http://127.0.0.1:3000', 'OSLC_BASE_URL=http://127.0.0.1:8015',
    'DEPO_PIPELINE_EXECUTION_MODE=worker', "ARTIFACT_STORAGE=$fixture"
  )
  foreach ($profile in @('ADMIN_API_KEY','DATA_PRODUCT_APPROVAL_TOKEN','AGENTIC_APPROVAL_TOKEN',
      'ARTIFACT_RETENTION_APPROVAL_TOKEN','DATA_JOB_EXECUTION_TOKEN','DATA_JOB_APPROVAL_TOKEN',
      'CEIM_PUBLISH_APPROVAL_TOKEN','CEIM_RESOLUTION_APPROVAL_TOKEN','SPEED_PATH_APPROVAL_TOKEN',
      'SPEED_EVENT_TOKEN','SPARQL_FEDERATION_APPROVAL_TOKEN','VOCABULARY_APPROVAL_TOKEN',
      'GRAPH_READ_TOKEN','GRAPH_PUBLICATION_TOKEN','INGESTION_WRITE_TOKEN','CATALOG_SERVICE_TOKEN',
      'ONTOLOGY_APPROVAL_TOKEN')) { $lines += "$profile=$([guid]::NewGuid().ToString('N'))" }
  Set-Content -LiteralPath $path -Value $lines
  & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $path -Profile Production -SkipEndpointChecks
  Add-Content -LiteralPath $path -Value 'NEO4J_URI=<customer-neo4j-uri>'
  & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $path -Profile Production -SkipEndpointChecks
  Set-Content -LiteralPath $path -Value ($lines | Where-Object { $_ -notmatch '^NEO4J_URL=' })
  $env:NEO4J_URI = 'bolt+s://inherited.example.com'
  $rejected = $false
  try {
    & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $path -Profile Production -SkipEndpointChecks
  } catch {
    if ($_.Exception.Message -notlike '*Missing Neo4j setting: NEO4J_URI*') { throw }
    $rejected = $true
  }
  if (-not $rejected) { throw 'Missing selected-file URI incorrectly fell back to an inherited setting.' }
  Set-Content -LiteralPath $path -Value ($lines + 'NEO4J_URI=bolt+s://conflicting.example.com')
  $rejected = $false
  try {
    & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $path -Profile Production -SkipEndpointChecks
  } catch {
    if ($_.Exception.Message -notlike '*Conflicting Neo4j aliases*') { throw }
    $rejected = $true
  }
  if (-not $rejected) { throw 'Preflight accepted conflicting Neo4j connection settings.' }
  Set-Content -LiteralPath $path -Value ($lines + 'DEPO_MAX_INGEST_BYTES=524288000cls')
  $rejected = $false
  try {
    & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $path -Profile Production -SkipEndpointChecks
  } catch {
    if ($_.Exception.Message -notlike '*DEPO_MAX_INGEST_BYTES must be a positive integer byte count*') { throw }
    $rejected = $true
  }
  if (-not $rejected) { throw 'Malformed ingestion limit passed deployment preflight.' }
  Write-Output 'PASS: real production preflight accepts aliases and rejects missing/conflicting selected-file settings without network access.'
} finally {
  [Environment]::SetEnvironmentVariable('NEO4J_URI', $previousUri, 'Process')
  $resolved = [IO.Path]::GetFullPath($fixture)
  if (-not $resolved.StartsWith([IO.Path]::GetFullPath($parent) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Unsafe preflight fixture cleanup path.'
  }
  if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}

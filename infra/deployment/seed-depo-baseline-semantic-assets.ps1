param(
  [string]$EnvFile = ".env.local",
  [string]$OntologyBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$settings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $OntologyBaseUrl -and $settings.ONTOLOGY_SERVICE_URL) { $OntologyBaseUrl = $settings.ONTOLOGY_SERVICE_URL.TrimEnd('/') + '/metadata-registry' }
if (-not $OntologyBaseUrl) {
  $hostName = if ($settings.DEPO_SERVICE_HOST) { $settings.DEPO_SERVICE_HOST } else { "127.0.0.1" }
  if ($hostName -in @('0.0.0.0','::')) { $hostName = '127.0.0.1' }
  if ($hostName.Contains(':') -and -not $hostName.StartsWith('[')) { $hostName = '[' + $hostName + ']' }
  $OntologyBaseUrl = "http://${hostName}:8011/api/v1/metadata-registry"
}
$assets = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "baseline-semantic-assets.json") -Raw | ConvertFrom-Json).assets
foreach ($asset in $assets) {
  try { $current = Invoke-RestMethod -Uri "$OntologyBaseUrl/assets/$($asset.asset_id)" -TimeoutSec 20 }
  catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
      $current = Invoke-RestMethod -Method Post -Uri "$OntologyBaseUrl/assets" -ContentType "application/json" -Body ($asset | ConvertTo-Json -Depth 8) -TimeoutSec 20
    } else { throw }
  }
  if ($current.version -ne $asset.version -or $current.lifecycle_status -ne "approved") { throw "Semantic baseline asset is not the expected approved release: $($asset.asset_id)" }
  Write-Host "Baseline semantic asset ready: $($current.asset_id)@$($current.version) [$($current.lifecycle_status)]"
}

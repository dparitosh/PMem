param(
  [string]$EnvFile = ".env.local",
  [string]$OntologyBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$settings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if ($settings.AUTH_MODE -ne 'disabled') {
  $routing = Resolve-DepoRouting $settings
  foreach ($key in $routing.Keys) { $settings[$key] = $routing[$key] }
}
$readHeaders = @{}
$writeHeaders = @{}
if ($settings.AUTH_MODE -ne 'disabled') {
  foreach ($key in @('GRAPH_READ_TOKEN', 'ONTOLOGY_APPROVAL_TOKEN')) {
    if (-not $settings[$key]) { throw "Baseline semantic seeding requires $key in the selected environment file." }
  }
  $readHeaders.Authorization = "Bearer $($settings.GRAPH_READ_TOKEN)"
  $writeHeaders.Authorization = "Bearer $($settings.ONTOLOGY_APPROVAL_TOKEN)"
}
if ($settings.DEPO_APIM_SUBSCRIPTION_KEY) {
  $readHeaders['Ocp-Apim-Subscription-Key'] = $settings.DEPO_APIM_SUBSCRIPTION_KEY
  $writeHeaders['Ocp-Apim-Subscription-Key'] = $settings.DEPO_APIM_SUBSCRIPTION_KEY
}
if (-not $OntologyBaseUrl -and $settings.ONTOLOGY_SERVICE_URL) { $OntologyBaseUrl = $settings.ONTOLOGY_SERVICE_URL.TrimEnd('/') + '/metadata-registry' }
if (-not $OntologyBaseUrl) {
  $hostName = if ($settings.DEPO_SERVICE_HOST) { $settings.DEPO_SERVICE_HOST } else { "127.0.0.1" }
  if ($hostName -in @('0.0.0.0','::')) { $hostName = '127.0.0.1' }
  if ($hostName.Contains(':') -and -not $hostName.StartsWith('[')) { $hostName = '[' + $hostName + ']' }
  $OntologyBaseUrl = "http://${hostName}:8011/api/v1/metadata-registry"
}
$assets = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "baseline-semantic-assets.json") -Raw | ConvertFrom-Json).assets
foreach ($asset in $assets) {
  try { $current = Invoke-RestMethod -Uri "$OntologyBaseUrl/assets/$($asset.asset_id)" -Headers $readHeaders -TimeoutSec 20 }
  catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
      $current = Invoke-RestMethod -Method Post -Uri "$OntologyBaseUrl/assets" -Headers $writeHeaders -ContentType "application/json" -Body ($asset | ConvertTo-Json -Depth 8) -TimeoutSec 20
    } else { throw }
  }
  if ($current.version -ne $asset.version -or $current.lifecycle_status -ne "approved") { throw "Semantic baseline asset is not the expected approved release: $($asset.asset_id)" }
  Write-Host "Baseline semantic asset ready: $($current.asset_id)@$($current.version) [$($current.lifecycle_status)]"
}

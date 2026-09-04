param(
  [Parameter(Mandatory = $true)][string]$OntologyServiceUrl,
  [Parameter(Mandatory = $true)][string]$GraphServiceUrl,
  [Parameter(Mandatory = $true)][string]$IngestionServiceUrl,
  [Parameter(Mandatory = $true)][string]$OslcServiceUrl,
  [Parameter(Mandatory = $true)][string]$QifServiceUrl,
  [Parameter(Mandatory = $true)][string]$AgenticServiceUrl,
  [Parameter(Mandatory = $true)][string]$CatalogServiceUrl,
  [Parameter(Mandatory = $true)][string]$DataProductsServiceUrl,
  [Parameter(Mandatory = $true)][string]$CeimServiceUrl,
  [Parameter(Mandatory = $true)][string]$DataPipelineServiceUrl
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$manifestPath = Join-Path $root "infra\deployment\services.json"
if (-not (Test-Path $manifestPath)) { throw "Deployment service manifest was not found: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

function Test-DepoService([string]$Name, [string]$ServiceUrl) {
  $baseUrl = $ServiceUrl.TrimEnd('/')
  foreach ($path in @("/healthz", "/openapi.json", "/odata/`$metadata")) {
    $response = Invoke-WebRequest -Uri "$baseUrl$path" -UseBasicParsing -TimeoutSec 20
    if ($response.StatusCode -ne 200) { throw "$Name returned HTTP $($response.StatusCode) from $path" }
  }
  Write-Host "$Name service contract is reachable."
}

$urls = @{ 'schema-sets'=$QifServiceUrl; ontology=$OntologyServiceUrl; agentic=$AgenticServiceUrl; graph=$GraphServiceUrl; ingestion=$IngestionServiceUrl; oslc=$OslcServiceUrl; catalog=$CatalogServiceUrl; 'data-products'=$DataProductsServiceUrl; ceim=$CeimServiceUrl; 'data-pipeline'=$DataPipelineServiceUrl }
foreach ($service in $manifest.services) { Test-DepoService $service.display_name $urls[$service.id] }

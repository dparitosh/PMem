param(
  [Parameter(Mandatory = $true)][string]$OntologyServiceUrl,
  [Parameter(Mandatory = $true)][string]$GraphServiceUrl,
  [Parameter(Mandatory = $true)][string]$IngestionServiceUrl,
  [Parameter(Mandatory = $true)][string]$OslcServiceUrl,
  [Parameter(Mandatory = $true)][string]$QifServiceUrl,
  [Parameter(Mandatory = $true)][string]$AgenticServiceUrl,
  [Parameter(Mandatory = $true)][string]$CatalogServiceUrl,
  [Parameter(Mandatory = $true)][string]$DataProductsServiceUrl
)

$ErrorActionPreference = "Stop"

function Test-DepoService([string]$Name, [string]$ServiceUrl) {
  $baseUrl = $ServiceUrl.TrimEnd('/')
  foreach ($path in @("/healthz", "/openapi.json", "/odata/`$metadata")) {
    $response = Invoke-WebRequest -Uri "$baseUrl$path" -UseBasicParsing -TimeoutSec 20
    if ($response.StatusCode -ne 200) { throw "$Name returned HTTP $($response.StatusCode) from $path" }
  }
  Write-Host "$Name service contract is reachable."
}

Test-DepoService "Ontology" $OntologyServiceUrl
Test-DepoService "Graph" $GraphServiceUrl
Test-DepoService "Ingestion" $IngestionServiceUrl
Test-DepoService "OSLC" $OslcServiceUrl
Test-DepoService "QIF" $QifServiceUrl
Test-DepoService "Agentic" $AgenticServiceUrl
Test-DepoService "Catalog" $CatalogServiceUrl
Test-DepoService "Data Products" $DataProductsServiceUrl

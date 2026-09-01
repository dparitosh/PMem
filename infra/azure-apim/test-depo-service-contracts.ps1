param(
  [Parameter(Mandatory = $true)][string]$OntologyServiceUrl,
  [Parameter(Mandatory = $true)][string]$GraphServiceUrl,
  [Parameter(Mandatory = $true)][string]$IngestionServiceUrl,
  [Parameter(Mandatory = $true)][string]$OslcServiceUrl
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

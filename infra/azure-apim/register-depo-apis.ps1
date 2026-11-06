param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$SubscriptionId,
  [Parameter(Mandatory = $true)][string]$ApimServiceName,
  [Parameter(Mandatory = $true)][string]$OntologyServiceUrl,
  [Parameter(Mandatory = $true)][string]$GraphServiceUrl,
  [Parameter(Mandatory = $true)][string]$IngestionServiceUrl,
  [Parameter(Mandatory = $true)][string]$OslcServiceUrl,
  [Parameter(Mandatory = $true)][string]$QifServiceUrl,
  [Parameter(Mandatory = $true)][string]$AgenticServiceUrl,
  [Parameter(Mandatory = $true)][string]$CatalogServiceUrl,
  [Parameter(Mandatory = $true)][string]$DataProductsServiceUrl,
  [Parameter(Mandatory = $true)][string]$CeimServiceUrl,
  [Parameter(Mandatory = $true)][string]$DataPipelineServiceUrl,
  [switch]$AllowAnonymous
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$manifestPath = Join-Path $root "infra\deployment\services.json"
if (-not (Test-Path $manifestPath)) { throw "Deployment service manifest was not found: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

function Assert-HttpsUrl([string]$Name, [string]$Value) {
  $uri = $null
  if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https") {
    throw "$Name must be an absolute HTTPS URL."
  }
}

Assert-HttpsUrl "OntologyServiceUrl" $OntologyServiceUrl
Assert-HttpsUrl "GraphServiceUrl" $GraphServiceUrl
Assert-HttpsUrl "IngestionServiceUrl" $IngestionServiceUrl
Assert-HttpsUrl "OslcServiceUrl" $OslcServiceUrl
Assert-HttpsUrl "QifServiceUrl" $QifServiceUrl
Assert-HttpsUrl "AgenticServiceUrl" $AgenticServiceUrl
Assert-HttpsUrl "CatalogServiceUrl" $CatalogServiceUrl
Assert-HttpsUrl "DataProductsServiceUrl" $DataProductsServiceUrl
Assert-HttpsUrl "CeimServiceUrl" $CeimServiceUrl
Assert-HttpsUrl "DataPipelineServiceUrl" $DataPipelineServiceUrl

function Register-DepoApi([string]$ApiId, [string]$Path, [string]$DisplayName, [string]$ServiceUrl) {
  $baseUrl = $ServiceUrl.TrimEnd('/')
  $subscriptionRequired = if ($AllowAnonymous) { "false" } else { "true" }
  az apim api import `
    --resource-group $ResourceGroup `
    --service-name $ApimServiceName `
    --api-id $ApiId `
    --path $Path `
    --display-name $DisplayName `
    --service-url $baseUrl `
    --specification-url "$baseUrl/openapi.json" `
    --specification-format OpenApiJson `
    --subscription-required $subscriptionRequired `
    --only-show-errors
}

function Register-DepoODataApi([string]$ApiId, [string]$Path, [string]$DisplayName, [string]$ServiceUrl) {
  $baseUrl = $ServiceUrl.TrimEnd('/')
  $subscriptionRequired = -not [bool]$AllowAnonymous
  $body = @{
    properties = @{
      type = "odata"
      format = "odata-link"
      path = $Path
      displayName = $DisplayName
      protocols = @("https")
      serviceUrl = "$baseUrl/odata"
      value = "$baseUrl/odata/`$metadata"
      subscriptionRequired = $subscriptionRequired
    }
  } | ConvertTo-Json -Depth 4 -Compress
  $uri = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.ApiManagement/service/$ApimServiceName/apis/$ApiId?api-version=2024-05-01"
  az rest --method put --uri $uri --body $body --only-show-errors
}

$urls = @{ 'schema-sets'=$QifServiceUrl; ontology=$OntologyServiceUrl; agentic=$AgenticServiceUrl; graph=$GraphServiceUrl; ingestion=$IngestionServiceUrl; oslc=$OslcServiceUrl; catalog=$CatalogServiceUrl; 'data-products'=$DataProductsServiceUrl; ceim=$CeimServiceUrl; 'data-pipeline'=$DataPipelineServiceUrl }
# Keep the generated IDs stable for APIM policies and subscriptions.
# Examples: "depo-ontology-odata" and "depo-oslc-odata".
foreach ($service in $manifest.services) {
  $url = $urls[$service.id]
  if (-not $url) { throw "Missing APIM service URL for $($service.id)." }
  Register-DepoApi "depo-$($service.id)" $service.apim_path $service.display_name $url
  Register-DepoODataApi "depo-$($service.id)-odata" "$($service.apim_path)-odata" "$($service.display_name) OData" $url
}

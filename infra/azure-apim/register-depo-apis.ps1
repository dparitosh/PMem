param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$SubscriptionId,
  [Parameter(Mandatory = $true)][string]$ApimServiceName,
  [Parameter(Mandatory = $true)][string]$OntologyServiceUrl,
  [Parameter(Mandatory = $true)][string]$GraphServiceUrl,
  [Parameter(Mandatory = $true)][string]$IngestionServiceUrl,
  [Parameter(Mandatory = $true)][string]$OslcServiceUrl,
  [switch]$AllowAnonymous
)

$ErrorActionPreference = "Stop"

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

Register-DepoApi "depo-ontology" "ontology" "DEPO Ontology Service" $OntologyServiceUrl
Register-DepoApi "depo-graph" "graph" "DEPO Graph Service" $GraphServiceUrl
Register-DepoApi "depo-ingestion" "ingestion" "DEPO Ingestion Service" $IngestionServiceUrl
Register-DepoApi "depo-oslc" "oslc" "DEPO OSLC Service" $OslcServiceUrl

Register-DepoODataApi "depo-ontology-odata" "ontology-odata" "DEPO Ontology OData" $OntologyServiceUrl
Register-DepoODataApi "depo-graph-odata" "graph-odata" "DEPO Graph OData" $GraphServiceUrl
Register-DepoODataApi "depo-ingestion-odata" "ingestion-odata" "DEPO Ingestion OData" $IngestionServiceUrl
Register-DepoODataApi "depo-oslc-odata" "oslc-odata" "DEPO OSLC OData" $OslcServiceUrl

param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$ApimServiceName,
  [Parameter(Mandatory = $true)][string]$OntologyServiceUrl,
  [Parameter(Mandatory = $true)][string]$GraphServiceUrl,
  [Parameter(Mandatory = $true)][string]$IngestionServiceUrl,
  [Parameter(Mandatory = $true)][string]$OslcServiceUrl,
  [switch]$RequireSubscription
)

$ErrorActionPreference = "Stop"

function Register-DepoApi([string]$ApiId, [string]$Path, [string]$DisplayName, [string]$ServiceUrl) {
  $baseUrl = $ServiceUrl.TrimEnd('/')
  $subscriptionRequired = if ($RequireSubscription) { "true" } else { "false" }
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

Register-DepoApi "depo-ontology" "ontology" "DEPO Ontology Service" $OntologyServiceUrl
Register-DepoApi "depo-graph" "graph" "DEPO Graph Service" $GraphServiceUrl
Register-DepoApi "depo-ingestion" "ingestion" "DEPO Ingestion Service" $IngestionServiceUrl
Register-DepoApi "depo-oslc" "oslc" "DEPO OSLC Service" $OslcServiceUrl

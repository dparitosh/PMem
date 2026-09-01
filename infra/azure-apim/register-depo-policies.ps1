param(
  [Parameter(Mandatory = $true)][string]$SubscriptionId,
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$ApimServiceName,
  [Parameter(Mandatory = $true)][string]$OpenIdConfigUrl,
  [Parameter(Mandatory = $true)][string]$Audience,
  [ValidateRange(1, 10000)][int]$RateLimitCalls = 120,
  [ValidateRange(1, 3600)][int]$RateLimitPeriodSeconds = 60
)

$ErrorActionPreference = "Stop"

function Escape-PolicyText([string]$Value) {
  return [System.Security.SecurityElement]::Escape($Value)
}

function Set-DepoApiPolicy([string]$ApiId) {
  $issuer = Escape-PolicyText $OpenIdConfigUrl
  $expectedAudience = Escape-PolicyText $Audience
  $policy = @"
<policies>
  <inbound>
    <base />
    <validate-jwt header-name="Authorization" require-scheme="Bearer" failed-validation-httpcode="401" failed-validation-error-message="Valid bearer token required.">
      <openid-config url="$issuer" />
      <audiences><audience>$expectedAudience</audience></audiences>
    </validate-jwt>
    <rate-limit-by-key calls="$RateLimitCalls" renewal-period="$RateLimitPeriodSeconds" counter-key="@(context.Subscription?.Key ?? context.Request.IpAddress)" />
    <set-header name="X-Content-Type-Options" exists-action="override"><value>nosniff</value></set-header>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
"@
  $body = @{ properties = @{ format = "rawxml"; value = $policy } } | ConvertTo-Json -Depth 5 -Compress
  $uri = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.ApiManagement/service/$ApimServiceName/apis/$ApiId/policies/policy?api-version=2024-05-01"
  az rest --method put --uri $uri --body $body --only-show-errors
}

@(
  "depo-ontology", "depo-graph", "depo-ingestion", "depo-oslc",
  "depo-ontology-odata", "depo-graph-odata", "depo-ingestion-odata", "depo-oslc-odata"
) | ForEach-Object { Set-DepoApiPolicy $_ }

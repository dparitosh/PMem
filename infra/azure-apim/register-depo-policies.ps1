<# .SYNOPSIS Applies Entra JWT policies to existing manifest APIs. Not for AUTH_MODE=token; it replaces API policies. Review and preserve custom policy requirements first. #>
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
    <set-header name="X-DEPO-Principal-Id" exists-action="override"><value>@(context.Principal.Claims.FirstOrDefault(c => c.Type == "oid")?.Value ?? context.Principal.Identity.Name)</value></set-header>
    <set-header name="X-DEPO-Roles" exists-action="override"><value>@(string.Join(",", context.Principal.Claims.Where(c => c.Type == "roles").Select(c => c.Value)))</value></set-header>
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
  if ($LASTEXITCODE -ne 0) { throw "APIM policy update failed for $ApiId; later policies were not changed." }
}

$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$manifest=Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI is required. Install it and run az login before policy registration.' }
az account set --subscription $SubscriptionId --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Cannot select the Azure subscription; no API policies were changed.' }
foreach($service in $manifest.services) {
  Set-DepoApiPolicy "depo-$($service.id)"
  Set-DepoApiPolicy "depo-$($service.id)-odata"
}

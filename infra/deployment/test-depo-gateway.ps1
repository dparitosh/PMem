<# .SYNOPSIS Verifies all ten service routes through the configured gateway. #>
[CmdletBinding()]
param([string]$EnvFile = '.env.local', [Security.SecureString]$AccessToken)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$values = Read-DepoEnvironment $root $EnvFile
if ($values['DEPO_ROUTING_MODE'] -ne 'gateway') { throw 'Gateway diagnostic requires DEPO_ROUTING_MODE=gateway.' }
$routing = Resolve-DepoRouting $values
$manifest = Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
$origin = @($values['ALLOWED_ORIGINS'].Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })[0]
if (-not $origin) { throw 'Configure ALLOWED_ORIGINS before the gateway diagnostic.' }
$headers = @{ Origin = $origin }
if ($values['DEPO_APIM_SUBSCRIPTION_KEY']) { $headers['Ocp-Apim-Subscription-Key'] = $values['DEPO_APIM_SUBSCRIPTION_KEY'] }
if ($AccessToken) {
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($AccessToken)
  try { $headers.Authorization = 'Bearer ' + [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
} elseif ($values['AUTH_MODE'] -eq 'token') {
  $headers.Authorization = 'Bearer ' + $values['GRAPH_READ_TOKEN']
} else { throw 'Entra gateway tests require -AccessToken (SecureString) containing a valid customer JWT.' }
$names = @{ 'schema-sets'='QIF'; ontology='ONTOLOGY'; agentic='AGENTIC'; graph='GRAPH'; ingestion='INGESTION'; oslc='OSLC'; catalog='CATALOG'; 'data-products'='DATA_PRODUCT'; ceim='CEIM'; 'data-pipeline'='DATA_PIPELINE' }
try {
  for ($index = 0; $index -lt $manifest.services.Count; $index++) {
    $service = $manifest.services[$index]
    $base = $routing["VITE_$($names[$service.id])_SERVICE_URL"]
    foreach ($path in @('/healthz','/readyz','/openapi.json')) {
      try { $response = Invoke-WebRequest -Uri "$base$path" -Headers $headers -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 15 }
      catch { throw "Gateway route $($service.id)$path failed. Check APIM suffix/rewrite, backend reachability, authorization and subscription policy. Response body and credentials are hidden." }
      if ($response.StatusCode -ne 200) { throw "Gateway route $($service.id)$path returned HTTP $($response.StatusCode)." }
      if ($path -eq '/openapi.json') {
        $contract = $response.Content | ConvertFrom-Json
        if ($contract.openapi -ne '3.0.3' -or -not $contract.paths) { throw "Gateway $($service.id) did not return the expected service OpenAPI contract." }
      }
    }
    $requestedHeaders = if ($values['DEPO_APIM_SUBSCRIPTION_KEY']) { 'authorization,ocp-apim-subscription-key' } else { 'authorization' }
    $preflight = @{ Origin=$origin; 'Access-Control-Request-Method'='GET'; 'Access-Control-Request-Headers'=$requestedHeaders }
    try { $cors = Invoke-WebRequest -Uri "$base/healthz" -Method Options -Headers $preflight -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 15 }
    catch { throw "Gateway browser preflight failed for $($service.id); OPTIONS must not require bearer/subscription credentials." }
    if ([string]$cors.Headers['Access-Control-Allow-Origin'] -ne $origin -or ([string]$cors.Headers['Access-Control-Allow-Headers']).ToLowerInvariant() -notmatch 'authorization') {
      throw "Gateway CORS policy does not authorize the configured browser origin and Authorization header for $($service.id)."
    }
    if ($values['DEPO_APIM_SUBSCRIPTION_KEY'] -and ([string]$cors.Headers['Access-Control-Allow-Headers']).ToLowerInvariant() -notmatch 'ocp-apim-subscription-key') { throw "Gateway $($service.id) does not allow the subscription header in browser preflight." }
    Write-Host "PASS: gateway $($service.id) health/readiness/OpenAPI and browser preflight."
  }
  try {
    Invoke-RestMethod -Uri ($routing['VITE_GRAPH_SERVICE_URL'] + '/api/v1/graph/overview?limit=1') -Headers $headers -MaximumRedirection 0 -TimeoutSec 30 | Out-Null
  } catch { throw 'Gateway protected graph read failed. Verify the forwarded bearer token and service authorization.' }
  Write-Host 'PASS: gateway protected graph read. Mutations were not executed.'
} finally { $headers.Clear(); $values.Clear() }

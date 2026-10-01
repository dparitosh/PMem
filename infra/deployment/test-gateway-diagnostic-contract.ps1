# Offline test: exercise the real diagnostic with fake HTTP responses.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$fixture = Join-Path $root ('.release-test-tmp/gateway-' + [guid]::NewGuid().ToString('N'))
$global:depoGatewayContractCalls = [Collections.Generic.List[string]]::new()
function Invoke-WebRequest {
  param($Uri, $Headers, $Method, [switch]$UseBasicParsing, $MaximumRedirection, $TimeoutSec)
  if ($Uri -notmatch '^https://gateway.example/depo/(qif|ontology|agentic|graph|ingestion|oslc|catalog|data-products|ceim|data-pipeline)/(healthz|readyz|openapi.json)$') { throw 'Incorrect gateway URI.' }
  if ($Method -eq 'Options') {
    if ($Headers.Authorization -or $Headers['Ocp-Apim-Subscription-Key']) { throw 'Preflight carries credentials.' }
  } elseif ($Headers.Authorization -ne 'Bearer fixture-read' -or $Headers['Ocp-Apim-Subscription-Key'] -ne 'fixture-subscription') { throw 'Gateway credentials missing.' }
  $global:depoGatewayContractCalls.Add([string]$Uri)
  return @{ StatusCode=200; Content='{"openapi":"3.0.3","paths":{"/api/v1/example":{}}}'; Headers=@{ 'Access-Control-Allow-Origin'='http://app.example:3000'; 'Access-Control-Allow-Headers'='authorization,ocp-apim-subscription-key' } }
}
function Invoke-RestMethod {
  param($Uri, $Headers, $MaximumRedirection, $TimeoutSec)
  if ($Uri -ne 'https://gateway.example/depo/graph/api/v1/graph/overview?limit=1' -or $Headers.Authorization -ne 'Bearer fixture-read') { throw 'Incorrect protected request.' }
  return @{}
}
try {
  New-Item -ItemType Directory -Path (Split-Path $fixture) -Force | Out-Null
  Set-Content -LiteralPath $fixture -Value @('DEPO_ROUTING_MODE=gateway','DEPO_API_GATEWAY_URL=https://gateway.example/depo','AUTH_MODE=token','ALLOWED_ORIGINS=http://app.example:3000','GRAPH_READ_TOKEN=fixture-read','DEPO_APIM_SUBSCRIPTION_KEY=fixture-subscription')
  & (Join-Path $PSScriptRoot 'test-depo-gateway.ps1') -EnvFile $fixture
  if ($global:depoGatewayContractCalls.Count -ne 40) { throw 'Not all ten service routes were checked.' }
} finally {
  Remove-Item -LiteralPath $fixture -ErrorAction SilentlyContinue
  Remove-Variable depoGatewayContractCalls -Scope Global -ErrorAction SilentlyContinue
}
Write-Host 'PASS: gateway diagnostic checks ten services, subscription/bearer headers and credential-free preflight (simulated HTTP).'

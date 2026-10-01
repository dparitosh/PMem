$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$local = Resolve-DepoRouting @{ DEPO_ROUTING_MODE='local'; AUTH_MODE='token' }
if ($local.GRAPH_SERVICE_URL -ne 'http://127.0.0.1:8013/api/v1' -or $local.VITE_DATA_PIPELINE_SERVICE_URL -ne 'http://127.0.0.1:8019') { throw 'Local mapping failed.' }
$gateway = Resolve-DepoRouting @{ DEPO_ROUTING_MODE='gateway'; DEPO_API_GATEWAY_URL='https://customer.example/depo/' }
if ($gateway.DATA_CATALOG_URL -ne 'https://customer.example/depo/catalog/api/v1' -or $gateway.VITE_CEIM_SERVICE_URL -ne 'https://customer.example/depo/ceim') { throw 'Gateway mapping failed.' }
if ((Resolve-DepoRouting @{}).Count -ne 0) { throw 'Legacy settings changed.' }
$custom = Resolve-DepoRouting @{ DEPO_ROUTING_MODE='gateway'; DEPO_API_GATEWAY_URL='https://customer.example'; DEPO_GATEWAY_GRAPH_PATH='engineering/graph' }
if ($custom.GRAPH_SERVICE_URL -ne 'https://customer.example/engineering/graph/api/v1') { throw 'Custom gateway mapping failed.' }
$bound = Resolve-DepoRouting @{ DEPO_ROUTING_MODE='local'; AUTH_MODE='token'; DEPO_SERVICE_HOST='10.0.2.16' }
if ($bound.VITE_GRAPH_SERVICE_URL -ne 'http://10.0.2.16:8013') { throw 'Bound host was not inherited.' }
$unused = Resolve-DepoRouting @{ DEPO_ROUTING_MODE='gateway'; DEPO_API_GATEWAY_URL='https://customer.example'; DEPO_LOCAL_SERVICE_HOST='<unused>' }
if (-not $unused.GRAPH_SERVICE_URL) { throw 'Unused local setting broke gateway routing.' }
foreach ($invalid in @(
  @{ DEPO_ROUTING_MODE='local'; AUTH_MODE='token'; DEPO_LOCAL_SERVICE_HOST='user@attacker.example' },
  @{ DEPO_ROUTING_MODE='invalid' },
  @{ DEPO_ROUTING_MODE='local'; AUTH_MODE='entra' },
  @{ DEPO_ROUTING_MODE='local'; AUTH_MODE='disabled' },
  @{ DEPO_ROUTING_MODE='local' },
  @{ DEPO_ROUTING_MODE='gateway'; DEPO_API_GATEWAY_URL='http:////bad' },
  @{ DEPO_ROUTING_MODE='gateway'; DEPO_API_GATEWAY_URL='https://user:password@example.com' }
  @{ DEPO_ROUTING_MODE='gateway'; AUTH_MODE='entra'; DEPO_API_GATEWAY_URL='http://customer.example' }
  @{ DEPO_ROUTING_MODE='gateway'; DEPO_API_GATEWAY_URL='https://customer.example'; DEPO_GATEWAY_GRAPH_PATH='../other' }
)) {
  $rejected = $false
  try { Resolve-DepoRouting $invalid | Out-Null } catch { $rejected = $true }
  if (-not $rejected) { throw 'Invalid routing was accepted.' }
}
Write-Host 'PASS: local, gateway, legacy and invalid routing configurations.'

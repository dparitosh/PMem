$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$fixture = Join-Path $root ('.release-test-tmp\browser-' + [guid]::NewGuid().ToString('N'))
$validator = Join-Path $PSScriptRoot 'test-depo-frontend-config.ps1'
function Assert-BrowserRejected([string[]]$Lines, [string]$Expected) {
  Set-Content -LiteralPath $fixture -Value $Lines
  $message = ''
  try { & $validator -EnvFile $fixture } catch { $message = $_.Exception.Message }
  if ($message -notlike "*$Expected*") { throw "Expected rejection for $Expected; received $message" }
}
try {
  New-Item -ItemType Directory -Path (Split-Path $fixture) -Force | Out-Null
  Set-Content -LiteralPath $fixture -Value @('VITE_API_GATEWAY_URL=', 'VITE_GRAPH_SERVICE_URL=http://127.0.0.1:8013')
  & $validator -EnvFile $fixture
  Set-Content -LiteralPath $fixture -Value 'VITE_API_GATEWAY_URL=https://customer.example/api'
  & $validator -EnvFile $fixture
  Assert-BrowserRejected @('VITE_GRAPH_SERVICE_URL=http:////127.0.0.1:8013') 'Invalid browser URL'
  Assert-BrowserRejected @('VITE_GRAPH_READ_TOKEN=fixture') 'Do not compile credentials'
  Assert-BrowserRejected @('VITE_API_GATEWAY_URL=https://<customer-host>') 'placeholder'
  Assert-BrowserRejected @('VITE_API_GATEWAY_URL=', 'VITE_API_GATEWAY_URL=') 'Duplicate'
} finally {
  if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Force }
}
Write-Host 'PASS: browser configuration validation'

# Offline: a stub npm command inspects the build environment. No packages or services run.
$ErrorActionPreference = 'Stop'
$workspace = Join-Path ([IO.Path]::GetTempPath()) ('depo-build-test-' + [Guid]::NewGuid().ToString('N'))
$previousGateway = $env:REACT_APP_API_GATEWAY_URL
$previousOverride = $env:DEPO_BROWSER_ROUTING_OVERRIDE_JSON
try {
  foreach ($folder in @('infra/windows','frontend/node_modules/.bin','frontend/dist')) {
    New-Item -ItemType Directory -Path (Join-Path $workspace $folder) -Force | Out-Null
  }
  foreach ($name in @('build-depo-frontend.ps1','runtime-config.ps1','native-install-command.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $workspace "infra/windows/$name")
  }
  # Runtime discovery is independently tested; this fixture must not require
  # a customer's installed Node binary or launch a real package build.
  Add-Content -LiteralPath (Join-Path $workspace 'infra/windows/runtime-config.ps1') -Value @'
function Get-DepoNodeRuntime {
  param([string]$Root,[string]$NodeJsDir)
  return @{Directory=$Root;Node='node';Npm='npm.cmd';Version='v24.0.0'}
}
'@
  Set-Content -LiteralPath (Join-Path $workspace 'frontend/node_modules/.bin/vite.cmd') -Value 'stub'
  Set-Content -LiteralPath (Join-Path $workspace '.env.local') -Value @('AUTH_MODE=token','DEPO_ROUTING_MODE=local')
  function global:npm.cmd {
    $routing = $env:DEPO_BROWSER_ROUTING_OVERRIDE_JSON | ConvertFrom-Json
    if ($null -eq $routing.VITE_API_GATEWAY_URL -or $routing.VITE_API_GATEWAY_URL -ne '' -or $routing.VITE_BACKEND_URL -ne '') { throw 'Empty root routing was lost.' }
    if ($routing.VITE_GRAPH_SERVICE_URL -ne 'http://127.0.0.1:8013') { throw 'Resolved service routing was lost.' }
    if (Test-Path -LiteralPath '../fail-build') { throw 'simulated build failure' }
    $global:LASTEXITCODE = 0
  }
  $env:REACT_APP_API_GATEWAY_URL = 'http://old.example'
  $env:DEPO_BROWSER_ROUTING_OVERRIDE_JSON = '{"existing":"value"}'
  $builder = Join-Path $workspace 'infra/windows/build-depo-frontend.ps1'
  & $builder
  if ($env:REACT_APP_API_GATEWAY_URL -ne 'http://old.example' -or $env:DEPO_BROWSER_ROUTING_OVERRIDE_JSON -ne '{"existing":"value"}') { throw 'Build did not restore the caller environment.' }
  $runtimeFile = Join-Path $workspace 'frontend/dist/depo-runtime-config.js'
  if (-not (Test-Path -LiteralPath $runtimeFile)) { throw 'Public runtime routing was not written.' }
  Set-Content -LiteralPath (Join-Path $workspace 'fail-build') -Value 'fail'
  $failed = $false
  try { & $builder } catch { if ($_.Exception.Message -notlike '*simulated build failure*') { throw }; $failed = $true }
  if (-not $failed -or $env:REACT_APP_API_GATEWAY_URL -ne 'http://old.example' -or $env:DEPO_BROWSER_ROUTING_OVERRIDE_JSON -ne '{"existing":"value"}') { throw 'Failed build did not restore the caller environment.' }
  Write-Output 'PASS: explicit empty root routing and caller environment restoration after successful and failed builds.'
} finally {
  [Environment]::SetEnvironmentVariable('REACT_APP_API_GATEWAY_URL',$previousGateway,'Process')
  [Environment]::SetEnvironmentVariable('DEPO_BROWSER_ROUTING_OVERRIDE_JSON',$previousOverride,'Process')
  Remove-Item -LiteralPath 'Function:\npm.cmd' -ErrorAction SilentlyContinue
  $resolved = [IO.Path]::GetFullPath($workspace)
  $boundary = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'depo-build-test-*') { throw 'Refusing unsafe fixture cleanup.' }
  if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}

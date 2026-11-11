# Offline upgrade orchestration regression: child stages are isolated stubs.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$fixture = Join-Path $root ('.release-test-tmp/upgrade-' + [guid]::NewGuid().ToString('N'))
foreach ($directory in @('infra/windows','infra/deployment','backend/.dt_venv/Scripts')) {
  New-Item -ItemType Directory -Path (Join-Path $fixture $directory) -Force | Out-Null
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'update-depo-windows.ps1') -Destination (Join-Path $fixture 'infra/windows/update-depo-windows.ps1')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'service-runtimes.ps1') -Destination (Join-Path $fixture 'infra/windows/service-runtimes.ps1')
Set-Content -LiteralPath (Join-Path $fixture 'backend/.dt_venv/Scripts/python.exe') -Value 'fixture only'
Set-Content -LiteralPath (Join-Path $fixture '.env.local') -Value 'retained customer configuration'
Set-Content -LiteralPath (Join-Path $fixture 'infra/deployment/services.json') -Value '{"services":[{"id":"ontology"}],"workers":[]}'
Set-Content -LiteralPath (Join-Path $fixture 'infra/windows/runtime-config.ps1') -Value 'function Read-DepoEnvironment { @{ DEPO_SERVICE_RUNTIME_MODE = "shared" } }'
$stages = @('infra/deployment/test-installation-package.ps1','infra/deployment/test-depo-deployment.ps1',
  'infra/deployment/test-depo-frontend-config.ps1','infra/windows/install-depo.ps1',
  'infra/windows/initialize-depo-schema.ps1','infra/windows/test-depo-neo4j.ps1',
  'infra/windows/update-depo-runtime-timeouts.ps1','infra/windows/stop-depo-frontend.ps1',
  'infra/windows/stop-depo-services.ps1','install-depo.ps1','infra/windows/start-depo-frontend.ps1')
foreach ($stage in $stages) {
  $stub = '$stageName=if($PSScriptRoot -eq (Split-Path $env:DEPO_UPGRADE_TEST_TRACE)){"root-install-depo.ps1"}else{$MyInvocation.MyCommand.Name}; Add-Content -LiteralPath $env:DEPO_UPGRADE_TEST_TRACE -Value $stageName; $global:LASTEXITCODE = 0; if ($env:DEPO_UPGRADE_TEST_FAIL -eq $stageName) { $global:LASTEXITCODE = 17 }'
  Set-Content -LiteralPath (Join-Path $fixture $stage) -Value $stub
}
$trace = Join-Path $fixture 'trace.txt'
$previousTrace = $env:DEPO_UPGRADE_TEST_TRACE
$previousFail = $env:DEPO_UPGRADE_TEST_FAIL
$env:DEPO_UPGRADE_TEST_TRACE = $trace
try {
  $updater = Join-Path $fixture 'infra/windows/update-depo-windows.ps1'
  & $updater -PreflightOnly
  $steps = @(Get-Content -LiteralPath $trace)
  if ($steps -contains 'stop-depo-services.ps1' -or $steps -contains 'root-install-depo.ps1' -or $steps -contains 'update-depo-runtime-timeouts.ps1') { throw 'Preflight performed a mutation stage.' }
  Set-Content -LiteralPath $trace -Value ''
  & $updater
  $steps = @(Get-Content -LiteralPath $trace)
  if ($steps -contains 'update-depo-runtime-timeouts.ps1') { throw 'Upgrade changed timeout settings without an explicit request.' }
  if ($steps[-1] -ne 'root-install-depo.ps1') { throw 'Upgrade did not delegate completion to the root installer.' }
  Set-Content -LiteralPath $trace -Value ''
  $env:DEPO_UPGRADE_TEST_FAIL = 'root-install-depo.ps1'
  $failed = $false
  try { & $updater } catch { $failed = $true }
  if (-not $failed) { throw 'Nonzero child exit was ignored.' }
  if (@(Get-Content -LiteralPath $trace) -contains 'start-depo-frontend.ps1') { throw 'Frontend started after failed migration/install.' }
  $env:DEPO_UPGRADE_TEST_FAIL = ''
  Set-Content -LiteralPath $trace -Value ''
  & $updater -LlmTimeoutSeconds 300
  if (@(Get-Content -LiteralPath $trace) -notcontains 'update-depo-runtime-timeouts.ps1') { throw 'Explicit timeout update was ignored.' }
  # Select a runtime absent from this shared-only fixture. This must fail
  # before either service or frontend shutdown, not after migrations.
  Set-Content -LiteralPath (Join-Path $fixture 'infra/windows/runtime-config.ps1') -Value 'function Read-DepoEnvironment { @{ DEPO_SERVICE_RUNTIME_MODE = "isolated" } }'
  Set-Content -LiteralPath $trace -Value ''
  $failed = $false
  try { & $updater } catch { $failed = $true }
  if (-not $failed -or @(Get-Content -LiteralPath $trace) -contains 'stop-depo-services.ps1') { throw 'Missing isolated runtime was not rejected before shutdown.' }
  if ((Get-Content -LiteralPath (Join-Path $fixture '.env.local') -Raw).Trim() -ne 'retained customer configuration') { throw 'Customer configuration changed.' }
  Write-Host 'PASS: read-only preflight, preserved configuration, explicit timeout updates, missing-runtime rejection, ordered upgrade and fail-fast native exit handling.'
} finally {
  $env:DEPO_UPGRADE_TEST_TRACE = $previousTrace
  $env:DEPO_UPGRADE_TEST_FAIL = $previousFail
}

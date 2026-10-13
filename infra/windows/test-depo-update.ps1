<# .SYNOPSIS Tests timeout edits and upgrade sequencing with isolated stub services. #>
$ErrorActionPreference = 'Stop'
$workspace = Join-Path ([IO.Path]::GetTempPath()) ('depo-update-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $workspace 'infra/windows') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $workspace 'backend/.dt_venv/Scripts') -Force | Out-Null
try {
  $scripts = Join-Path $workspace 'infra/windows'
  foreach ($name in @('update-depo-windows.ps1','update-depo-runtime-timeouts.ps1','runtime-config.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $scripts $name)
  }
  Set-Content -LiteralPath (Join-Path $workspace 'backend/.dt_venv/Scripts/python.exe') -Value 'stub runtime: never executed'
  $stub = @'
param([string]$EnvFile, [string]$Profile, [switch]$SkipFrontend, [switch]$SkipDependencyInstall)
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Add-Content -LiteralPath (Join-Path $root 'order.txt') -Value ([IO.Path]::GetFileNameWithoutExtension($PSCommandPath))
if ($PSCommandPath -like '*install-depo-windows.ps1' -and (Test-Path -LiteralPath (Join-Path $root 'fail-install'))) { throw 'simulated migration failure' }
'@
  foreach ($name in @('stop-depo-frontend.ps1','stop-depo-services.ps1','install-depo-windows.ps1','build-depo-frontend.ps1','start-depo-frontend.ps1')) {
    Set-Content -LiteralPath (Join-Path $scripts $name) -Value $stub
  }
  $envFile = Join-Path $workspace '.env.local'
  Set-Content -LiteralPath $envFile -Value @('# Preserve this comment','OTHER_SETTING=kept','LLM_REQUEST_TIMEOUT_SECONDS=30','AGENTIC_TOOL_TIMEOUT_SECONDS=30','AGENTIC_RUN_TIMEOUT_SECONDS=300')
  & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile
  . (Join-Path $scripts 'runtime-config.ps1')
  $values = Read-DepoEnvironment -Root $workspace -EnvFile $envFile
  if ($values.LLM_REQUEST_TIMEOUT_SECONDS -ne '300' -or $values.AGENTIC_TOOL_TIMEOUT_SECONDS -ne '330' -or $values.AGENTIC_RUN_TIMEOUT_SECONDS -ne '900' -or $values.OTHER_SETTING -ne 'kept') { throw 'Timeout or preserved setting mismatch.' }
  if ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -join ',' -ne 'stop-depo-frontend,stop-depo-services,install-depo-windows,build-depo-frontend,start-depo-frontend') { throw 'Upgrade sequence mismatch.' }
  $before = [IO.File]::ReadAllText($envFile)
  & (Join-Path $scripts 'update-depo-runtime-timeouts.ps1') -EnvFile $envFile
  if ([IO.File]::ReadAllText($envFile) -ne $before) { throw 'Repeated timeout update was not idempotent.' }
  & (Join-Path $scripts 'update-depo-runtime-timeouts.ps1') -EnvFile $envFile -LlmTimeoutSeconds 600
  & (Join-Path $scripts 'update-depo-runtime-timeouts.ps1') -EnvFile $envFile -LlmTimeoutSeconds 300
  $values = Read-DepoEnvironment -Root $workspace -EnvFile $envFile
  if ($values.LLM_REQUEST_TIMEOUT_SECONDS -ne '600' -or $values.AGENTIC_TOOL_TIMEOUT_SECONDS -ne '630') { throw 'Higher existing budgets were reduced.' }
  Set-Content -LiteralPath (Join-Path $workspace 'order.txt') -Value ''
  Set-Content -LiteralPath (Join-Path $workspace 'fail-install') -Value 'fail'
  $failed = $false
  try { & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile } catch { $failed = $true }
  if (-not $failed -or (Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -contains 'start-depo-frontend') { throw 'Failed migration must prevent frontend restart.' }
  Write-Host 'PASS: update sequence, timeout synchronization, idempotence, preserved settings, and failed-stage stop.'
} finally {
  $resolved = [IO.Path]::GetFullPath($workspace)
  $boundary = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'depo-update-test-*') { throw 'Refusing cleanup outside the isolated test workspace.' }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

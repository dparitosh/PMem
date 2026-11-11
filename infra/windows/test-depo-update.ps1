<# .SYNOPSIS Tests timeout edits and upgrade sequencing with isolated stub services. #>
$ErrorActionPreference = 'Stop'
$originalEnvironment = @{}
Get-ChildItem Env: | ForEach-Object { $originalEnvironment[$_.Name] = $_.Value }
$workspace = Join-Path ([IO.Path]::GetTempPath()) ('depo-update-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $workspace 'infra/windows') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $workspace 'backend/.dt_venv/Scripts') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $workspace 'infra/deployment') -Force | Out-Null
try {
  $scripts = Join-Path $workspace 'infra/windows'
  foreach ($name in @('update-depo-windows.ps1','update-depo-runtime-timeouts.ps1','runtime-config.ps1','service-runtimes.ps1','process-control.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $scripts $name)
  }
  Set-Content -LiteralPath (Join-Path $workspace 'infra/deployment/services.json') -Value '{"services":[{"id":"ontology"}],"workers":[]}'
  Set-Content -LiteralPath (Join-Path $workspace 'backend/.dt_venv/Scripts/python.exe') -Value 'stub runtime: never executed'
  $pythonStubPath = Join-Path $workspace 'backend/.dt_venv/Scripts/python.exe'
  function Invoke-TestAgenticPreflight {
    param([Parameter(ValueFromRemainingArguments=$true)]$Arguments)
    if (($Arguments -join ' ') -ne '-B -m backend.agentic_service.configuration --preflight') { throw 'Unexpected Python invocation in update test.' }
    Add-Content -LiteralPath (Join-Path $workspace 'order.txt') -Value 'agentic-preflight'
    $global:LASTEXITCODE = if (Test-Path -LiteralPath (Join-Path $workspace 'fail-agentic')) { 1 } else { 0 }
  }
  New-Alias -Name $pythonStubPath -Value Invoke-TestAgenticPreflight
  $stub = @'
param([string]$EnvFile, [string]$RootEnvFile, [string]$Profile, [int]$ServiceStartupTimeoutSeconds, [switch]$SkipFrontend, [switch]$SkipDependencyInstall, [switch]$SkipEndpointChecks, [switch]$CheckPrerequisites)
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Add-Content -LiteralPath (Join-Path $root 'order.txt') -Value ([IO.Path]::GetFileNameWithoutExtension($PSCommandPath))
if ($PSScriptRoot -eq $env:DEPO_UPDATE_TEST_ROOT -and $PSCommandPath -like '*install-depo.ps1' -and (Test-Path -LiteralPath (Join-Path $root 'fail-install'))) { throw 'simulated migration failure' }
if ($PSCommandPath -like '*test-depo-*' -and (Test-Path -LiteralPath (Join-Path $root 'fail-preflight'))) { throw 'simulated preflight failure' }
if ([IO.Path]::GetFileName($PSCommandPath) -eq 'install-depo.ps1' -and $PSScriptRoot -ne $env:DEPO_UPDATE_TEST_ROOT) {
  if (-not $CheckPrerequisites) { throw 'Prerequisite stage attempted installation.' }
  if (Test-Path -LiteralPath (Join-Path $root 'fail-prerequisite')) { throw 'simulated prerequisite failure' }
}
'@
  $env:DEPO_UPDATE_TEST_ROOT=$workspace
  $rootStub=$stub.Replace("`$root = (Resolve-Path (Join-Path `$PSScriptRoot '../..')).Path","`$root = `$PSScriptRoot")
  Set-Content -LiteralPath (Join-Path $workspace 'install-depo.ps1') -Value $rootStub
  foreach ($name in @('stop-depo-frontend.ps1','stop-depo-services.ps1','initialize-depo-schema.ps1','test-depo-neo4j.ps1','install-depo.ps1','build-depo-frontend.ps1','start-depo-frontend.ps1')) {
    Set-Content -LiteralPath (Join-Path $scripts $name) -Value $stub
  }
  foreach ($name in @('test-installation-package.ps1','test-depo-deployment.ps1','test-depo-frontend-config.ps1')) {
    Set-Content -LiteralPath (Join-Path $workspace "infra/deployment/$name") -Value $stub
  }
  $envFile = Join-Path $workspace '.env.local'
  Set-Content -LiteralPath $envFile -Value @('# Preserve this comment','OTHER_SETTING=kept','LLM_REQUEST_TIMEOUT_SECONDS=30','AGENTIC_TOOL_TIMEOUT_SECONDS=30','AGENTIC_RUN_TIMEOUT_SECONDS=300')
  & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile -LlmTimeoutSeconds 300
  . (Join-Path $scripts 'runtime-config.ps1')
  $values = Read-DepoEnvironment -Root $workspace -EnvFile $envFile
  if ($values.LLM_REQUEST_TIMEOUT_SECONDS -ne '300' -or $values.AGENTIC_TOOL_TIMEOUT_SECONDS -ne '330' -or $values.AGENTIC_RUN_TIMEOUT_SECONDS -ne '1440' -or $values.OTHER_SETTING -ne 'kept') { throw 'Timeout or preserved setting mismatch.' }
  if ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -join ',' -ne 'test-installation-package,test-depo-deployment,test-depo-frontend-config,install-depo,agentic-preflight,initialize-depo-schema,test-depo-neo4j,stop-depo-frontend,stop-depo-services,install-depo') { throw 'Upgrade sequence mismatch.' }
  $beforeFailure = [IO.File]::ReadAllText($envFile)
  Set-Content -LiteralPath (Join-Path $workspace 'order.txt') -Value ''
  & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile -PreflightOnly
  if ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -match '^stop-depo-') { throw 'Preflight-only stopped services.' }
  if ([IO.File]::ReadAllText($envFile) -ne $beforeFailure) { throw 'Preflight-only modified settings.' }
  Set-Content -LiteralPath (Join-Path $workspace 'order.txt') -Value ''
  Set-Content -LiteralPath (Join-Path $workspace 'fail-agentic') -Value 'fail'
  $failed = $false
  try { & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile } catch { $failed = $true }
  if (-not $failed -or ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -match '^stop-depo-')) { throw 'Agentic configuration failure must preserve running services.' }
  if ([IO.File]::ReadAllText($envFile) -ne $beforeFailure) { throw 'Agentic configuration failure modified settings.' }
  Remove-Item -LiteralPath (Join-Path $workspace 'fail-agentic')
  Set-Content -LiteralPath (Join-Path $workspace 'order.txt') -Value ''
  Set-Content -LiteralPath (Join-Path $workspace 'fail-preflight') -Value 'fail'
  $failed = $false
  try { & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile } catch { $failed = $true }
  if (-not $failed -or ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -match '^stop-depo-')) { throw 'Preflight failure must preserve running services.' }
  if ([IO.File]::ReadAllText($envFile) -ne $beforeFailure) { throw 'Preflight failure modified the environment file.' }
  Remove-Item -LiteralPath (Join-Path $workspace 'fail-preflight')
  Set-Content -LiteralPath (Join-Path $workspace 'order.txt') -Value ''
  Set-Content -LiteralPath (Join-Path $workspace 'fail-prerequisite') -Value 'fail'
  $failed = $false
  try { & (Join-Path $scripts 'update-depo-windows.ps1') -EnvFile $envFile } catch { $failed = $true }
  if (-not $failed -or ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -match '^stop-depo-')) { throw 'Prerequisite failure must preserve running services.' }
  if ([IO.File]::ReadAllText($envFile) -ne $beforeFailure) { throw 'Prerequisite failure modified settings.' }
  Remove-Item -LiteralPath (Join-Path $workspace 'fail-prerequisite')
  $invalidTimeoutFile = Join-Path $workspace 'invalid-timeout.env'
  foreach ($timeout in @('0','301','3600','bad')) {
    Set-Content -LiteralPath $invalidTimeoutFile -Value "SERVICE_REQUEST_TIMEOUT_SECONDS=$timeout"
    $original = [IO.File]::ReadAllText($invalidTimeoutFile)
    $failed = $false
    try { & (Join-Path $scripts 'update-depo-runtime-timeouts.ps1') -EnvFile $invalidTimeoutFile } catch { $failed = $_.Exception.Message -like '*SERVICE_REQUEST_TIMEOUT_SECONDS*1 and 300*' }
    if (-not $failed -or [IO.File]::ReadAllText($invalidTimeoutFile) -ne $original) { throw 'Invalid service timeout was accepted or modified the file.' }
  }
  Set-Content -LiteralPath $invalidTimeoutFile -Value 'SERVICE_REQUEST_TIMEOUT_SECONDS=300'
  & (Join-Path $scripts 'update-depo-runtime-timeouts.ps1') -EnvFile $invalidTimeoutFile
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
  if (-not ((Get-Content -LiteralPath (Join-Path $workspace 'order.txt')) -contains 'stop-depo-services')) { throw 'Migration failure test did not reach the migration stage.' }
  Write-Host 'PASS: update sequence, timeout synchronization, idempotence, preserved settings, and failed-stage stop.'
} finally {
  if ($pythonStubPath) { Remove-Item -LiteralPath "Alias:$pythonStubPath" -ErrorAction SilentlyContinue }
  Get-ChildItem Env: | Where-Object { -not $originalEnvironment.ContainsKey($_.Name) } | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name, $null, 'Process') }
  foreach ($entry in $originalEnvironment.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
  $resolved = [IO.Path]::GetFullPath($workspace)
  $boundary = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'depo-update-test-*') { throw 'Refusing cleanup outside the isolated test workspace.' }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

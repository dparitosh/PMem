<# Offline lifecycle orchestration tests. No services or databases are contacted. #>
$ErrorActionPreference = 'Stop'
$workspace = Join-Path ([IO.Path]::GetTempPath()) ('depo-lifecycle-test-' + [guid]::NewGuid().ToString('N'))
try {
  $deployment = Join-Path $workspace 'infra/deployment'
  $windows = Join-Path $workspace 'infra/windows'
  New-Item -ItemType Directory -Path $deployment,$windows -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'invoke-depo-lifecycle.ps1') -Destination $deployment
  # Stub only configuration reads; never import a real customer environment.
  Set-Content -LiteralPath (Join-Path $windows 'runtime-config.ps1') -Value @'
function Read-DepoEnvironment([string]$Root,[string]$EnvFile) { return @{NEO4J_URI='bolt://fixture.invalid:7687'} }
'@
  $stub = @'
param([string]$EnvFile,[string]$Profile,[switch]$SkipEndpointChecks,[switch]$EnableSpark,
 [switch]$EnableNeo4jSparkConnector,[switch]$EnablePostgresSparkConnector,[switch]$EnablePipelineScheduler,
 [switch]$SkipPostgres,[string]$PostgresBinDir,[string]$PostgresDataDir,[switch]$Production,[switch]$Bootstrap,[switch]$LocalInsecureDemo,[int]$ServiceStartupTimeoutSeconds)
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$name = [IO.Path]::GetFileNameWithoutExtension($PSCommandPath)
if ($SkipEndpointChecks) { $name += '-configuration' }
Add-Content -LiteralPath (Join-Path $root 'calls.jsonl') -Value (@{name=$name;env=$EnvFile;spark=[bool]$EnableSpark;profile=$Profile;bin=$PostgresBinDir;data=$PostgresDataDir;startup=$ServiceStartupTimeoutSeconds;production=[bool]$Production;bootstrap=[bool]$Bootstrap} | ConvertTo-Json -Compress)
if ((Test-Path -LiteralPath (Join-Path $root 'fail-at')) -and (Get-Content -LiteralPath (Join-Path $root 'fail-at')) -eq $name) { exit 17 }
'@
  foreach ($name in @('test-depo-deployment','seed-depo-baseline-data-jobs','seed-depo-baseline-semantic-assets')) {
    Set-Content -LiteralPath (Join-Path $deployment "$name.ps1") -Value $stub
  }
  foreach ($name in @('start-depo-services','stop-depo-services','initialize-depo-schema','test-depo-release','test-depo-neo4j')) {
    Set-Content -LiteralPath (Join-Path $windows "$name.ps1") -Value $stub
  }
  $script = Join-Path $deployment 'invoke-depo-lifecycle.ps1'
  $log = Join-Path $workspace 'calls.jsonl'
  Push-Location ([IO.Path]::GetTempPath())
  try {
    & $script -Action Start -EnvFile 'customer.env' -Profile Production -EnableSpark -ServiceStartupTimeoutSeconds 1200
    $calls = @(Get-Content -LiteralPath $log | ForEach-Object { $_ | ConvertFrom-Json })
    $expected = 'test-depo-deployment-configuration,test-depo-neo4j,start-depo-services,test-depo-deployment,seed-depo-baseline-data-jobs,seed-depo-baseline-semantic-assets'
    if (($calls.name -join ',') -ne $expected) { throw 'Lifecycle startup sequence mismatch.' }
    if (@($calls | Where-Object { $_.env -ne (Join-Path $workspace 'customer.env') }).Count) { throw 'Environment path changed with caller directory.' }
    $startCall = $calls | Where-Object { $_.name -eq 'start-depo-services' }
    if (-not $startCall.spark) { throw 'Spark option was not forwarded.' }
    if ($startCall.startup -ne 1200) { throw 'Startup timeout override was not forwarded.' }
    if (-not ($calls | Where-Object { $_.name -eq 'test-depo-neo4j' }).production) { throw 'Schema verification must be read-only Production mode.' }
    Set-Content -LiteralPath $log -Value ''
    & $script -Action Start -EnvFile 'customer.env' -Profile Production -SkipBaselineProvisioning
    $calls = @(Get-Content -LiteralPath $log | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
    if (($calls.name -join ',') -ne 'test-depo-deployment-configuration,test-depo-neo4j,start-depo-services,test-depo-deployment') { throw 'Baseline suppression changed startup checks or still ran seeds.' }
    foreach ($failure in @('test-depo-deployment-configuration','test-depo-neo4j','start-depo-services','test-depo-deployment','seed-depo-baseline-data-jobs')) {
      Set-Content -LiteralPath $log -Value ''
      Set-Content -LiteralPath (Join-Path $workspace 'fail-at') -Value $failure
      $caught = $false
      try { & $script -Action Start } catch { $caught = $_.Exception.Message -like '*17*' }
      if (-not $caught) { throw "Native exit was not propagated: $failure" }
      $names = @(Get-Content -LiteralPath $log | Where-Object { $_ } | ForEach-Object { ($_ | ConvertFrom-Json).name })
      if ($names[-1] -ne $failure) { throw "Lifecycle continued after failure: $failure" }
    }
    Set-Content -LiteralPath (Join-Path $workspace 'fail-at') -Value 'none'
    Set-Content -LiteralPath $log -Value ''
    & $script -Action Stop -PostgresBinDir 'selected-bin' -PostgresDataDir 'selected-data'
    $call = Get-Content -LiteralPath $log | Where-Object { $_ } | ConvertFrom-Json
    if ($call.bin -ne 'selected-bin' -or $call.data -ne 'selected-data') { throw 'Shutdown paths were not forwarded.' }
    foreach ($action in @('InitializeDatabase','Validate','ReleasePreflight')) {
      $target = switch ($action) { 'InitializeDatabase' {'initialize-depo-schema'} 'Validate' {'test-depo-deployment'} 'ReleasePreflight' {'test-depo-release'} }
      Set-Content -LiteralPath $log -Value ''
      & $script -Action $action -Profile Production -EnvFile 'customer.env'
      $calls = @(Get-Content -LiteralPath $log | Where-Object { $_ } | ConvertFrom-Json)
      if ($calls.Count -ne 1 -or $calls[0].name -ne $target) { throw "Incorrect delegation: $action" }
      if ($action -eq 'ReleasePreflight' -and -not $calls[0].production) { throw 'Production release profile not forwarded.' }
      Set-Content -LiteralPath (Join-Path $workspace 'fail-at') -Value $target
      $caught = $false
      try { & $script -Action $action } catch { $caught = $_.Exception.Message -like '*17*' }
      if (-not $caught) { throw "Failed action did not stop: $action" }
      Set-Content -LiteralPath (Join-Path $workspace 'fail-at') -Value 'none'
    }
    . (Join-Path $PSScriptRoot '../windows/runtime-config.ps1')
    foreach ($case in @(@{value='';expected=20},@{value='3';expected=20},@{value='30';expected=155},@{value='2.5';expected=18})) {
      if ((Get-DepoReadinessProbeTimeoutSeconds @{'DEPO_READINESS_TIMEOUT_SECONDS'=$case.value}) -ne $case.expected) { throw 'Incorrect readiness request budget.' }
    }
    foreach ($invalid in @('NaN','Infinity','bad','0','31')) {
      $caught = $false
      try { Get-DepoReadinessProbeTimeoutSeconds @{'DEPO_READINESS_TIMEOUT_SECONDS'=$invalid} | Out-Null } catch { $caught = $true }
      if (-not $caught) { throw 'Invalid readiness budget accepted.' }
    }
    Write-Host 'PASS: lifecycle automatic sequence, root-relative environment, option forwarding, and fail-fast child exit handling.'
  } finally { Pop-Location }
} finally {
  $resolved = [IO.Path]::GetFullPath($workspace)
  $boundary = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'depo-lifecycle-test-*') { throw 'Refusing cleanup outside isolated lifecycle fixture.' }
  if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}

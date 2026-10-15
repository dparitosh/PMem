param(
  [Parameter(Mandatory = $true)][ValidateSet("Start", "Stop", "Validate", "InitializeDatabase", "ReleasePreflight")][string]$Action,
  [string]$EnvFile = ".env.local",
  [ValidateSet("Bootstrap", "Production")][string]$Profile = "Bootstrap",
  [switch]$LocalInsecureDemo,
  [switch]$EnableSpark,
  [switch]$EnableNeo4jSparkConnector,
  [switch]$EnablePostgresSparkConnector,
  [switch]$EnablePipelineScheduler,
  [switch]$SkipBaselineProvisioning,
  [ValidateRange(1,3600)][int]$ServiceStartupTimeoutSeconds = 600,
  [string]$PostgresBinDir = "",
  [string]$PostgresDataDir = "",
  [switch]$SkipPostgres
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EnvFile = if ([IO.Path]::IsPathRooted($EnvFile)) { [IO.Path]::GetFullPath($EnvFile) } else { [IO.Path]::GetFullPath((Join-Path $root $EnvFile)) }
function Invoke-DepoLifecycleStep([string]$Name, [string]$Script, [hashtable]$Parameters = @{}) {
  if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw "Incomplete deployment: lifecycle script missing: $Script" }
  Write-Host "Lifecycle ${Action}: $Name"
  $global:LASTEXITCODE = 0
  try {
    & $Script @Parameters
    if ($LASTEXITCODE -ne 0) { throw "Child process exited with code $LASTEXITCODE." }
  } catch {
    Write-Warning "Lifecycle action '$Action' stopped at '$Name'. Subsequent steps were not run."
    throw
  }
}
switch ($Action) {
  "Start" {
    if ($LocalInsecureDemo) {
      if ($Profile -ne 'Bootstrap') { throw '-LocalInsecureDemo requires Bootstrap.' }
      . (Join-Path $root 'infra/windows/runtime-config.ps1')
      $demoValues = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
      if ($demoValues.AUTH_MODE -ne 'disabled' -or $demoValues.DEPO_ALLOW_INSECURE_LOCAL_AUTH -ne 'true' -or $demoValues.DEPO_SERVICE_HOST -notin @('127.0.0.1','localhost','::1')) {
        throw '-LocalInsecureDemo requires AUTH_MODE=disabled, DEPO_ALLOW_INSECURE_LOCAL_AUTH=true and a loopback service host in the selected file.'
      }
    }
    Invoke-DepoLifecycleStep 'Configuration preflight' (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') @{EnvFile=$EnvFile; Profile=$Profile; SkipEndpointChecks=$true}
    $startParameters = @{ EnvFile = $EnvFile; ServiceStartupTimeoutSeconds = $ServiceStartupTimeoutSeconds }
    if ($PostgresBinDir) { $startParameters.PostgresBinDir = $PostgresBinDir }
    if ($PostgresDataDir) { $startParameters.PostgresDataDir = $PostgresDataDir }
    if ($SkipPostgres) { $startParameters.SkipPostgres = $true }
    foreach ($option in @('EnableSpark','EnableNeo4jSparkConnector','EnablePostgresSparkConnector','EnablePipelineScheduler')) {
      if ($PSBoundParameters.ContainsKey($option)) { $startParameters[$option] = $PSBoundParameters[$option] }
    }
    Invoke-DepoLifecycleStep 'Backend service startup' (Join-Path $root 'infra/windows/start-depo-services.ps1') $startParameters
    Invoke-DepoLifecycleStep 'Endpoint validation' (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') @{EnvFile=$EnvFile; Profile=$Profile}
    if (-not $SkipBaselineProvisioning) {
      Invoke-DepoLifecycleStep 'Baseline data jobs' (Join-Path $PSScriptRoot 'seed-depo-baseline-data-jobs.ps1') @{EnvFile=$EnvFile}
      Invoke-DepoLifecycleStep 'Baseline semantic assets' (Join-Path $PSScriptRoot 'seed-depo-baseline-semantic-assets.ps1') @{EnvFile=$EnvFile}
    }
  }
  "InitializeDatabase" { Invoke-DepoLifecycleStep 'Database initialization' (Join-Path $root 'infra/windows/initialize-depo-schema.ps1') @{EnvFile=$EnvFile} }
  "Stop" {
    $stopParameters = @{EnvFile=$EnvFile}
    if ($PostgresBinDir) { $stopParameters.PostgresBinDir=$PostgresBinDir }
    if ($PostgresDataDir) { $stopParameters.PostgresDataDir=$PostgresDataDir }
    Invoke-DepoLifecycleStep 'Backend service shutdown' (Join-Path $root 'infra/windows/stop-depo-services.ps1') $stopParameters
  }
  "Validate" { Invoke-DepoLifecycleStep 'Deployment validation' (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') @{EnvFile=$EnvFile; Profile=$Profile} }
  "ReleasePreflight" {
    $releaseParameters = @{ EnvFile = $EnvFile }
    if ($Profile -eq "Production") { $releaseParameters.Production = $true } else { $releaseParameters.Bootstrap = $true }
    if ($LocalInsecureDemo) { $releaseParameters.LocalInsecureDemo = $true }
    Invoke-DepoLifecycleStep 'Release preflight' (Join-Path $root 'infra/windows/test-depo-release.ps1') $releaseParameters
  }
}

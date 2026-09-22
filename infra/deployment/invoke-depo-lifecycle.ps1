param(
  [Parameter(Mandatory = $true)][ValidateSet("Start", "Stop", "Validate", "ReleasePreflight")][string]$Action,
  [string]$EnvFile = ".env.local",
  [ValidateSet("Bootstrap", "Production")][string]$Profile = "Bootstrap",
  [switch]$LocalInsecureDemo,
  [switch]$EnableSpark,
  [switch]$EnableNeo4jSparkConnector,
  [switch]$EnablePipelineScheduler,
  [switch]$SkipBaselineProvisioning,
  [string]$PostgresBinDir = "",
  [string]$PostgresDataDir = "",
  [switch]$SkipPostgres
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
switch ($Action) {
  "Start" {
    & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $EnvFile -Profile $Profile -SkipEndpointChecks
    $startParameters = @{ EnvFile = $EnvFile }
    if ($PostgresBinDir) { $startParameters.PostgresBinDir = $PostgresBinDir }
    if ($PostgresDataDir) { $startParameters.PostgresDataDir = $PostgresDataDir }
    if ($SkipPostgres) { $startParameters.SkipPostgres = $true }
    if ($EnableSpark) { $startParameters.EnableSpark = $true }
    if ($EnableNeo4jSparkConnector) {
      if (-not $EnableSpark) { throw '-EnableNeo4jSparkConnector requires -EnableSpark.' }
      $startParameters.EnableNeo4jSparkConnector = $true
    }
    if ($EnablePipelineScheduler) { $startParameters.EnablePipelineScheduler = $true }
    & (Join-Path $root "infra\windows\start-depo-services.ps1") @startParameters
    & (Join-Path $PSScriptRoot "test-depo-deployment.ps1") -EnvFile $EnvFile -Profile $Profile
    if (-not $SkipBaselineProvisioning) {
      & (Join-Path $PSScriptRoot "seed-depo-baseline-data-jobs.ps1") -EnvFile $EnvFile
      & (Join-Path $PSScriptRoot "seed-depo-baseline-semantic-assets.ps1") -EnvFile $EnvFile
    }
  }
  "Stop" { & (Join-Path $root "infra\windows\stop-depo-services.ps1") -EnvFile $EnvFile }
  "Validate" { & (Join-Path $PSScriptRoot "test-depo-deployment.ps1") -EnvFile $EnvFile -Profile $Profile }
  "ReleasePreflight" {
    $switch = if ($Profile -eq "Production") { "-Production" } else { "-Bootstrap" }
    $releaseParameters = @{ EnvFile = $EnvFile }
    if ($Profile -eq "Production") { $releaseParameters.Production = $true } else { $releaseParameters.Bootstrap = $true }
    if ($LocalInsecureDemo) { $releaseParameters.LocalInsecureDemo = $true }
    & (Join-Path $root "infra\windows\test-depo-release.ps1") @releaseParameters
  }
}

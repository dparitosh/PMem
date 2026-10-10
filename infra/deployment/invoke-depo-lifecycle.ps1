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
  [string]$PostgresBinDir = "",
  [string]$PostgresDataDir = "",
  [switch]$SkipPostgres
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
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
    & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $EnvFile -Profile $Profile -SkipEndpointChecks
    $startParameters = @{ EnvFile = $EnvFile }
    if ($PostgresBinDir) { $startParameters.PostgresBinDir = $PostgresBinDir }
    if ($PostgresDataDir) { $startParameters.PostgresDataDir = $PostgresDataDir }
    if ($SkipPostgres) { $startParameters.SkipPostgres = $true }
    foreach ($option in @('EnableSpark','EnableNeo4jSparkConnector','EnablePostgresSparkConnector','EnablePipelineScheduler')) {
      if ($PSBoundParameters.ContainsKey($option)) { $startParameters[$option] = $PSBoundParameters[$option] }
    }
    & (Join-Path $root "infra\windows\start-depo-services.ps1") @startParameters
    & (Join-Path $PSScriptRoot "test-depo-deployment.ps1") -EnvFile $EnvFile -Profile $Profile
    if (-not $SkipBaselineProvisioning) {
      & (Join-Path $PSScriptRoot "seed-depo-baseline-data-jobs.ps1") -EnvFile $EnvFile
      & (Join-Path $PSScriptRoot "seed-depo-baseline-semantic-assets.ps1") -EnvFile $EnvFile
    }
  }
  "InitializeDatabase" { & (Join-Path $root "infra/windows/initialize-depo-schema.ps1") -EnvFile $EnvFile }
  "Stop" { & (Join-Path $root "infra\windows\stop-depo-services.ps1") -EnvFile $EnvFile }
  "Validate" { & (Join-Path $PSScriptRoot "test-depo-deployment.ps1") -EnvFile $EnvFile -Profile $Profile }
  "ReleasePreflight" {
    $releaseParameters = @{ EnvFile = $EnvFile }
    if ($Profile -eq "Production") { $releaseParameters.Production = $true } else { $releaseParameters.Bootstrap = $true }
    if ($LocalInsecureDemo) { $releaseParameters.LocalInsecureDemo = $true }
    & (Join-Path $root "infra\windows\test-depo-release.ps1") @releaseParameters
  }
}

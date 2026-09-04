param(
  [Parameter(Mandatory = $true)][ValidateSet("Start", "Stop", "Validate", "ReleasePreflight")][string]$Action,
  [string]$EnvFile = ".env.local",
  [ValidateSet("Bootstrap", "Production")][string]$Profile = "Bootstrap",
  [switch]$LocalInsecureDemo,
  [switch]$EnableSpark,
  [switch]$EnablePipelineScheduler
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
switch ($Action) {
  "Start" {
    $startParameters = @{ EnvFile = $EnvFile }
    if ($EnableSpark) { $startParameters.EnableSpark = $true }
    if ($EnablePipelineScheduler) { $startParameters.EnablePipelineScheduler = $true }
    & (Join-Path $root "infra\windows\start-depo-services.ps1") @startParameters
    & (Join-Path $PSScriptRoot "test-depo-deployment.ps1") -EnvFile $EnvFile -Profile $Profile
  }
  "Stop" { & (Join-Path $root "infra\windows\stop-depo-services.ps1") }
  "Validate" { & (Join-Path $PSScriptRoot "test-depo-deployment.ps1") -EnvFile $EnvFile -Profile $Profile }
  "ReleasePreflight" {
    $switch = if ($Profile -eq "Production") { "-Production" } else { "-Bootstrap" }
    $releaseParameters = @{ EnvFile = $EnvFile }
    if ($Profile -eq "Production") { $releaseParameters.Production = $true } else { $releaseParameters.Bootstrap = $true }
    if ($LocalInsecureDemo) { $releaseParameters.LocalInsecureDemo = $true }
    & (Join-Path $root "infra\windows\test-depo-release.ps1") @releaseParameters
  }
}

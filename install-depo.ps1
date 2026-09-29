<# .SYNOPSIS Supported customer entry point for a complete Windows installation. #>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [string]$Python = 'py',
  [switch]$EnableSpark,
  [switch]$EnableNeo4jSparkConnector,
  [switch]$EnablePostgresSparkConnector,
  [switch]$EnablePipelineScheduler,
  [switch]$SkipFrontend,
  [switch]$SkipBaselineProvisioning,
  [switch]$SkipDependencyInstall,
  [switch]$SkipReleasePreflight
)
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
& (Join-Path $PSScriptRoot 'infra\windows\install-depo-windows.ps1') @PSBoundParameters
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "DEPO installation failed with exit code $LASTEXITCODE." }

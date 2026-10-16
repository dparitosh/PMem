<# .SYNOPSIS Upgrades an existing customer deployment using its retained configuration. #>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [ValidateRange(1,900)][int]$LlmTimeoutSeconds = 300,
  [ValidateRange(1,3600)][int]$ServiceStartupTimeoutSeconds = 600,
  [switch]$SkipFrontend,
  [switch]$InstallDependencies,
  [switch]$EnableOcr,
  [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
& (Join-Path $PSScriptRoot 'infra/windows/update-depo-windows.ps1') @PSBoundParameters
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "DEPO upgrade failed with exit code $LASTEXITCODE." }

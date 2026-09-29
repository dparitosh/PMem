<# .SYNOPSIS Starts or stops an installed DEPO Windows deployment. #>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('Start','Stop')][string]$Action,
  [string]$EnvFile = '.env.local',
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [switch]$SkipPostgres,
  [switch]$SkipBaselineProvisioning
)
$ErrorActionPreference = 'Stop'
$parameters = @{ Action = $Action; EnvFile = $EnvFile; Profile = $Profile }
if ($SkipPostgres) { $parameters.SkipPostgres = $true }
if ($SkipBaselineProvisioning) { $parameters.SkipBaselineProvisioning = $true }
$global:LASTEXITCODE = 0
& (Join-Path $PSScriptRoot 'infra\deployment\invoke-depo-lifecycle.ps1') @parameters
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "DEPO $Action failed with exit code $LASTEXITCODE." }

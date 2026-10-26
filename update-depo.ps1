<#
.SYNOPSIS Upgrades an existing customer deployment using its retained configuration.
.DESCRIPTION Run after placing a complete matching release. Applies pending PostgreSQL
migrations and indexes, provisions Neo4j search indexes/backfills, rebuilds the frontend
and restarts application services. Reports retained AP242 mapping changes for review;
does not regenerate source instances or approve/publish PMI associations automatically.
Use -PreflightOnly to validate without applying migrations or stopping services.
#>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [string]$Python = 'py',
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [ValidateRange(1,900)][int]$LlmTimeoutSeconds = 300,
  [ValidateRange(1,3600)][int]$ServiceStartupTimeoutSeconds = 600,
  [switch]$SkipFrontend,
  [switch]$InstallDependencies,
  [switch]$EnableOcr,
  [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
if ((Get-ExecutionPolicy) -ne 'Bypass') {
  try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction Stop }
  catch { throw 'PowerShell policy blocked update. Use Setup-DEPO.cmd or an approved signed release; machine policy was not changed.' }
  if ((Get-ExecutionPolicy) -ne 'Bypass') { throw 'Process bypass is overridden by organization policy. Use an approved signed release.' }
}
$updateArguments=@{} + $PSBoundParameters
. (Join-Path $PSScriptRoot 'infra/windows/native-install-command.ps1')
Invoke-DepoLoggedAction -Root $PSScriptRoot -Name 'update' -AuditEnvFile $EnvFile -Action {
$global:LASTEXITCODE = 0
& (Join-Path $PSScriptRoot 'infra/windows/update-depo-windows.ps1') @updateArguments
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "DEPO upgrade failed with exit code $LASTEXITCODE." }
}

<#
.SYNOPSIS Upgrades an existing deployment after placing the matching release files.
.DESCRIPTION Applies pending PostgreSQL migrations, provisions Neo4j schema,
builds the frontend and restarts services using the existing environment file.
API keys are validated and preserved; rotation remains a separate explicit action.
#>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [ValidateRange(1,900)][int]$LlmTimeoutSeconds = 300,
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [switch]$SkipFrontend,
  [switch]$InstallDependencies
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw 'Existing environment file is missing; restore it before redeployment.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'backend/.dt_venv/Scripts/python.exe') -PathType Leaf)) { throw 'Existing backend runtime is absent. Use install-depo-windows.ps1 for a first installation.' }
& (Join-Path $PSScriptRoot 'update-depo-runtime-timeouts.ps1') -EnvFile $envPath -LlmTimeoutSeconds $LlmTimeoutSeconds
if (-not $SkipFrontend) { & (Join-Path $PSScriptRoot 'stop-depo-frontend.ps1') }
& (Join-Path $PSScriptRoot 'stop-depo-services.ps1') -EnvFile $envPath
# Delegate migration, graph provisioning and release validation to the same
# installer used for a new deployment; do not duplicate those lifecycle stages.
& (Join-Path $PSScriptRoot 'install-depo-windows.ps1') -EnvFile $envPath -Profile $Profile -SkipFrontend:$SkipFrontend -SkipDependencyInstall:(!$InstallDependencies)
if (-not $SkipFrontend) {
  if (-not $InstallDependencies) { & (Join-Path $PSScriptRoot 'build-depo-frontend.ps1') -EnvFile $envPath }
  & (Join-Path $PSScriptRoot 'start-depo-frontend.ps1') -EnvFile $envPath
}
Write-Host 'DEPO redeployment completed: database schema/indexes verified, timeouts applied, services restarted.' -ForegroundColor Green

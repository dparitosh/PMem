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
  [ValidateRange(1,3600)][int]$ServiceStartupTimeoutSeconds = 600,
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [switch]$SkipFrontend,
  [switch]$InstallDependencies
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw 'Existing environment file is missing; restore it before redeployment.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'backend/.dt_venv/Scripts/python.exe') -PathType Leaf)) { throw 'Existing backend runtime is absent. Use install-depo-windows.ps1 for a first installation.' }
# Validate the selected release configuration while the running deployment is
# still available. No environment edits or shutdown may precede these checks.
& (Join-Path $root 'infra/deployment/test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks
if (-not $SkipFrontend) {
  & (Join-Path $root 'infra/deployment/test-depo-frontend-config.ps1') -RootEnvFile $envPath
}
& (Join-Path $PSScriptRoot 'install-depo.ps1') -CheckPrerequisites -SkipFrontend:$SkipFrontend -EnvFile $envPath
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Runtime prerequisite check failed. Services were not stopped.' }
& (Join-Path $PSScriptRoot 'initialize-depo-schema.ps1') -EnvFile $envPath -UpgradePreflight
& (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') -EnvFile $envPath -UpgradePreflight
& (Join-Path $PSScriptRoot 'update-depo-runtime-timeouts.ps1') -EnvFile $envPath -LlmTimeoutSeconds $LlmTimeoutSeconds
Write-Host 'Read-only database upgrade checks passed. Stopping application processes next.'
if (-not $SkipFrontend) { & (Join-Path $PSScriptRoot 'stop-depo-frontend.ps1') }
& (Join-Path $PSScriptRoot 'stop-depo-services.ps1') -EnvFile $envPath
# Delegate migration, graph provisioning and release validation to the same
# installer used for a new deployment; do not duplicate those lifecycle stages.
& (Join-Path $PSScriptRoot 'install-depo-windows.ps1') -EnvFile $envPath -Profile $Profile -ServiceStartupTimeoutSeconds $ServiceStartupTimeoutSeconds -SkipFrontend:$SkipFrontend -SkipDependencyInstall:(!$InstallDependencies)
if (-not $SkipFrontend) {
  & (Join-Path $PSScriptRoot 'start-depo-frontend.ps1') -EnvFile $envPath
}
Write-Host 'DEPO redeployment completed: database schema/indexes verified, timeouts applied, services restarted.' -ForegroundColor Green

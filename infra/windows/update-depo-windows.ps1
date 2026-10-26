<#
.SYNOPSIS Upgrades an existing deployment after placing the matching release files.
.DESCRIPTION Applies pending PostgreSQL migrations, provisions Neo4j schema,
builds the frontend and restarts services using the existing environment file.
API keys are validated and preserved; rotation remains a separate explicit action.
#>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [string]$Python = 'py',
  [ValidateRange(1,900)][int]$LlmTimeoutSeconds = 300,
  [ValidateRange(1,3600)][int]$ServiceStartupTimeoutSeconds = 600,
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [switch]$SkipFrontend,
  [switch]$InstallDependencies,
  [switch]$EnableOcr,
  [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw 'Existing environment file is missing; restore it before redeployment.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'backend/.dt_venv/Scripts/python.exe') -PathType Leaf)) { throw 'Existing backend runtime is absent. Use Setup-DEPO.cmd for a first installation.' }
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'service-runtimes.ps1')
$settings = Read-DepoEnvironment -Root $root -EnvFile $envPath
function Invoke-DepoUpgradeStep([string]$Name, [scriptblock]$Action) {
  Write-Host "Upgrade: $Name"
  $global:LASTEXITCODE = 0
  try {
    & $Action
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Child process exited with code $LASTEXITCODE." }
  } catch {
    Write-Warning "Upgrade stopped at '$Name'. Data and configuration are retained. Do not restart an older release against a newer migrated schema without a reviewed rollback."
    throw
  }
}
# Validate the selected release configuration while the running deployment is
# still available. No environment edits or shutdown may precede these checks.
Invoke-DepoUpgradeStep 'Release package validation' { & (Join-Path $root 'infra/deployment/test-installation-package.ps1') }
Invoke-DepoUpgradeStep 'Configuration preflight' { & (Join-Path $root 'infra/deployment/test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks }
if (-not $SkipFrontend) {
  Invoke-DepoUpgradeStep 'Frontend configuration' { & (Join-Path $root 'infra/deployment/test-depo-frontend-config.ps1') -RootEnvFile $envPath }
}
Invoke-DepoUpgradeStep 'Runtime prerequisites' { & (Join-Path $PSScriptRoot 'install-depo.ps1') -Python $Python -CheckPrerequisites -SkipFrontend:$SkipFrontend -EnvFile $envPath }
if ($EnableOcr -and -not $InstallDependencies) { throw '-EnableOcr requires -InstallDependencies during upgrade.' }
if (-not $InstallDependencies) {
  $manifest = Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
  foreach ($entry in (@($manifest.services) + @($manifest.workers))) {
    $runtime = Get-DepoServicePython -Root $root -ServiceId $entry.id -Mode $settings.DEPO_SERVICE_RUNTIME_MODE
    if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) { throw "Missing runtime for '$($entry.id)'. Rerun with -InstallDependencies. Services were not stopped." }
  }
}
Invoke-DepoUpgradeStep 'PostgreSQL upgrade history and privileges' { & (Join-Path $PSScriptRoot 'initialize-depo-schema.ps1') -EnvFile $envPath -UpgradePreflight }
Invoke-DepoUpgradeStep 'Neo4j existing schema compatibility' { & (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') -EnvFile $envPath -UpgradePreflight }
if ($PreflightOnly) { Write-Host 'Upgrade preflight passed. No services stopped, migrations applied, or configuration changed.'; return }
if ($PSBoundParameters.ContainsKey('LlmTimeoutSeconds')) {
  Invoke-DepoUpgradeStep 'Explicit timeout configuration update' { & (Join-Path $PSScriptRoot 'update-depo-runtime-timeouts.ps1') -EnvFile $envPath -LlmTimeoutSeconds $LlmTimeoutSeconds }
}
Write-Host 'Read-only database upgrade checks passed. Stopping application processes next.'
if (-not $SkipFrontend) { Invoke-DepoUpgradeStep 'Frontend shutdown' { & (Join-Path $PSScriptRoot 'stop-depo-frontend.ps1') } }
Invoke-DepoUpgradeStep 'Backend shutdown' { & (Join-Path $PSScriptRoot 'stop-depo-services.ps1') -EnvFile $envPath }
# Delegate migration, graph provisioning and release validation to the same
# installer used for a new deployment; do not duplicate those lifecycle stages.
Invoke-DepoUpgradeStep 'Migration, installation and service verification' {
  & (Join-Path $root 'install-depo.ps1') -Python $Python -EnvFile $envPath -Profile $Profile -ServiceStartupTimeoutSeconds $ServiceStartupTimeoutSeconds -SkipFrontend:$SkipFrontend -SkipDependencyInstall:(!$InstallDependencies) -EnableOcr:$EnableOcr -SkipBaselineProvisioning
}
Write-Host 'Review logs/installation/ceim-upgrade-review/plan.json. New PMI rules require source regeneration and governed publication; existing graph publications were not replaced.'
Write-Host 'DEPO redeployment completed: database schema/indexes verified and services restarted. Existing credentials and configuration were preserved except explicitly requested timeout updates.' -ForegroundColor Green

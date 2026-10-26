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
. (Join-Path $PSScriptRoot 'process-control.ps1')
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
Invoke-DepoUpgradeStep 'Agentic configuration before shutdown' {
  Import-DepoEnvironment -Root $root -EnvFile $envPath
  if (-not $env:NEO4J_USER -and $env:NEO4J_USERNAME) { $env:NEO4J_USER = $env:NEO4J_USERNAME }
  if (-not $env:NEO4J_PASS -and $env:NEO4J_PASSWORD) { $env:NEO4J_PASS = $env:NEO4J_PASSWORD }
  $bindHost = if ($env:DEPO_SERVICE_HOST) { $env:DEPO_SERVICE_HOST } else { '127.0.0.1' }
  $probeHost = Get-DepoProbeHost $bindHost
  $peerPorts = @{ AGENTIC_SERVICE_URL=8012; ONTOLOGY_SERVICE_URL=8011; GRAPH_SERVICE_URL=8013; INGESTION_SERVICE_URL=8014; OSLC_SERVICE_URL=8015; QIF_SERVICE_URL=8010; DATA_CATALOG_URL=8016; DATA_PRODUCT_SERVICE_URL=8017; CEIM_SERVICE_URL=8018; DATA_PIPELINE_SERVICE_URL=8019 }
  foreach ($entry in $peerPorts.GetEnumerator()) {
    if (-not [Environment]::GetEnvironmentVariable($entry.Key, 'Process')) {
      [Environment]::SetEnvironmentVariable($entry.Key, "http://${probeHost}:$($entry.Value)/api/v1", 'Process')
    }
  }
  Push-Location $root
  try {
    & (Join-Path $root 'backend/.dt_venv/Scripts/python.exe') -B -m backend.agentic_service.configuration --preflight
    if ($LASTEXITCODE -ne 0) { throw 'Agentic configuration validation failed. Correct the listed settings. Services were not stopped.' }
  } finally { Pop-Location }
}
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
Write-Host 'Refresh the browser and revalidate access. Review retained workflow status before retrying imports or publication; this update does not replay or approve pending operations.'

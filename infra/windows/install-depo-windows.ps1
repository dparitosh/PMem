<#
.SYNOPSIS
Installs and starts a complete DEPO Windows deployment from one command.

.DESCRIPTION
This is the supported Windows release entry point. It never creates database,
Neo4j, or API credentials: the reviewed root .env.local must exist first.
Each stage delegates to the service-owned script so there is one source of
truth for dependency installation, migration, startup, Spark validation and
release readiness.
#>
param(
  [string]$EnvFile = '.env.local',
  [ValidateSet('Bootstrap', 'Production')][string]$Profile = 'Production',
  [string]$Python = 'py',
  [switch]$EnableSpark,
  [switch]$EnableNeo4jSparkConnector,
  [switch]$EnablePipelineScheduler,
  [switch]$SkipFrontend,
  [switch]$SkipBaselineProvisioning,
  [switch]$SkipDependencyInstall,
  [switch]$SkipReleasePreflight
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }

function Invoke-DepoStage([string]$Name, [scriptblock]$Action) {
  Write-Host "`n=== DEPO: $Name ===" -ForegroundColor Cyan
  $global:LASTEXITCODE = 0
  & $Action
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "DEPO stage failed: $Name (exit code $LASTEXITCODE)." }
  Write-Host "=== DEPO: $Name complete ===" -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
  throw "Missing deployment configuration: $envPath. Create and complete root .env.local before running this installer."
}
if (($EnableNeo4jSparkConnector -or $EnablePipelineScheduler) -and -not $EnableSpark) {
  throw '-EnableNeo4jSparkConnector and -EnablePipelineScheduler require -EnableSpark.'
}

if (-not $SkipDependencyInstall) {
  Invoke-DepoStage 'Prerequisites' {
    & (Join-Path $PSScriptRoot 'install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend -CheckPrerequisites
  }
  Invoke-DepoStage 'Application dependencies and frontend build' {
    & (Join-Path $PSScriptRoot 'install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend
  }
}

Invoke-DepoStage 'Deployment configuration validation' {
  & (Join-Path $root 'infra\deployment\test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks
}
Invoke-DepoStage 'PostgreSQL schema migration' {
  & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') -Action InitializeDatabase -EnvFile $envPath -Profile $Profile
}
Invoke-DepoStage 'Neo4j connection validation' {
  $neo4jParameters = @{ EnvFile = $envPath }
  if ($Profile -eq 'Production') { $neo4jParameters.Production = $true } else { $neo4jParameters.Bootstrap = $true }
  & (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') @neo4jParameters
}
if ($EnableSpark) {
  Invoke-DepoStage 'Spark runtime smoke test' {
    $sparkParameters = @{ EnvFile = $envPath }
    if ($EnableNeo4jSparkConnector) { $sparkParameters.Neo4jConnector = $true }
    & (Join-Path $PSScriptRoot 'test-depo-spark.ps1') @sparkParameters
  }
}
Invoke-DepoStage 'Service startup and endpoint validation' {
  $startParameters = @{ Action = 'Start'; EnvFile = $envPath; Profile = $Profile }
  if ($EnableSpark) { $startParameters.EnableSpark = $true }
  if ($EnableNeo4jSparkConnector) { $startParameters.EnableNeo4jSparkConnector = $true }
  if ($EnablePipelineScheduler) { $startParameters.EnablePipelineScheduler = $true }
  if ($SkipBaselineProvisioning) { $startParameters.SkipBaselineProvisioning = $true }
  & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') @startParameters
}
if (-not $SkipReleasePreflight) {
  Invoke-DepoStage 'Release preflight' {
    & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') -Action ReleasePreflight -EnvFile $envPath -Profile $Profile
  }
}

Write-Host "`nDEPO Windows installation completed successfully." -ForegroundColor Green
Write-Host 'Frontend build: frontend\dist. Serve it through the customer HTTPS reverse proxy.'

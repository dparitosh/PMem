<#
.SYNOPSIS
Installs and starts a complete DEPO Windows deployment from one command.

.DESCRIPTION
This is the supported Windows release entry point. It does not generate secrets
or create the PostgreSQL database: the reviewed root .env.local and DBA-created
database/schema must exist first. Migration bootstraps missing hashed API-key
profiles when PostgreSQL credential storage is enabled; existing profiles remain.
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
  [switch]$EnablePostgresSparkConnector,
  [switch]$EnablePipelineScheduler,
  [switch]$SkipFrontend,
  [switch]$SkipBaselineProvisioning,
  [switch]$SkipDependencyInstall,
  [switch]$ReplaceExistingCredentials,
  [switch]$SkipReleasePreflight
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }

function Invoke-DepoStage([string]$Name, [scriptblock]$Action) {
  Write-Host "`n=== DEPO: $Name ===" -ForegroundColor Cyan
  $global:LASTEXITCODE = 0
  try { & $Action } catch {
    Write-Warning "Stopped at stage: $Name. Correct the error below, then rerun the same repository-root install command. Do not delete the environment files or database."
    throw
  }
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "DEPO stage failed: $Name (exit code $LASTEXITCODE)." }
  Write-Host "=== DEPO: $Name complete ===" -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
  throw "Missing deployment configuration: $envPath. Create and complete root .env.local before running this installer."
}
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$settings = Read-DepoEnvironment -Root $root -EnvFile $envPath
Invoke-DepoStage 'Deployment configuration preflight (before dependency installation)' {
  & (Join-Path $root 'infra\deployment\test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks
  if (-not $SkipFrontend) {
    & (Join-Path $root 'infra\deployment\test-depo-frontend-config.ps1') -RootEnvFile $envPath
  }
}
$artifactStorage = $settings['ARTIFACT_STORAGE']
if (-not $artifactStorage -or -not [IO.Path]::IsPathRooted($artifactStorage)) {
  throw 'ARTIFACT_STORAGE must be an absolute durable directory shared by the DEPO APIs and workers.'
}
New-Item -ItemType Directory -Path $artifactStorage -Force | Out-Null
$artifactProbe = Join-Path $artifactStorage ('.depo-write-probe-' + [guid]::NewGuid().ToString('N'))
try {
  Set-Content -LiteralPath $artifactProbe -Value 'DEPO artifact storage write probe' -NoNewline
} finally {
  if (Test-Path -LiteralPath $artifactProbe) { Remove-Item -LiteralPath $artifactProbe -Force }
}
$configuredSpark = $settings['DEPO_SPARK_ENABLED'] -eq 'true'
$configuredConnector = $settings['DEPO_SPARK_NEO4J_ENABLED'] -eq 'true'
$configuredPostgresConnector = $settings['DEPO_SPARK_POSTGRES_ENABLED'] -eq 'true'
$configuredScheduler = $settings['DEPO_PIPELINE_SCHEDULER_ENABLED'] -eq 'true'
$effectiveSpark = [bool]($EnableSpark -or $configuredSpark)
$effectiveConnector = [bool]($EnableNeo4jSparkConnector -or $configuredConnector)
$effectivePostgresConnector = [bool]($EnablePostgresSparkConnector -or $configuredPostgresConnector)
$effectiveScheduler = [bool]($EnablePipelineScheduler -or $configuredScheduler)
if (($effectiveConnector -or $effectivePostgresConnector) -and -not $effectiveSpark) {
  throw 'Spark connectors require Spark enabled through -EnableSpark or DEPO_SPARK_ENABLED=true in .env.local.'
}

if (-not $SkipDependencyInstall) {
  Invoke-DepoStage 'Prerequisites' {
    & (Join-Path $PSScriptRoot 'install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend -CheckPrerequisites
  }
  Invoke-DepoStage 'Application dependencies and frontend build' {
    & (Join-Path $PSScriptRoot 'install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend -EnvFile $envPath
  }
}

if ($SkipDependencyInstall -and -not $SkipFrontend) {
  Invoke-DepoStage 'Frontend rebuild using installed dependencies' {
    & (Join-Path $PSScriptRoot 'build-depo-frontend.ps1') -EnvFile $envPath
  }
}
if (-not $SkipFrontend -and -not (Test-Path -LiteralPath (Join-Path $root 'frontend/dist/index.html') -PathType Leaf)) {
  throw 'Frontend build output is missing. No services were started.'
}

Invoke-DepoStage 'Deployment configuration validation' {
  & (Join-Path $root 'infra\deployment\test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks
}
Invoke-DepoStage 'Selected PostgreSQL runtime startup' {
  & (Join-Path $PSScriptRoot 'start-depo-postgres.ps1') -EnvFile $envPath
}
Invoke-DepoStage 'PostgreSQL URL connectivity' {
  & (Join-Path $root 'infra\postgres\test-postgres-connectivity.ps1') -EnvFile $envPath
}
Invoke-DepoStage 'PostgreSQL schema migration' {
  & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') -Action InitializeDatabase -EnvFile $envPath -Profile $Profile
}
if ($settings['AUTH_MODE'] -eq 'token' -and $settings['DEPO_CREDENTIAL_STORE'] -eq 'postgres') {
  Invoke-DepoStage 'Central credential synchronization (before service launch)' {
    & (Join-Path $PSScriptRoot 'apply-depo-service-credentials.ps1') -EnvFile $envPath -ReplaceExisting:$ReplaceExistingCredentials
  }
} elseif ($ReplaceExistingCredentials) {
  throw '-ReplaceExistingCredentials requires AUTH_MODE=token and DEPO_CREDENTIAL_STORE=postgres.'
}
Invoke-DepoStage 'Neo4j schema provisioning and validation' {
  # The schema file is idempotent. Provision it before the read-only release
  # preflight so a first Production installation cannot fail on missing indexes.
  & (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') -EnvFile $envPath -Bootstrap
  if ($Profile -eq 'Production') {
    & (Join-Path $PSScriptRoot 'test-depo-neo4j.ps1') -EnvFile $envPath -Production
  }
}
if ($effectiveSpark) {
  Invoke-DepoStage 'Spark runtime smoke test' {
    & (Join-Path $PSScriptRoot 'test-depo-spark.ps1') -EnvFile $envPath
  }
  if ($effectiveConnector) {
    Invoke-DepoStage 'Spark Neo4j connector smoke test' {
      & (Join-Path $PSScriptRoot 'test-depo-spark.ps1') -EnvFile $envPath -Neo4jConnector
    }
  }
  if ($effectivePostgresConnector) {
    Invoke-DepoStage 'Spark PostgreSQL connector smoke test' {
      & (Join-Path $PSScriptRoot 'test-depo-spark.ps1') -EnvFile $envPath -PostgresConnector
    }
  }
}
Invoke-DepoStage 'Service startup and endpoint validation' {
  $startParameters = @{ Action = 'Start'; EnvFile = $envPath; Profile = $Profile }
  if ($effectiveSpark) { $startParameters.EnableSpark = $true }
  if ($effectiveConnector) { $startParameters.EnableNeo4jSparkConnector = $true }
  if ($effectivePostgresConnector) { $startParameters.EnablePostgresSparkConnector = $true }
  if ($effectiveScheduler) { $startParameters.EnablePipelineScheduler = $true }
  if ($SkipBaselineProvisioning) { $startParameters.SkipBaselineProvisioning = $true }
  & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') @startParameters
}
if ($settings['AUTH_MODE'] -eq 'token' -and $settings['DEPO_CREDENTIAL_STORE'] -eq 'postgres') {
  Invoke-DepoStage 'Central browser-session authentication verification' {
    & (Join-Path $PSScriptRoot 'test-depo-browser-session.ps1') -EnvFile $envPath
    if ($settings['DEPO_ROUTING_MODE'] -eq 'gateway') {
      & (Join-Path $PSScriptRoot 'test-depo-browser-session.ps1') -EnvFile $envPath -Gateway
    }
  }
}
if (-not $SkipReleasePreflight) {
  Invoke-DepoStage 'Release preflight' {
    & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') -Action ReleasePreflight -EnvFile $envPath -Profile $Profile
  }
}

Write-Host "`nDEPO Windows installation completed successfully." -ForegroundColor Green
if ($settings['AUTH_MODE'] -eq 'token' -and $settings['DEPO_CREDENTIAL_STORE'] -eq 'postgres') {
  Write-Host 'Next: verify central browser authentication with infra/windows/test-depo-browser-session.ps1 using the same -EnvFile.'
  Write-Host 'In the browser open Admin -> Connect registered service credentials, enter ADMIN_API_KEY once, and explicitly choose workflow scopes if needed.'
}
if (-not $SkipFrontend) {
  Write-Host 'Backend services are started. The frontend is built but is not yet served.'
  Write-Host ('Start the frontend with the same configuration: .\infra\windows\start-depo-frontend.ps1 -EnvFile "{0}"' -f $envPath)
  Write-Host 'Open the frontend URL reported by the frontend launcher; allow its exact origin through root .env.local ALLOWED_ORIGINS. For customer access, publish frontend\dist through your configured web server.'
}

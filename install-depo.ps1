<#
.SYNOPSIS
Advanced complete installation of backend and frontend; guided users run Setup-DEPO.cmd.

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
  [ValidateRange(1,3600)][int]$ServiceStartupTimeoutSeconds = 600,
  [switch]$EnableSpark,
  [switch]$EnableNeo4jSparkConnector,
  [switch]$EnablePostgresSparkConnector,
  [switch]$EnablePipelineScheduler,
  [switch]$SkipFrontend,
  [switch]$EnableOcr,
  [switch]$SkipBaselineProvisioning,
  [switch]$SkipDependencyInstall,
  [Alias('SynchronizeCredentials')][switch]$ReplaceExistingCredentials,
  [switch]$SkipReleasePreflight,
  [switch]$ForceReinstall,
  [switch]$StageOntologyUpdates
)

$ErrorActionPreference = 'Stop'
# Direct PowerShell invocation must protect nested release helpers too.
# This changes only this process; enforced organization policy remains authoritative.
if ((Get-ExecutionPolicy) -ne 'Bypass') {
  try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction Stop }
  catch { throw 'PowerShell policy blocked setup. Run Setup-DEPO.cmd from the release root. If organization Group Policy enforces signing, use an approved signed release or contact your administrator; machine policy was not changed.' }
  if ((Get-ExecutionPolicy) -ne 'Bypass') {
    throw 'Process execution-policy bypass is overridden by organization policy. Use an approved signed release; machine policy was not changed.'
  }
}

$root = $PSScriptRoot
$windows = Join-Path $root 'infra/windows'
. (Join-Path $windows 'native-install-command.ps1')
Invoke-DepoLoggedAction -Root $root -Name 'install' -AuditEnvFile $EnvFile -Action {
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not $SkipDependencyInstall) {
  $dependencyInstaller = Join-Path $windows 'install-depo.ps1'
  if (-not (Test-Path -LiteralPath $dependencyInstaller -PathType Leaf)) {
    throw 'Incomplete release: infra/windows/install-depo.ps1 is missing. Restore the complete release with its folder structure.'
  }
  $installerTokens = $null
  $installerErrors = $null
  $installerAst = [System.Management.Automation.Language.Parser]::ParseFile($dependencyInstaller, [ref]$installerTokens, [ref]$installerErrors)
  if ($installerErrors.Count -gt 0) { throw 'Dependency installer contains syntax errors. Restore infra/windows/install-depo.ps1 from the matching release.' }
  $installerParameters = @($installerAst.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
  foreach ($requiredParameter in @('CheckPrerequisites', 'EnvFile', 'Python', 'SkipFrontend', 'EnableOcr')) {
    if ($requiredParameter -notin $installerParameters) {
      throw "Mismatched release: infra/windows/install-depo.ps1 lacks -$requiredParameter. Restore the matching dependency installer, not the repository-root launcher. Preserve environment files and the database."
    }
  }
}

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
. (Join-Path $windows 'runtime-config.ps1')
Write-Host "Deployment environment file: $envPath"
$settings = Read-DepoEnvironment -Root $root -EnvFile $envPath
. (Join-Path $windows 'deployment-process-guards.ps1')
Invoke-DepoStage 'Stopped backend verification (before installation or migrations)' {
  Assert-DepoWindowsManagementAccess
  Assert-DepoDeploymentStopped -Root $root
}
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
if ($effectiveSpark) {
  Assert-DepoSparkRuntime $settings.DEPO_SPARK_HOME $settings.DEPO_JAVA_HOME $settings.DEPO_HADOOP_HOME $settings.DEPO_SPARK_OUTPUT_ROOT
  if ($effectivePostgresConnector) { Assert-DepoSparkPostgresConfiguration -Values $settings }
  if ($effectiveConnector -and (-not $settings.DEPO_SPARK_NEO4J_PACKAGE -or $settings.DEPO_SPARK_NEO4J_PACKAGE -match '<.*>')) {
    throw 'DEPO_SPARK_NEO4J_PACKAGE is required for the selected Neo4j connector.'
  }
}

if (-not $SkipDependencyInstall) {
  Invoke-DepoStage 'Prerequisites' {
    & (Join-Path $windows 'install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend -EnableOcr:$EnableOcr -CheckPrerequisites -EnvFile $envPath
  }
  Invoke-DepoStage 'Application dependencies and frontend build' {
    & (Join-Path $windows 'install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend -EnableOcr:$EnableOcr -EnvFile $envPath -ForceReinstall:$ForceReinstall
  }
}

if ($SkipDependencyInstall -and -not $SkipFrontend) {
  Invoke-DepoStage 'Frontend rebuild using installed dependencies' {
    & (Join-Path $windows 'build-depo-frontend.ps1') -EnvFile $envPath
  }
}
if (-not $SkipFrontend -and -not (Test-Path -LiteralPath (Join-Path $root 'frontend/dist/index.html') -PathType Leaf)) {
  throw 'Frontend build output is missing. No services were started.'
}

Invoke-DepoStage 'Deployment configuration validation' {
  & (Join-Path $root 'infra\deployment\test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks
}
if ($SkipDependencyInstall) {
  Invoke-DepoStage 'Existing service runtime availability' {
    . (Join-Path $windows 'service-runtimes.ps1')
    $manifest = Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
    foreach ($entry in (@($manifest.services) + @($manifest.workers))) {
      $runtime = Get-DepoServicePython -Root $root -ServiceId $entry.id -Mode $settings.DEPO_SERVICE_RUNTIME_MODE
      if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) { throw "Missing runtime for '$($entry.id)'. Omit -SkipDependencyInstall to install this release's dependencies. No migrations were applied." }
    }
  }
}
Invoke-DepoStage 'Selected PostgreSQL runtime startup' {
  & (Join-Path $windows 'start-depo-postgres.ps1') -EnvFile $envPath
}
Invoke-DepoStage 'PostgreSQL URL connectivity' {
  & (Join-Path $root 'infra\postgres\test-postgres-connectivity.ps1') -EnvFile $envPath
}
$script:depoDetectedMode = $null
Invoke-DepoStage 'Detect first installation or existing database' {
  Import-DepoEnvironment -Root $root -EnvFile $envPath
  Push-Location $root
  try {
    $info = Invoke-DepoNativeCommand -Executable (Join-Path $root 'backend/.dt_venv/Scripts/python.exe') -NativeArguments @('-m','backend.depo_platform.ontology_upgrade','--root',$root,'--detect')
    if ($LASTEXITCODE -ne 0) { throw 'Deployment detection failed; no migrations applied.' }
    $script:depoDetectedMode = ($info | ConvertFrom-Json).mode
    if ($script:depoDetectedMode -notin @('new','existing')) { throw 'Invalid deployment detection response' }
    Write-Host "Deployment mode: $script:depoDetectedMode"
  } finally { Pop-Location }
}
Invoke-DepoStage 'PostgreSQL schema migration' {
  & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') -Action InitializeDatabase -EnvFile $envPath -Profile $Profile
}
if ($settings['AUTH_MODE'] -eq 'token' -and $settings['DEPO_CREDENTIAL_STORE'] -eq 'postgres') {
  $credentialStage = if ($ReplaceExistingCredentials) { 'Central credential synchronization from selected environment (before service launch)' } else { 'Central credential validation (before service launch)' }
  Invoke-DepoStage $credentialStage {
    & (Join-Path $windows 'apply-depo-service-credentials.ps1') -EnvFile $envPath -ReplaceExisting:$ReplaceExistingCredentials
  }
} elseif ($ReplaceExistingCredentials) {
  throw '-ReplaceExistingCredentials requires AUTH_MODE=token and DEPO_CREDENTIAL_STORE=postgres.'
}
Invoke-DepoStage 'Neo4j schema provisioning and validation' {
  # The schema file is idempotent. Provision it before the read-only release
  # preflight so a first Production installation cannot fail on missing indexes.
  & (Join-Path $windows 'test-depo-neo4j.ps1') -EnvFile $envPath -Bootstrap
  if ($Profile -eq 'Production') {
    & (Join-Path $windows 'test-depo-neo4j.ps1') -EnvFile $envPath -Production
  }
}
if ($effectiveSpark) {
  Invoke-DepoStage 'Spark runtime smoke test' {
    & (Join-Path $windows 'test-depo-spark.ps1') -EnvFile $envPath
  }
  if ($effectiveConnector) {
    Invoke-DepoStage 'Spark Neo4j connector smoke test' {
      & (Join-Path $windows 'test-depo-spark.ps1') -EnvFile $envPath -Neo4jConnector
    }
  }
  if ($effectivePostgresConnector) {
    Invoke-DepoStage 'Spark PostgreSQL connector smoke test' {
      & (Join-Path $windows 'test-depo-spark.ps1') -EnvFile $envPath -PostgresConnector
    }
  }
}
Invoke-DepoStage 'Service startup and endpoint validation' {
  $startParameters = @{ Action = 'Start'; EnvFile = $envPath; Profile = $Profile; ServiceStartupTimeoutSeconds = $ServiceStartupTimeoutSeconds }
  if ($effectiveSpark) { $startParameters.EnableSpark = $true }
  if ($effectiveConnector) { $startParameters.EnableNeo4jSparkConnector = $true }
  if ($effectivePostgresConnector) { $startParameters.EnablePostgresSparkConnector = $true }
  if ($effectiveScheduler) { $startParameters.EnablePipelineScheduler = $true }
  if ($SkipBaselineProvisioning) { $startParameters.SkipBaselineProvisioning = $true }
  & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') @startParameters
}
if ($settings['AUTH_MODE'] -eq 'token' -and $settings['DEPO_CREDENTIAL_STORE'] -eq 'postgres') {
  Invoke-DepoStage 'Central browser-session authentication verification' {
    & (Join-Path $windows 'test-depo-browser-session.ps1') -EnvFile $envPath
    if ($settings['DEPO_ROUTING_MODE'] -eq 'gateway') {
      & (Join-Path $windows 'test-depo-browser-session.ps1') -EnvFile $envPath -Gateway
    }
  }
}
if (-not $SkipReleasePreflight) {
  Invoke-DepoStage 'Release preflight' {
    $releaseParameters = @{Action='ReleasePreflight'; EnvFile=$envPath; Profile=$Profile}
    if ($Profile -eq 'Bootstrap' -and $settings.AUTH_MODE -eq 'disabled') { $releaseParameters.LocalInsecureDemo = $true }
    & (Join-Path $root 'infra\deployment\invoke-depo-lifecycle.ps1') @releaseParameters
  }
}

if ($settings['AUTH_MODE'] -eq 'token' -and $settings['DEPO_CREDENTIAL_STORE'] -eq 'postgres') {
  Write-Host 'Next: verify central browser authentication with infra/windows/test-depo-browser-session.ps1 using the same -EnvFile.'
  if ($settings['DEPO_BROWSER_AUTH_MODE'] -eq 'local') { Write-Host 'The local frontend connects registered credentials automatically; no API-key copy/paste is required.' }
  else { Write-Host 'Use Admin to connect the configured browser identity for manual or gateway access.' }
}
if (-not $SkipFrontend) {
  Invoke-DepoStage 'Frontend startup and readiness' {
    & (Join-Path $windows 'start-depo-frontend.ps1') -EnvFile $envPath
  }
  Write-Host 'Installation complete. Open the frontend URL reported above. Rerun the same installer after a failure; verified dependencies are reused.'

}


if ($script:depoDetectedMode -eq 'existing') {
  Invoke-DepoStage 'Existing ontology upgrade review' {
    Push-Location $root
    try {
      $arguments=@('-m','backend.depo_platform.ontology_upgrade','--root',$root)
      if($StageOntologyUpdates){$arguments+='--stage'}
      . (Join-Path $windows 'service-runtimes.ps1')
      $upgradePython=Get-DepoServicePython -Root $root -ServiceId 'ingestion' -Mode $settings.DEPO_SERVICE_RUNTIME_MODE
      Invoke-DepoNativeCommand -Executable $upgradePython -NativeArguments $arguments
      if($LASTEXITCODE -ne 0){throw 'Ontology upgrade review failed. Existing publications are retained; rerun setup to resume.'}
      Write-Host 'Review logs/installation/ontology-upgrade-v2/plan.json. Corrected drafts require lifecycle approval and publication through Ontology Junction. Existing publications are retained until that review.'
    } finally { Pop-Location }
  }
} else { Write-Host 'First deployment: legacy ontology upgrades skipped.' }

Write-Host "`nDEPO Windows installation completed successfully." -ForegroundColor Green

}

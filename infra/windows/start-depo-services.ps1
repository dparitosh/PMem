param(
  [string]$EnvFile = ".env.local",
  [string]$PostgresBinDir = "",
  [string]$PostgresDataDir = "",
  [string]$BindHost = "",
  [ValidateRange(1, 3600)]
  [int]$ServiceStartupTimeoutSeconds = 300,
  [switch]$SkipPostgres,
  [switch]$EnableSpark,
  [switch]$EnablePipelineScheduler,
  [switch]$EnableNeo4jSparkConnector,
  [switch]$EnablePostgresSparkConnector
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root "backend\.dt_venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Project Python runtime was not found: $python" }

. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'process-control.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$configuredAllowedOrigins = [string]$env:ALLOWED_ORIGINS
$corsProbeOrigin = @($configuredAllowedOrigins.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })[0]
if (-not $corsProbeOrigin) { throw 'ALLOWED_ORIGINS must contain at least one browser origin.' }
# Aura exports use USERNAME/PASSWORD while the customer template uses the
# shorter USER/PASS names. Normalize only the child-process environment so
# every Spark launch path receives the same credentials without duplicating
# them in the customer configuration file.
if (-not $env:NEO4J_USER -and $env:NEO4J_USERNAME) { $env:NEO4J_USER = $env:NEO4J_USERNAME }
if (-not $env:NEO4J_PASS -and $env:NEO4J_PASSWORD) { $env:NEO4J_PASS = $env:NEO4J_PASSWORD }
if (-not $PostgresBinDir) { $PostgresBinDir = $env:DEPO_POSTGRES_BIN_DIR }
if (-not $PostgresDataDir) { $PostgresDataDir = $env:DEPO_POSTGRES_DATA_DIR }
if (-not $BindHost) { $BindHost = if ($env:DEPO_SERVICE_HOST) { $env:DEPO_SERVICE_HOST } else { "127.0.0.1" } }
$peerHost = Get-DepoProbeHost $BindHost
# Local peer URLs keep the control plane usable without duplicating service
# addresses in every developer .env.local. Customer deployments override them
# with private service discovery addresses.
$serviceUrls = @{
  AGENTIC_SERVICE_URL = 8012; ONTOLOGY_SERVICE_URL = 8011; GRAPH_SERVICE_URL = 8013; INGESTION_SERVICE_URL = 8014
  OSLC_SERVICE_URL = 8015; QIF_SERVICE_URL = 8010; DATA_CATALOG_URL = 8016
  DATA_PRODUCT_SERVICE_URL = 8017; CEIM_SERVICE_URL = 8018; DATA_PIPELINE_SERVICE_URL = 8019
}
foreach ($entry in $serviceUrls.GetEnumerator()) {
  if (-not [Environment]::GetEnvironmentVariable($entry.Key, 'Process')) {
    Set-Item -Path ("Env:" + $entry.Key) -Value ("http://${peerHost}:$($entry.Value)/api/v1")
  }
}

# Fail before launching processes when the agentic runtime is incomplete.
Push-Location $root
try {
  & $python -m backend.agentic_service.configuration
  if ($LASTEXITCODE -ne 0) { throw 'Agentic configuration validation failed. Configure the listed settings before starting services.' }
} finally { Pop-Location }


$requestedSparkOptions = Resolve-DepoSparkOptions $PSBoundParameters

if (-not $SkipPostgres) {
  & (Join-Path $PSScriptRoot 'start-depo-postgres.ps1') -EnvFile $EnvFile -PostgresBinDir $PostgresBinDir -PostgresDataDir $PostgresDataDir
}

# Use the same reviewed migration entry point as schema-only upgrades. This
# preserves the SQLSTATE-based corrective action and guarantees startup stops
# before any service process is created when the database is incompatible.
& (Join-Path $PSScriptRoot 'initialize-depo-schema.ps1') -EnvFile $EnvFile

# Apply CLI overrides after schema initialization reloads the selected file.
$sparkOptions = $requestedSparkOptions
$EnableSpark = $sparkOptions.EnableSpark
$EnableNeo4jSparkConnector = $sparkOptions.EnableNeo4jSparkConnector
$EnablePipelineScheduler = $sparkOptions.EnablePipelineScheduler
$EnablePostgresSparkConnector = $sparkOptions.EnablePostgresSparkConnector
$env:DEPO_SPARK_ENABLED = ([bool]$EnableSpark).ToString().ToLowerInvariant()
$env:DEPO_SPARK_NEO4J_ENABLED = ([bool]$EnableNeo4jSparkConnector).ToString().ToLowerInvariant()
$env:DEPO_PIPELINE_SCHEDULER_ENABLED = ([bool]$EnablePipelineScheduler).ToString().ToLowerInvariant()
$env:DEPO_SPARK_POSTGRES_ENABLED = ([bool]$EnablePostgresSparkConnector).ToString().ToLowerInvariant()
if (-not $env:DEPO_PIPELINE_EXECUTION_MODE) { $env:DEPO_PIPELINE_EXECUTION_MODE = 'worker' }
if ($env:DEPO_PIPELINE_EXECUTION_MODE -notin @('worker','inline')) { throw 'DEPO_PIPELINE_EXECUTION_MODE must be worker or inline.' }
# Spark is deliberately opt-in: the data-pipeline API stays healthy without
# allocating a JVM, while this switch lets an operator enable the local Spark
# execution plane for bounded interactive transformations and telemetry.
if ($EnableSpark) {
  $env:DEPO_SPARK_ENABLED = 'true'
  Assert-DepoSparkRuntime $env:DEPO_SPARK_HOME $env:DEPO_JAVA_HOME $env:DEPO_HADOOP_HOME
  $env:SPARK_HOME = $env:DEPO_SPARK_HOME
  $env:JAVA_HOME = $env:DEPO_JAVA_HOME
  $env:HADOOP_HOME = $env:DEPO_HADOOP_HOME
  $env:hadoop_home = $env:DEPO_HADOOP_HOME
  $env:PATH = (Join-Path $env:DEPO_HADOOP_HOME 'bin') + ';' + $env:PATH
  $env:PYSPARK_PYTHON = $python
  if ($EnableNeo4jSparkConnector) {
    $env:DEPO_SPARK_NEO4J_ENABLED = 'true'
    if (-not $env:DEPO_SPARK_NEO4J_PACKAGE) { $env:DEPO_SPARK_NEO4J_PACKAGE = 'org.neo4j.connectors:spark:6.0.0-s_2.13' }
    $requiredNeo4jKeys = @('NEO4J_URI')
    if ($env:NEO4J_AUTH_MODE -ne 'none') { $requiredNeo4jKeys += @('NEO4J_USER', 'NEO4J_PASS') }
    foreach ($key in $requiredNeo4jKeys) {
      if (-not [Environment]::GetEnvironmentVariable($key, 'Process')) { throw "$key is required when -EnableNeo4jSparkConnector is used." }
    }
  }
  if ($EnablePostgresSparkConnector) {
    $values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
    Assert-DepoSparkPostgresConfiguration -Values $values
  }
}
if ($EnablePipelineScheduler) {
  $env:DEPO_PIPELINE_SCHEDULER_ENABLED = 'true'
}


$stateDir = Join-Path $root "logs\windows-services"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$manifestPath = Join-Path $root "infra\deployment\services.json"
if (-not (Test-Path $manifestPath)) { throw "Deployment service manifest was not found: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$services = @($manifest.services | ForEach-Object { @{ Name=$_.id; Module=$_.module; Port=[int]$_.port } })
$services += @($manifest.workers | ForEach-Object { @{ Name=$_.id; Module=$_.module; Port=$null } })
if ($services.Count -ne 12) { throw "Deployment manifest must define ten HTTP services and two workers." }
$startedServices = @()
try {
foreach ($service in $services) {
  $pidFile = Join-Path $stateDir "$($service.Name).pid"
  # A PID may be reused after an unplanned shutdown.  Reuse it only when the
  # expected Python executable is still alive *and* the service port is
  # listening; otherwise an old PID can silently prevent recovery.
  $portListening = $false
  if ($service.Port) {
    $portListening = [bool](Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  }
  if (Test-Path $pidFile) {
    $recordedPid = [int](Get-Content $pidFile)
    $existing = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
    $processDetails = if ($existing) { Get-CimInstance Win32_Process -Filter "ProcessId = $recordedPid" -ErrorAction SilentlyContinue } else { $null }
    $expectedProcess = $existing -and $processDetails -and
      $processDetails.ExecutablePath -eq $python -and
      $processDetails.CommandLine -match [regex]::Escape($service.Module)
    if ($expectedProcess -and ($null -eq $service.Port -or (Test-DepoListener $recordedPid $python $service.Module $service.Port $BindHost))) { continue }
    if ($expectedProcess -and $portListening) { throw "Tracked service '$($service.Name)' does not own the expected listener/binding. Stop it before changing BindHost; PID tracking is retained." }
    if ($expectedProcess -and -not $portListening) { Stop-DepoProcessTree $recordedPid $python $service.Module }
    Remove-Item -LiteralPath $pidFile -Force
  }
  # A healthy process may have lost its PID file (for example after a manual
  # recovery); never create a competing listener in that case.
  if ($service.Port -and $portListening) {
    throw "Port $($service.Port) for '$($service.Name)' is already in use by an untracked process; refusing to start a competing service. Stop the owner or remove the stale listener and retry."
  }
  $arguments = if ($service.Port) { "-m uvicorn $($service.Module) --host $BindHost --port $($service.Port) --no-proxy-headers" } else { "-m $($service.Module)" }
  $stdout = Join-Path $stateDir "$($service.Name).out.log"
  $stderr = Join-Path $stateDir "$($service.Name).err.log"
  $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
  # Roll back only processes launched by this invocation. Existing healthy
  # services are intentionally not part of a failed start attempt.
  $startedServices += @{ ProcessId = $process.Id; PidFile = $pidFile; Module = $service.Module }
  Set-Content -LiteralPath $pidFile -Value $process.Id
}

foreach ($service in $services | Where-Object { $_.Port }) {
  Write-Host "Waiting up to $ServiceStartupTimeoutSeconds seconds for '$($service.Name)' readiness on port $($service.Port)..."
  $deadline = (Get-Date).AddSeconds($ServiceStartupTimeoutSeconds)
  $ready = $false
  $corsMismatch = ''
  do {
    try {
      # Liveness means a Python process exists; readiness also verifies every
      # configured shared dependency before a service is announced usable.
      $response = Invoke-WebRequest -UseBasicParsing "http://${peerHost}:$($service.Port)/readyz" -Headers @{ Origin = $corsProbeOrigin } -TimeoutSec 5
      $ready = $response.StatusCode -eq 200 -and (Test-DepoListener ([int](Get-Content -LiteralPath (Join-Path $stateDir "$($service.Name).pid"))) $python $service.Module $service.Port $BindHost)
      if ($ready) {
        $actualCorsOrigin = [string]$response.Headers['Access-Control-Allow-Origin']
        if ($actualCorsOrigin -ne $corsProbeOrigin) {
          $corsMismatch = "DEPO service '$($service.Name)' is running with stale CORS configuration. Expected Access-Control-Allow-Origin '$corsProbeOrigin' but received '$actualCorsOrigin'. Stop all DEPO services, then start them again so .env.local is reloaded."
          $ready = $false
          break
        }
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while (-not $ready -and (Get-Date) -lt $deadline)
  if ($corsMismatch) { throw $corsMismatch }
  if (-not $ready) { throw "DEPO service '$($service.Name)' did not become ready within $ServiceStartupTimeoutSeconds seconds. Check $stateDir\$($service.Name).err.log. For a slower cold start, retry with -ServiceStartupTimeoutSeconds 600." }
  if ($env:AUTH_MODE -eq 'token') {
    try {
      $access = Invoke-RestMethod -Uri "http://${peerHost}:$($service.Port)/auth/access" -Headers @{ Authorization = "Bearer $($env:GRAPH_READ_TOKEN)" } -TimeoutSec 10
      if ($access.status -ne 'authorized') { throw 'Read access was not authorized.' }
    } catch { throw "Service '$($service.Name)' does not accept the configured read key. Stop and restart all services after key changes; deploy matching backend modules if /auth/access is missing." }
  }

}
# Workers have no readiness port. Require every worker started by this
# invocation to remain alive through the complete HTTP-service readiness pass.
foreach ($worker in $services | Where-Object { $null -eq $_.Port }) {
  $pidFile = Join-Path $stateDir "$($worker.Name).pid"
  if (-not (Test-Path -LiteralPath $pidFile)) { throw "Worker '$($worker.Name)' has no PID file." }
  $workerPid = [int](Get-Content -LiteralPath $pidFile)
  if (-not (Get-Process -Id $workerPid -ErrorAction SilentlyContinue)) {
    throw "DEPO worker '$($worker.Name)' exited during startup. Check $stateDir\$($worker.Name).err.log."
  }
}
if ($env:DEPO_PIPELINE_EXECUTION_MODE -eq 'worker') {
  $executionDeadline = (Get-Date).AddSeconds(30)
  $executionReady = $false
  do {
    try {
      $execution = Invoke-RestMethod -Uri "http://${peerHost}:8019/api/v1/pipeline/execution-ready" -TimeoutSec 5
      $executionReady = $execution.status -eq 'ready'
    } catch { Start-Sleep -Milliseconds 500 }
  } while (-not $executionReady -and (Get-Date) -lt $executionDeadline)
  if (-not $executionReady) { throw 'Pipeline API is alive but no current worker heartbeat is available. Check data-pipeline-worker logs and PostgreSQL connectivity.' }
}
} catch {
  foreach ($startedService in @($startedServices | Sort-Object { [int]$_.ProcessId } -Descending)) {
    try { Stop-DepoProcessTree $startedService.ProcessId $python $startedService.Module }
    catch { Write-Warning "Cleanup failed for $($startedService.Module): $($_.Exception.Message)"; continue }
    if (Test-Path -LiteralPath $startedService.PidFile) {
      Remove-Item -LiteralPath $startedService.PidFile -Force -ErrorAction SilentlyContinue
    }
  }
  throw
}

Write-Host "DEPO services are ready on $BindHost. Use infra/windows/stop-depo-services.ps1 to stop them."

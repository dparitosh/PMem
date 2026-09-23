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
  [switch]$EnableNeo4jSparkConnector
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root "backend\.dt_venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Project Python runtime was not found: $python" }

. (Join-Path $PSScriptRoot 'runtime-config.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
# Aura exports use USERNAME/PASSWORD while the customer template uses the
# shorter USER/PASS names. Normalize only the child-process environment so
# every Spark launch path receives the same credentials without duplicating
# them in the customer configuration file.
if (-not $env:NEO4J_USER -and $env:NEO4J_USERNAME) { $env:NEO4J_USER = $env:NEO4J_USERNAME }
if (-not $env:NEO4J_PASS -and $env:NEO4J_PASSWORD) { $env:NEO4J_PASS = $env:NEO4J_PASSWORD }
if (-not $PostgresBinDir) { $PostgresBinDir = $env:DEPO_POSTGRES_BIN_DIR }
if (-not $PostgresDataDir) { $PostgresDataDir = $env:DEPO_POSTGRES_DATA_DIR }
if (-not $BindHost) { $BindHost = if ($env:DEPO_SERVICE_HOST) { $env:DEPO_SERVICE_HOST } else { "127.0.0.1" } }
$peerHost = if ($BindHost -in @('0.0.0.0','::')) { '127.0.0.1' } else { $BindHost }
  if ($peerHost.Contains(':') -and -not $peerHost.StartsWith('[')) { $peerHost = '[' + $peerHost + ']' }
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

$sparkOptions = Resolve-DepoSparkOptions $PSBoundParameters
$EnableSpark = $sparkOptions.EnableSpark
$EnableNeo4jSparkConnector = $sparkOptions.EnableNeo4jSparkConnector
$EnablePipelineScheduler = $sparkOptions.EnablePipelineScheduler
$env:DEPO_SPARK_ENABLED = ([bool]$EnableSpark).ToString().ToLowerInvariant()
$env:DEPO_SPARK_NEO4J_ENABLED = ([bool]$EnableNeo4jSparkConnector).ToString().ToLowerInvariant()
$env:DEPO_PIPELINE_SCHEDULER_ENABLED = ([bool]$EnablePipelineScheduler).ToString().ToLowerInvariant()
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
    foreach ($key in 'NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASS') {
      if (-not [Environment]::GetEnvironmentVariable($key, 'Process')) { throw "$key is required when -EnableNeo4jSparkConnector is used." }
    }
  }
}
if ($EnablePipelineScheduler) {
  if (-not $EnableSpark) { throw "-EnablePipelineScheduler requires -EnableSpark." }
  $env:DEPO_PIPELINE_SCHEDULER_ENABLED = 'true'
}

if (-not $SkipPostgres -and $env:DEPO_POSTGRES_MODE -ne 'external') {
  if ($env:DEPO_POSTGRES_MODE -notin @('service','portable')) { throw 'Set DEPO_POSTGRES_MODE=external, service or portable. No PostgreSQL instance is selected automatically.' }
  $postgres = $null
  if ($env:DEPO_POSTGRES_MODE -eq 'service') {
    if (-not $env:DEPO_POSTGRES_SERVICE_NAME) { throw 'DEPO_POSTGRES_SERVICE_NAME is required for service mode.' }
    $postgres = Get-Service -Name $env:DEPO_POSTGRES_SERVICE_NAME -ErrorAction Stop
  }
  if ($postgres) {
    if ($postgres.Status -ne 'Running') { Start-Service -Name $postgres.Name; $postgres.WaitForStatus('Running', [TimeSpan]::FromSeconds(30)) }
  } else {
    if (-not $PostgresBinDir -or -not $PostgresDataDir) { throw 'Portable PostgreSQL requires DEPO_POSTGRES_BIN_DIR and DEPO_POSTGRES_DATA_DIR.' }
    $pgCtl = Join-Path $PostgresBinDir 'pg_ctl.exe'
    $pgVersion = Join-Path $PostgresDataDir 'PG_VERSION'
    if (-not (Test-Path $pgCtl) -or -not (Test-Path $pgVersion)) {
      throw "No PostgreSQL Windows service was found. Set -PostgresBinDir and -PostgresDataDir to an initialized PostgreSQL installation, or use -SkipPostgres for a remote instance."
    }
    $pgIsReady = Join-Path $PostgresBinDir 'pg_isready.exe'
    if (-not (Test-Path $pgIsReady)) { throw "PostgreSQL readiness executable was not found: $pgIsReady" }
    & $pgCtl status -D $PostgresDataDir | Out-Null
    if ($LASTEXITCODE -ne 0) {
      # Keep the active log outside PGDATA: crash recovery fsyncs that tree,
      # and an open Windows log handle can cause sharing violations there.
      $postgresLogDir = Join-Path $root 'logs\windows-services'
      New-Item -ItemType Directory -Path $postgresLogDir -Force | Out-Null
      $logFile = Join-Path $postgresLogDir 'postgres.log'
      & $pgCtl start -D $PostgresDataDir -l $logFile -w -t 60
      if ($LASTEXITCODE -ne 0) { throw "PostgreSQL could not start. See $logFile." }
    }
  }
}

Push-Location $root
try {
  & $python -m backend.depo_platform.database_setup
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL migration/column verification failed.' }
} finally { Pop-Location }

$stateDir = Join-Path $root "logs\windows-services"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$manifestPath = Join-Path $root "infra\deployment\services.json"
if (-not (Test-Path $manifestPath)) { throw "Deployment service manifest was not found: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$services = @($manifest.services | ForEach-Object { @{ Name=$_.id; Module=$_.module; Port=[int]$_.port } })
$services += @($manifest.workers | ForEach-Object { @{ Name=$_.id; Module=$_.module; Port=$null } })
if ($services.Count -ne 11) { throw "Deployment manifest must define ten HTTP services and one worker." }
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
    $expectedProcess = $existing -and $existing.Path -eq $python
    if ($expectedProcess -and ($null -eq $service.Port -or $portListening)) { continue }
    if ($expectedProcess -and -not $portListening) { Stop-Process -Id $recordedPid -Force -ErrorAction SilentlyContinue }
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
  Set-Content -Path $pidFile -Value $process.Id
  # Roll back only processes launched by this invocation. Existing healthy
  # services are intentionally not part of a failed start attempt.
  $startedServices += @{ ProcessId = $process.Id; PidFile = $pidFile }
}

foreach ($service in $services | Where-Object { $_.Port }) {
  Write-Host "Waiting up to $ServiceStartupTimeoutSeconds seconds for '$($service.Name)' readiness on port $($service.Port)..."
  $deadline = (Get-Date).AddSeconds($ServiceStartupTimeoutSeconds)
  $ready = $false
  do {
    try {
      # Liveness means a Python process exists; readiness also verifies every
      # configured shared dependency before a service is announced usable.
      $response = Invoke-WebRequest -UseBasicParsing "http://${peerHost}:$($service.Port)/readyz" -TimeoutSec 5
      $ready = $response.StatusCode -eq 200
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while (-not $ready -and (Get-Date) -lt $deadline)
  if (-not $ready) { throw "DEPO service '$($service.Name)' did not become ready within $ServiceStartupTimeoutSeconds seconds. Check $stateDir\$($service.Name).err.log. For a slower cold start, retry with -ServiceStartupTimeoutSeconds 600." }
}
} catch {
  foreach ($startedService in @($startedServices | Sort-Object { [int]$_.ProcessId } -Descending)) {
    Stop-Process -Id $startedService.ProcessId -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $startedService.PidFile) {
      Remove-Item -LiteralPath $startedService.PidFile -Force -ErrorAction SilentlyContinue
    }
  }
  throw
}

Write-Host "DEPO services are ready on $BindHost. Use infra/windows/stop-depo-services.ps1 to stop them."

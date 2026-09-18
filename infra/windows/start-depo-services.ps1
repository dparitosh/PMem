param(
  [string]$EnvFile = ".env.local",
  [string]$PostgresBinDir = "D:\codevita\postgresql-16\pgsql\bin",
  [string]$PostgresDataDir = "D:\codevita\postgresql-16\data",
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
if (-not (Test-Path (Join-Path $root $EnvFile))) { throw "Create $EnvFile from .env.postgres.example first." }

Get-Content (Join-Path $root $EnvFile) | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ("Env:" + $matches[1].Trim()) -Value $matches[2].Trim() }
}
if (-not $BindHost) { $BindHost = if ($env:DEPO_SERVICE_HOST) { $env:DEPO_SERVICE_HOST } else { "127.0.0.1" } }
# Local peer URLs keep the control plane usable without duplicating service
# addresses in every developer .env.local. Customer deployments override them
# with private service discovery addresses.
$serviceUrls = @{
  ONTOLOGY_SERVICE_URL = 8011; GRAPH_SERVICE_URL = 8013; INGESTION_SERVICE_URL = 8014
  OSLC_SERVICE_URL = 8015; QIF_SERVICE_URL = 8010; DATA_CATALOG_URL = 8016
  DATA_PRODUCT_SERVICE_URL = 8017; CEIM_SERVICE_URL = 8018; DATA_PIPELINE_SERVICE_URL = 8019
}
foreach ($entry in $serviceUrls.GetEnumerator()) {
  if (-not [Environment]::GetEnvironmentVariable($entry.Key, 'Process')) {
    Set-Item -Path ("Env:" + $entry.Key) -Value ("http://${BindHost}:$($entry.Value)/api/v1")
  }
}

# Spark is deliberately opt-in: the data-pipeline API stays healthy without
# allocating a JVM, while this switch lets an operator enable the local Spark
# execution plane for bounded interactive transformations and telemetry.
if ($EnableSpark) {
  $env:DEPO_SPARK_ENABLED = 'true'
  if (-not $env:DEPO_SPARK_HOME) { $env:DEPO_SPARK_HOME = 'D:\DEPO\runtime\spark-4.1.2-bin-hadoop3' }
  if (-not $env:DEPO_JAVA_HOME) { $env:DEPO_JAVA_HOME = 'D:\DEPO\runtime\jdk-21\jdk-21.0.12.1+1' }
  if (-not $env:DEPO_HADOOP_HOME) { $env:DEPO_HADOOP_HOME = 'D:\DEPO\runtime\hadoop' }
  if (-not (Test-Path $env:DEPO_SPARK_HOME)) { throw "Spark runtime was not found: $env:DEPO_SPARK_HOME" }
  if (-not (Test-Path $env:DEPO_JAVA_HOME)) { throw "Java runtime was not found: $env:DEPO_JAVA_HOME" }
  if (-not (Test-Path (Join-Path $env:DEPO_HADOOP_HOME 'bin\winutils.exe'))) { throw "Windows Hadoop helper was not found: $env:DEPO_HADOOP_HOME\bin\winutils.exe" }
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

if (-not $SkipPostgres) {
  $postgres = Get-Service | Where-Object { $_.Name -match '^postgresql' -or $_.DisplayName -match 'PostgreSQL' } | Select-Object -First 1
  if ($postgres) {
    if ($postgres.Status -ne 'Running') { Start-Service -Name $postgres.Name; $postgres.WaitForStatus('Running', [TimeSpan]::FromSeconds(30)) }
  } else {
    $pgCtl = Join-Path $PostgresBinDir 'pg_ctl.exe'
    $pgVersion = Join-Path $PostgresDataDir 'PG_VERSION'
    if (-not (Test-Path $pgCtl) -or -not (Test-Path $pgVersion)) {
      throw "No PostgreSQL Windows service was found. Set -PostgresBinDir and -PostgresDataDir to an initialized PostgreSQL installation, or use -SkipPostgres for a remote instance."
    }
    $pgIsReady = Join-Path $PostgresBinDir 'pg_isready.exe'
    if (-not (Test-Path $pgIsReady)) { throw "PostgreSQL readiness executable was not found: $pgIsReady" }
    & $pgIsReady -h 127.0.0.1 -p 5432 | Out-Null
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

& $python -c "from backend.mesh_store import PostgresRegistry; PostgresRegistry('startup_probe').put('ready', {'value': True})"
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL is not reachable with DEPO_DATABASE_URL." }

$stateDir = Join-Path $root "logs\windows-services"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$manifestPath = Join-Path $root "infra\deployment\services.json"
if (-not (Test-Path $manifestPath)) { throw "Deployment service manifest was not found: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$services = @($manifest.services | ForEach-Object { @{ Name=$_.id; Module=$_.module; Port=[int]$_.port } })
$services += @($manifest.workers | ForEach-Object { @{ Name=$_.id; Module=$_.module; Port=$null } })
if ($services.Count -ne 11) { throw "Deployment manifest must define ten HTTP services and one worker." }
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
}

foreach ($service in $services | Where-Object { $_.Port }) {
  Write-Host "Waiting up to $ServiceStartupTimeoutSeconds seconds for '$($service.Name)' readiness on port $($service.Port)..."
  $deadline = (Get-Date).AddSeconds($ServiceStartupTimeoutSeconds)
  $ready = $false
  do {
    try {
      # Liveness means a Python process exists; readiness also verifies every
      # configured shared dependency before a service is announced usable.
      $response = Invoke-WebRequest -UseBasicParsing "http://${BindHost}:$($service.Port)/readyz" -TimeoutSec 5
      $ready = $response.StatusCode -eq 200
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while (-not $ready -and (Get-Date) -lt $deadline)
  if (-not $ready) { throw "DEPO service '$($service.Name)' did not become ready within $ServiceStartupTimeoutSeconds seconds. Check $stateDir\$($service.Name).err.log. For a slower cold start, retry with -ServiceStartupTimeoutSeconds 600." }
}

Write-Host "DEPO services are ready on $BindHost. Use infra/windows/stop-depo-services.ps1 to stop them."

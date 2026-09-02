param(
  [string]$EnvFile = ".env.local",
  [string]$PostgresBinDir = "D:\codevita\postgresql-16\pgsql\bin",
  [string]$PostgresDataDir = "D:\codevita\postgresql-16\data",
  [string]$BindHost = "",
  [int]$ServiceStartupTimeoutSeconds = 90,
  [switch]$SkipPostgres
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
      $logFile = Join-Path $PostgresDataDir 'depo-postgres.log'
      & $pgCtl start -D $PostgresDataDir -l $logFile -w -t 60
      if ($LASTEXITCODE -ne 0) { throw "PostgreSQL could not start. See $logFile." }
    }
  }
}

& $python -c "from backend.mesh_store import PostgresRegistry; PostgresRegistry('startup_probe').put('ready', {'value': True})"
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL is not reachable with DEPO_DATABASE_URL." }

$stateDir = Join-Path $root "logs\windows-services"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$services = @(
  @{ Name='catalog'; Module='backend.data_catalog_service.app:app'; Port=8016 },
  @{ Name='data-products'; Module='backend.data_product_service.app:app'; Port=8017 },
  @{ Name='data-product-outbox'; Module='backend.data_product_service.worker'; Port=$null },
  @{ Name='ontology'; Module='backend.ontology_service.app:app'; Port=8011 },
  @{ Name='graph'; Module='backend.graph_service.app:app'; Port=8013 },
  @{ Name='ingestion'; Module='backend.ingestion_service.app:app'; Port=8014 },
  @{ Name='oslc'; Module='backend.oslc_service.app:app'; Port=8015 },
  @{ Name='agentic'; Module='backend.agentic_service.app:app'; Port=8012 },
  @{ Name='schema-sets'; Module='backend.qif.app:app'; Port=8010 }
)
foreach ($service in $services) {
  $pidFile = Join-Path $stateDir "$($service.Name).pid"
  if (Test-Path $pidFile) { $existing = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue; if ($existing) { continue } }
  $arguments = if ($service.Port) { "-m uvicorn $($service.Module) --host $BindHost --port $($service.Port)" } else { "-m $($service.Module)" }
  $stdout = Join-Path $stateDir "$($service.Name).out.log"
  $stderr = Join-Path $stateDir "$($service.Name).err.log"
  $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
  Set-Content -Path $pidFile -Value $process.Id
}

foreach ($service in $services | Where-Object { $_.Port }) {
  $deadline = (Get-Date).AddSeconds($ServiceStartupTimeoutSeconds)
  $ready = $false
  do {
    try {
      $response = Invoke-WebRequest -UseBasicParsing "http://${BindHost}:$($service.Port)/healthz" -TimeoutSec 3
      $ready = $response.StatusCode -eq 200
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while (-not $ready -and (Get-Date) -lt $deadline)
  if (-not $ready) { throw "DEPO service '$($service.Name)' did not become ready within $ServiceStartupTimeoutSeconds seconds." }
}

Write-Host "DEPO services are ready on $BindHost. Use infra/windows/stop-depo-services.ps1 to stop them."

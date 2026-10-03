param([string]$EnvFile = '.env.local', [string]$PostgresBinDir = '', [string]$PostgresDataDir = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$pgSettings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $PostgresBinDir) { $PostgresBinDir = $pgSettings['DEPO_POSTGRES_BIN_DIR'] }
if (-not $PostgresDataDir) { $PostgresDataDir = $pgSettings['DEPO_POSTGRES_DATA_DIR'] }
if ($pgSettings['DEPO_POSTGRES_MODE'] -eq 'external') { return }
  if ($pgSettings['DEPO_POSTGRES_MODE'] -notin @('service','portable')) { throw 'Set DEPO_POSTGRES_MODE=external, service or portable. No PostgreSQL instance is selected automatically.' }
  $postgres = $null
  if ($pgSettings['DEPO_POSTGRES_MODE'] -eq 'service') {
    if (-not $pgSettings['DEPO_POSTGRES_SERVICE_NAME']) { throw 'DEPO_POSTGRES_SERVICE_NAME is required for service mode.' }
    $postgres = Get-Service -Name $pgSettings['DEPO_POSTGRES_SERVICE_NAME'] -ErrorAction Stop
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
Write-Host 'Selected local PostgreSQL runtime is started; connectivity is verified separately.'

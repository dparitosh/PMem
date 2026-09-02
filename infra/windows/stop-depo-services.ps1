param(
  [switch]$StopPostgres,
  [string]$PostgresBinDir = "D:\codevita\postgresql-16\pgsql\bin",
  [string]$PostgresDataDir = "D:\codevita\postgresql-16\data"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$expectedPython = (Join-Path $root "backend\.dt_venv\Scripts\python.exe").ToLowerInvariant()
$stateDir = Join-Path $root "logs\windows-services"
if (Test-Path $stateDir) {
  Get-ChildItem $stateDir -Filter '*.pid' | ForEach-Object {
    $process = Get-Process -Id (Get-Content $_.FullName) -ErrorAction SilentlyContinue
    # A PID can be reused after a prior run. Stop only this project's Python
    # runtime, never an unrelated Windows process with a matching stale PID.
    if ($process -and $process.Path -and $process.Path.ToLowerInvariant() -eq $expectedPython) {
      Stop-Process -Id $process.Id -Force
    }
    Remove-Item $_.FullName -Force
  }
}
if ($StopPostgres) {
  $postgres = Get-Service | Where-Object { $_.Name -match '^postgresql' -or $_.DisplayName -match 'PostgreSQL' } | Select-Object -First 1
  if ($postgres -and $postgres.Status -eq 'Running') {
    Stop-Service -Name $postgres.Name
  } elseif (Test-Path (Join-Path $PostgresBinDir 'pg_ctl.exe')) {
    $pgVersion = Join-Path $PostgresDataDir 'PG_VERSION'
    if (Test-Path $pgVersion) { & (Join-Path $PostgresBinDir 'pg_ctl.exe') stop -D $PostgresDataDir -m fast -w -t 60 }
  }
}
Write-Host "DEPO services stopped."

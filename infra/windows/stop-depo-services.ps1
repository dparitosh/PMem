param(
  [switch]$StopPostgres,
  [string]$EnvFile = '.env.local',
  [string]$PostgresBinDir = "",
  [string]$PostgresDataDir = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$expectedPython = (Join-Path $root "backend\.dt_venv\Scripts\python.exe").ToLowerInvariant()
$stateDir = Join-Path $root "logs\windows-services"
$manifestPath = Join-Path $root "infra\deployment\services.json"
. (Join-Path $PSScriptRoot 'process-control.ps1')
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Service manifest is required for safe shutdown.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$entries = @($manifest.workers) + @($manifest.services)
# Discover verified launchers even if tracking was lost. Shared tree control
# checks creation times, stops children first, and verifies listener cleanup.
$snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
foreach ($entry in $entries) {
  $module = [string]$entry.module
  $pattern = '(?<![A-Za-z0-9_.])' + [regex]::Escape($module) + '(?![A-Za-z0-9_.])'
  $roots = @($snapshot | Where-Object {
    $_.ExecutablePath -ieq $expectedPython -and $_.CommandLine -match $pattern
  })
  foreach ($candidate in $roots) {
    Stop-DepoProcessTree ([int]$candidate.ProcessId) $expectedPython $module
  }
  $pidPath = Join-Path $stateDir ($entry.id + '.pid')
  if (Test-Path -LiteralPath $pidPath) {
    $trackedPid = [int](Get-Content -LiteralPath $pidPath)
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $trackedPid" -ErrorAction Stop
    if ($current) {
      # An unrelated reused PID must not be killed or silently untracked.
      Stop-DepoProcessTree $trackedPid $expectedPython $module
    }
    Remove-Item -LiteralPath $pidPath -Force
  }
}
if ($StopPostgres) {
  . (Join-Path $PSScriptRoot 'runtime-config.ps1')
  Import-DepoEnvironment -Root $root -EnvFile $EnvFile
  if ($env:DEPO_POSTGRES_MODE -eq 'service') {
    if (-not $env:DEPO_POSTGRES_SERVICE_NAME) { throw 'Specify DEPO_POSTGRES_SERVICE_NAME before stopping PostgreSQL.' }
    Stop-Service -Name $env:DEPO_POSTGRES_SERVICE_NAME -ErrorAction Stop
  } elseif ($env:DEPO_POSTGRES_MODE -eq 'portable') {
    if (-not $PostgresBinDir) { $PostgresBinDir = $env:DEPO_POSTGRES_BIN_DIR }
    if (-not $PostgresDataDir) { $PostgresDataDir = $env:DEPO_POSTGRES_DATA_DIR }
    if (-not $PostgresBinDir -or -not $PostgresDataDir) { throw 'Explicit PostgreSQL binary/data paths are required.' }
    & (Join-Path $PostgresBinDir 'pg_ctl.exe') stop -D $PostgresDataDir -m fast -w -t 60
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL stop failed.' }
  } else {
    throw 'Refusing to stop an external or unspecified PostgreSQL instance.'
  }
}
Write-Host "DEPO services stopped."

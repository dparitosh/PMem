param(
  [switch]$StopPostgres,
  [string]$PostgresBinDir = "D:\codevita\postgresql-16\pgsql\bin",
  [string]$PostgresDataDir = "D:\codevita\postgresql-16\data"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$expectedPython = (Join-Path $root "backend\.dt_venv\Scripts\python.exe").ToLowerInvariant()
$stateDir = Join-Path $root "logs\windows-services"
$manifestPath = Join-Path $root "infra\deployment\services.json"
$modules = @()
if (Test-Path $manifestPath) {
  $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
  $modules = @($manifest.services | ForEach-Object { [string]$_.module }) + @($manifest.workers | ForEach-Object { [string]$_.module })
}

# PID files alone are not sufficient after a crash or a shell restart: a
# Uvicorn listener can outlive its recorded launcher PID. Discover only this
# repository's Python processes and only the modules declared in the manifest.
$serviceProcesses = @()
if ($modules.Count -gt 0) {
  foreach ($candidate in Get-CimInstance Win32_Process -ErrorAction SilentlyContinue) {
    if (-not $candidate.ExecutablePath -or $candidate.ExecutablePath.ToLowerInvariant() -ne $expectedPython -or -not $candidate.CommandLine) { continue }
    foreach ($module in $modules) {
      if ($module -and $candidate.CommandLine -match [regex]::Escape($module)) {
        $serviceProcesses += $candidate
        break
      }
    }
  }
}
# Windows virtual-environment launchers can remain as a parent process while
# the actual listener runs under the base Python executable. Include only
# descendants of the already verified PMem launcher; never select arbitrary
# system-Python processes by their module name alone.
$knownProcessIds = [System.Collections.Generic.HashSet[int]]::new()
foreach ($service in $serviceProcesses) { [void]$knownProcessIds.Add([int]$service.ProcessId) }
$processSnapshot = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$foundDescendant = $true
while ($foundDescendant) {
  $foundDescendant = $false
  foreach ($candidate in $processSnapshot) {
    if ($candidate.ParentProcessId -and $knownProcessIds.Contains([int]$candidate.ParentProcessId) -and $knownProcessIds.Add([int]$candidate.ProcessId)) {
      $serviceProcesses += $candidate
      $foundDescendant = $true
    }
  }
}
# Stop children before their launcher so active port listeners cannot survive
# a graceful-looking stop after a virtual-environment process exits.
foreach ($service in ($serviceProcesses | Sort-Object { $_.ProcessId } -Descending)) {
  Stop-Process -Id $service.ProcessId -Force -ErrorAction SilentlyContinue
}
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

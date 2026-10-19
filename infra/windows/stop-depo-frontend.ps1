$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'process-control.ps1')
$expectedPython = Join-Path $root 'backend\.dt_venv\Scripts\python.exe'
$pidFile = Join-Path $root 'logs\windows-services\frontend.pid'

function Test-ProjectFrontend($Process) {
  return [bool]($Process -and $Process.ExecutablePath -ieq $expectedPython -and
    $Process.CommandLine -match '(?<![A-Za-z0-9_.])(?:http\.server|backend\.depo_platform\.frontend_server)(?![A-Za-z0-9_.])' -and
    $Process.CommandLine -match 'frontend[\\/]dist')
}

# Inspect tracked and recoverable launchers from the same snapshot. A second
# CIM query can return different visibility or race with process termination.
$snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
$launchers = @($snapshot | Where-Object { Test-ProjectFrontend $_ })
if (Test-Path -LiteralPath $pidFile) {
  $recordedPid = 0
  if (-not [int]::TryParse(([string](Get-Content -LiteralPath $pidFile -Raw)).Trim(), [ref]$recordedPid) -or $recordedPid -le 0) {
    throw 'Invalid frontend PID file. Tracking retained for inspection.'
  }
  $recorded = $snapshot | Where-Object { $_.ProcessId -eq $recordedPid } | Select-Object -First 1
  if ($recorded -and -not (Test-ProjectFrontend $recorded)) {
    throw "Recorded frontend PID $recordedPid has executable '$($recorded.ExecutablePath)', expected '$expectedPython', or its frontend command does not match. Tracking retained; no unrelated process was stopped."
  }
}
foreach ($launcher in $launchers) {
  $module = if ($launcher.CommandLine -match 'backend\.depo_platform\.frontend_server') { 'backend.depo_platform.frontend_server' } else { 'http.server' }
  Stop-DepoProcessTree $launcher.ProcessId $expectedPython $module
}
if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
Write-Host 'DEPO frontend processes stopped. Untracked base-Python processes are not controlled.'

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'process-control.ps1')
$expectedPython = Join-Path $root 'backend\.dt_venv\Scripts\python.exe'
$pidFile = Join-Path $root 'logs\windows-services\frontend.pid'
# Recover a missing launcher PID file only from this repository's verified runtime.
$launchers = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
  $_.ExecutablePath -ieq $expectedPython -and $_.CommandLine -match 'http\.server' -and $_.CommandLine -match 'frontend[\\/]dist'
})
if (Test-Path -LiteralPath $pidFile) {
  $recordedPid = [int](Get-Content -LiteralPath $pidFile)
  $recorded = Get-CimInstance Win32_Process -Filter "ProcessId = $recordedPid" -ErrorAction Stop
  if ($recorded -and $recorded.ProcessId -notin @($launchers.ProcessId)) {
    throw 'Recorded frontend PID is not the expected project frontend. Tracking retained; inspect the process before retrying.'
  }
}
foreach ($launcher in $launchers) { Stop-DepoProcessTree $launcher.ProcessId $expectedPython 'http.server' }
if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
Write-Host 'DEPO frontend processes stopped. Untracked base-Python processes are not controlled.'

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedPython = (Join-Path $root 'backend\.dt_venv\Scripts\python.exe').ToLowerInvariant()
$pidFile = Join-Path $root 'logs\windows-services\frontend.pid'

if (-not (Test-Path -LiteralPath $pidFile)) {
  Write-Host 'DEPO frontend is not recorded as running.'
  return
}

$recordedPid = [int](Get-Content -LiteralPath $pidFile)
$process = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
$details = if ($process) { Get-CimInstance Win32_Process -Filter "ProcessId = $recordedPid" -ErrorAction SilentlyContinue } else { $null }
if ($details -and $details.ExecutablePath -and $details.ExecutablePath.ToLowerInvariant() -eq $expectedPython -and
    $details.CommandLine -match 'http\.server' -and $details.CommandLine -match 'frontend[\\/]dist') {
  Stop-Process -Id $recordedPid -Force
}
Remove-Item -LiteralPath $pidFile -Force
Write-Host 'DEPO frontend stopped.'

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
if ($process -and $process.Path -and $process.Path.ToLowerInvariant() -eq $expectedPython) {
  Stop-Process -Id $recordedPid -Force
}
Remove-Item -LiteralPath $pidFile -Force
Write-Host 'DEPO frontend stopped.'

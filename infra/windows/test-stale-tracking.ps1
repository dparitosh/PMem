$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'process-control.ps1')
$allowed=@('C:\PMem\backend\.dt_venv\Scripts\python.exe')
$module='backend.graph_service'
if ((Get-DepoTrackedProcessState $null $allowed $module) -ne 'exited') {throw 'Exited case failed'}
$proc=[pscustomobject]@{ExecutablePath=$allowed[0];CommandLine='python -m backend.graph_service'}
if ((Get-DepoTrackedProcessState $proc $allowed $module) -ne 'owned') {throw 'Owned case failed'}
$proc.CommandLine='python -m unrelated.service'
if ((Get-DepoTrackedProcessState $proc $allowed $module) -ne 'reused') {throw 'Reused case failed'}
$proc.CommandLine='python -m backend.graph_service';$proc.ExecutablePath='C:\Other\python.exe'
$rejected=$false
try {Get-DepoTrackedProcessState $proc $allowed $module} catch {$rejected=$true}
if (-not $rejected) {throw 'Unapproved runtime accepted'}
$proc.ExecutablePath=$null
$rejected=$false
try {Get-DepoTrackedProcessState $proc $allowed $module} catch {$rejected=$true}
if (-not $rejected) {throw 'Unreadable identity accepted'}
Write-Host 'PASS: five tracked-process identity cases'

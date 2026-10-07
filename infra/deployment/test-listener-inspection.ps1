$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../windows/process-control.ps1')
$fixture = @{ listeners=@(); failure=$false }
function Get-CimInstance {
  param($ClassName, $Filter, $ErrorAction)
  if ($Filter) {
    # A reused PID has a newer creation time and must not be terminated.
    return [pscustomobject]@{ProcessId=1234; CreationDate=[datetime]'2026-02-01'}
  }
  [pscustomobject]@{ProcessId=1234; ParentProcessId=1; CreationDate=[datetime]'2026-01-01'; ExecutablePath='fixture-python'; CommandLine='-m uvicorn backend.qif.app:app'}
  [pscustomobject]@{ProcessId=5678; ParentProcessId=1234; CreationDate=[datetime]'2026-01-02'; ExecutablePath='child-python'; CommandLine='child'}
}
function Get-NetTCPConnection {
  param($State, $ErrorAction)
  if ($ErrorAction -ne 'Stop') { throw 'Listener inspection must preserve errors' }
  if ($fixture.failure) { throw 'CIM access denied' }
  $fixture.listeners
}
function Assert-Listener([bool]$Expected) {
  $actual = Test-DepoListener 1234 'fixture-python' 'backend.qif.app:app' 8010 '10.0.2.16'
  if ($actual -ne $Expected) { throw "Expected listener result $Expected, got $actual" }
}
Assert-Listener $false
$fixture.listeners = @([pscustomobject]@{LocalPort=8010; LocalAddress='10.0.2.16'; OwningProcess=5678})
Assert-Listener $true
$fixture.listeners[0].OwningProcess = 9999
Assert-Listener $false
$fixture.listeners[0].OwningProcess = 5678
$fixture.listeners[0].LocalAddress = '127.0.0.1'
Assert-Listener $false
$fixture.listeners[0].LocalAddress = '10.0.2.16'
$fixture.listeners[0].LocalPort = 8011
Assert-Listener $false
$fixture.failure = $true
$caught = $false
try { Assert-Listener $false } catch {
  if ($_.Exception.Message -notlike '*Windows listener inspection failed for port 8010: CIM access denied*') { throw }
  $caught = $true
}
if (-not $caught) { throw 'CIM failure was hidden' }
$fixture.failure = $false
$fixture.listeners = @()
function Stop-Process { throw 'Reused PID was terminated' }
Stop-DepoProcessTree 1234 'fixture-python' 'backend.qif.app:app'
Write-Host 'PASS: absent listener, descendant owner, unrelated owner, binding/port mismatch and CIM failure.'
Write-Host 'PASS: shutdown does not terminate reused PIDs.'

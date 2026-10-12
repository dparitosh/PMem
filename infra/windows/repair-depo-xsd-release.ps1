<# .SYNOPSIS Repair mismatched XSD converter files from an extracted matching release. #>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ReleaseRoot,
  [Parameter(Mandatory=$true)][string]$ApplicationRoot
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$target = (Resolve-Path -LiteralPath $ApplicationRoot).Path
if ($source -ieq $target) { throw 'ReleaseRoot must be a separate extracted release directory.' }
$python = Join-Path $target 'backend\.dt_venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Application Python runtime is missing.' }
$files = @('backend/Services/xsd_semantics.py', 'backend/Services/owl_xsd_engine.py',
  'backend/Services/owl_generation_service.py', 'backend/depo_platform/release_code_check.py',
  'infra/windows/start-depo-services.ps1', 'infra/windows/stop-depo-services.ps1',
  'infra/windows/process-control.ps1')
foreach ($name in $files) {
  if (-not (Test-Path -LiteralPath (Join-Path $source $name) -PathType Leaf)) { throw "Release is missing $name; use a complete matching release." }
}
& $python -B (Join-Path $source 'backend/depo_platform/release_code_check.py') --root $source
if ($LASTEXITCODE -ne 0) { throw 'Source release validation failed; application files were not changed.' }
# Never copy over a running converter, even if PID tracking was lost.
$expectedPython = [IO.Path]::GetFullPath($python)
$running = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
  $_.ExecutablePath -ieq $expectedPython -and $_.CommandLine -match 'backend\.'
})
if ($running.Count) { throw 'Stop DEPO backend services first, then rerun repair. No files were changed.' }
$backup = Join-Path $target ('logs\release-repair\' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$changed = @()
try {
  foreach ($name in $files) {
    $destination = [IO.Path]::GetFullPath((Join-Path $target $name))
    if (-not $destination.StartsWith($target.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Repair path escaped application root.' }
    $saved = Join-Path $backup $name
    New-Item -ItemType Directory -Path (Split-Path $saved -Parent) -Force | Out-Null
    $existed = Test-Path -LiteralPath $destination -PathType Leaf
    if ($existed) { Copy-Item -LiteralPath $destination -Destination $saved }
    $changed += @{ Destination=$destination; Saved=$saved; Existed=$existed }
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $destination -Force
    if ((Get-FileHash -LiteralPath $destination).Hash -ne (Get-FileHash -LiteralPath (Join-Path $source $name)).Hash) { throw "Copied file verification failed: $name" }
  }
  & $python -B (Join-Path $target 'backend/depo_platform/release_code_check.py') --root $target
  if ($LASTEXITCODE -ne 0) { throw 'Repaired converter validation failed.' }
} catch {
  foreach ($item in $changed) {
    if ($item.Existed) { Copy-Item -LiteralPath $item.Saved -Destination $item.Destination -Force }
    else { Remove-Item -LiteralPath $item.Destination -Force }
  }
  throw
}
Write-Host "XSD converter and launcher repair verified. Backup: $backup"
Write-Host 'Restart backend services. This repair does not upgrade unrelated services or dependencies.'

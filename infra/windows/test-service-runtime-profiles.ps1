# Offline runtime-path validation; no installs, processes or databases.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'service-runtimes.ps1')
$manifest = Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
foreach ($entry in (@($manifest.services) + @($manifest.workers))) {
  $shared = Get-DepoServicePython -Root $root -ServiceId $entry.id -Mode shared
  $isolated = Get-DepoServicePython -Root $root -ServiceId $entry.id -Mode isolated
  if ($shared -ne (Join-Path $root 'backend/.dt_venv/Scripts/python.exe')) { throw 'Shared runtime path changed.' }
  if ($isolated -ne (Join-Path $root ("backend/.dt_venv-{0}/Scripts/python.exe" -f $entry.id))) { throw 'Isolated runtime path is incorrect.' }
  if (-not (Test-Path -LiteralPath (Join-Path $root ("backend/dependency-profiles/{0}.txt" -f $entry.id)))) { throw 'Service lock is missing.' }
}
foreach ($invalid in @('../ontology','unknown')) {
  $rejected = $false
  try { Get-DepoServicePython -Root $root -ServiceId $invalid -Mode isolated | Out-Null } catch { $rejected = $true }
  if (-not $rejected) { throw 'Unsafe runtime identity was accepted.' }
}
Write-Host 'PASS: 13 service/worker paths, shared compatibility, profile presence and unknown identity rejection.'

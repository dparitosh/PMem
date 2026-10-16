# One runtime selection contract for installation, launch and shutdown.
function Get-DepoServicePython([string]$Root, [string]$ServiceId, [string]$Mode = $env:DEPO_SERVICE_RUNTIME_MODE) {
  if ($ServiceId -notmatch '^[a-z][a-z0-9-]*$') { throw 'Invalid DEPO service runtime identity.' }
  if (-not $Mode) { $Mode = 'shared' }
  if ($Mode -notin @('shared','isolated')) { throw 'DEPO_SERVICE_RUNTIME_MODE must be shared or isolated.' }
  $manifest = Get-Content -LiteralPath (Join-Path $Root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
  if ($ServiceId -notin @(@($manifest.services) + @($manifest.workers) | ForEach-Object { $_.id })) { throw 'Unknown DEPO service runtime.' }
  $folder = if ($Mode -eq 'isolated') { '.dt_venv-' + $ServiceId } else { '.dt_venv' }
  return Join-Path $Root "backend/$folder/Scripts/python.exe"
}

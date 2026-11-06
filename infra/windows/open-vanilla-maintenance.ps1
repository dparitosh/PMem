param([string]$EnvFile = '.env.local')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'native-install-command.ps1')
Invoke-DepoLoggedAction -Root $root -Name 'vanilla-maintenance' -AuditEnvFile $EnvFile -Action {
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'service-runtimes.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$stateDirectory = Join-Path $root 'logs/windows-services'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
$modeFile = Join-Path $stateDirectory 'vanilla-maintenance.lock'
# Share-none prevents two maintenance launchers and remains held for this host.
$modeHandle = [IO.File]::Open($modeFile, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
# Uses the existing process-identity checks and graceful stop. Never stops DBs.
$previousMode = $env:DEPO_VANILLA_MAINTENANCE
try {
  & (Join-Path $PSScriptRoot 'stop-depo-services.ps1') -EnvFile $EnvFile
  $python = Get-DepoServicePython -Root $root -ServiceId 'ontology'
  $env:DEPO_VANILLA_MAINTENANCE = 'true'
  $bind = if ($env:DEPO_LOCAL_SERVICE_HOST) { $env:DEPO_LOCAL_SERVICE_HOST } elseif ($env:DEPO_SERVICE_HOST) { $env:DEPO_SERVICE_HOST } else { '127.0.0.1' }
  Write-Host 'Isolated reset maintenance. Open Admin > Maintenance, preview Reset DEPO to vanilla state and confirm there.'
  Write-Host 'No data is deleted by this launcher. After reset, press Ctrl+C here and run manage-depo.ps1 -Action Start.'
  Push-Location $root
  try { Invoke-DepoNativeCommand -Executable $python -NativeArguments @('-m', 'uvicorn', 'backend.ontology_service.app:app', '--host', $bind, '--port', '8011', '--no-proxy-headers') -AllowFailure }
  finally { Pop-Location }
  if ($LASTEXITCODE -notin @(0,130)) { throw "Maintenance host exited with code $LASTEXITCODE" }
} finally {
  $env:DEPO_VANILLA_MAINTENANCE = $previousMode
  $modeHandle.Dispose()
  Remove-Item -LiteralPath $modeFile -ErrorAction SilentlyContinue
}
}

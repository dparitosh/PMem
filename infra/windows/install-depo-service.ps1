<# .SYNOPSIS Installs reviewed per-service dependencies without migrations or startup. #>
[CmdletBinding()]
param(
  [string]$ServiceId = 'all',
  [string]$EnvFile = '.env.local',
  [string]$Python = 'py',
  [switch]$EnableOcr,
  [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'service-runtimes.ps1')
. (Join-Path $PSScriptRoot 'native-install-command.ps1')
. (Join-Path $PSScriptRoot 'deployment-process-guards.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$manifest = Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
$entries = @($manifest.services) + @($manifest.workers)
if ($ServiceId -ne 'all') {
  $entries = @($entries | Where-Object { $_.id -eq $ServiceId })
  if (-not $entries.Count) { throw 'Unknown service ID; use an ID from infra/deployment/services.json.' }
}
$profiles = Join-Path $root 'backend/dependency-profiles'
foreach ($entry in $entries) {
  $lock = Join-Path $profiles ($entry.id + '.txt')
  if (-not (Test-Path -LiteralPath $lock -PathType Leaf)) { throw "Missing reviewed service lock: $($entry.id)" }
  $invalid = Get-Content -LiteralPath $lock | Where-Object { $_ -and -not $_.StartsWith('#') -and $_ -notmatch '^[a-z0-9][a-z0-9.-]*==[^ ]+ --hash=sha256:[a-f0-9]{64}$' }
  if ($invalid) { throw "Invalid hash-pinned service lock: $($entry.id)" }
}
if ($CheckOnly) { Write-Host "Validated $($entries.Count) service lock files; no runtimes installed."; return }
$runtimeVersion = & $Python -c 'import sys; print(sys.version_info.major, sys.version_info.minor, 64 if sys.maxsize > 2**32 else 32)'
if ($LASTEXITCODE -ne 0 -or "$runtimeVersion".Trim() -ne '3 12 64') { throw 'Service runtimes require 64-bit CPython 3.12.' }
# Validate the entire selection before changing the first runtime.
foreach ($entry in $entries) {
  Assert-DepoRuntimeIdle -Python (Get-DepoServicePython -Root $root -ServiceId $entry.id -Mode isolated)
}
$logs = Join-Path $root 'logs/installation'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
foreach ($entry in $entries) {
  $servicePython = Get-DepoServicePython -Root $root -ServiceId $entry.id -Mode isolated
  Assert-DepoRuntimeIdle -Python $servicePython
  $venv = Split-Path (Split-Path $servicePython -Parent) -Parent
  if (-not (Test-Path -LiteralPath $servicePython)) {
    & $Python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Service runtime creation failed: $($entry.id)" }
  }
  $runtimeVersion = & $servicePython -c 'import sys; print(sys.version_info.major, sys.version_info.minor, 64 if sys.maxsize > 2**32 else 32)'
  if ($LASTEXITCODE -ne 0 -or "$runtimeVersion".Trim() -ne '3 12 64') { throw "Incompatible existing service runtime: $($entry.id). Preserve configuration and replace only the reviewed virtual environment." }
  $arguments = @('-m','pip','install','--disable-pip-version-check','--require-hashes','-r',(Join-Path $profiles ($entry.id + '.txt')))
  if ($EnableOcr -and $entry.id -eq 'ingestion') { $arguments += @('-r',(Join-Path $profiles 'ocr.txt')) }
  $log = Join-Path $logs ($entry.id + '-' + [guid]::NewGuid().ToString('N') + '.log')
  $code = Invoke-DepoInstallCommand -Executable $servicePython -NativeArguments $arguments -LogPath $log
  if ($code -ne 0) { throw "Service dependency installation failed: $($entry.id). Inspect $log" }
  & $servicePython -m pip check
  if ($LASTEXITCODE -ne 0) { throw "Service dependency compatibility check failed: $($entry.id)" }
  Push-Location $root
  try {
    & $servicePython -m backend.depo_platform.service_smoke --service $entry.id
    if ($LASTEXITCODE -ne 0) { throw "Service import/OpenAPI check failed: $($entry.id)" }
  } finally { Pop-Location }
}
Write-Host 'Selected service runtimes installed and smoke checked. No database changes or service startup performed.'

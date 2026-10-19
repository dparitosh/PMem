param(
  [string]$EnvFile = '.env.local',
  [string]$Python = "py",
  [switch]$SkipFrontend,
  [switch]$Development,
  [switch]$EnableOcr,
  [switch]$CheckPrerequisites,
  [switch]$ForceReinstall
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPath = Join-Path $root "backend\.dt_venv"
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
# Check prerequisites before creating directories or installing dependencies.
$pythonToCheck = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { $Python }
if (-not (Get-Command $pythonToCheck -ErrorAction SilentlyContinue)) {
  throw 'Python was not found. Install 64-bit CPython 3.12 and pass -Python <executable> if needed.'
}
$pythonVersion = & $pythonToCheck -c 'import sys; print(sys.version.split()[0])'
if ($LASTEXITCODE -ne 0 -or ([version]$pythonVersion).Major -ne 3 -or ([version]$pythonVersion).Minor -ne 12) {
  throw 'The customer release requires CPython 3.12.x. Replace an incompatible backend/.dt_venv before installing.'
}
$pythonBits = & $pythonToCheck -c 'import sys; print(64 if sys.maxsize > 2**32 else 32)'
if ($LASTEXITCODE -ne 0 -or "$pythonBits".Trim() -ne '64') { throw 'The customer release requires 64-bit CPython 3.12. No dependencies were installed.' }
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
if (-not $SkipFrontend) {
  $nodeSettings=Read-DepoEnvironment -Root $root -EnvFile $EnvFile
  $nodeRuntime=Get-DepoNodeRuntime -Root $root -NodeJsDir $nodeSettings['DEPO_NODEJS_DIR']
  $env:Path=$nodeRuntime.Directory+';'+$env:Path
  $nodeVersion=$nodeRuntime.Version
  $npmVersion = & npm.cmd --version
  if ($LASTEXITCODE -ne 0 -or [version]$npmVersion -lt [version]'10.2.0') { throw 'npm 10.2 or newer is required.' }
  if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend/package-lock.json'))) { throw 'Missing frontend/package-lock.json.' }
}
$productionLock = Join-Path $root 'backend\requirements-lock.txt'
$ocrLock = Join-Path $root 'backend\requirements-ocr-lock.txt'
if (-not $Development) {
  $selectedLocks = @($productionLock)
  if ($EnableOcr) { $selectedLocks += $ocrLock }
  foreach ($lock in $selectedLocks) {
    if (-not (Test-Path -LiteralPath $lock -PathType Leaf)) { throw "Missing dependency lock: $lock" }
    $unhashed = Get-Content -LiteralPath $lock | Where-Object { $_ -and -not $_.StartsWith('#') -and $_ -notmatch ' --hash=sha256:[0-9a-f]{64}$' }
    if ($unhashed) { throw "Every production dependency must be exact-version and SHA-256 pinned in $lock" }
  }
}
. (Join-Path $PSScriptRoot 'deployment-process-guards.ps1')
Assert-DepoWindowsManagementAccess
if ($CheckPrerequisites) {
  Write-Host 'Installation prerequisites passed. No dependencies were installed.'
  return
}
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'deployment-process-guards.ps1')
# Import the selected deployment configuration before any service imports.
# Python's legacy .env lookup does not load root .env.local automatically.
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$isolatedServices = $env:DEPO_SERVICE_RUNTIME_MODE -eq 'isolated'
if ($isolatedServices -and $Development) { throw 'Isolated service deployment uses reviewed production locks; omit -Development.' }
if ($isolatedServices) { $productionLock = Join-Path $root 'backend/dependency-profiles/platform-tools.txt' }
if (-not (Test-Path $venvPython)) {
  & $Python -m venv $VenvPath
  if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed." }
}
$requirements = if ($Development) { Join-Path $root 'backend/requirements-dev.txt' } else { $productionLock }
Assert-DepoRuntimeIdle -Python $venvPython
. (Join-Path $PSScriptRoot 'native-install-command.ps1')
$installLogDir = Join-Path $root 'logs\installation'
New-Item -ItemType Directory -Path $installLogDir -Force | Out-Null
$pipLog = Join-Path $installLogDir ('pip-install-' + [guid]::NewGuid().ToString('N') + '.log')
$pipArguments = @('-m', 'pip', 'install', '--disable-pip-version-check')
if (-not $Development) { $pipArguments += '--require-hashes' }
$pipArguments += @('-r', $requirements)
if ($EnableOcr -and -not $Development -and -not $isolatedServices) { $pipArguments += @('-r', $ocrLock) }
Write-Host "Installing backend dependencies. Output log: $pipLog"
. (Join-Path $PSScriptRoot 'install-checkpoints.ps1')
$dependencyInputs = @($requirements)
if ($EnableOcr -and -not $Development -and -not $isolatedServices) { $dependencyInputs += $ocrLock }
$runtimeIdentity = & $venvPython -c 'import sys; print(sys.executable, sys.version)'
$dependencyFingerprint = Get-DepoInstallFingerprint -Files $dependencyInputs -Values @($runtimeIdentity, [string]$Development, [string]$EnableOcr)
Invoke-DepoDependencyStage -Root $root -Name 'backend' -Fingerprint $dependencyFingerprint -Force:($ForceReinstall -or $Development) -Action {
  $pipExitCode = Invoke-DepoInstallCommand -Executable $venvPython -NativeArguments $pipArguments -LogPath $pipLog
  if ($pipExitCode -ne 0) { throw "Backend dependency installation failed. Inspect $pipLog; rerun the same installer after correcting the error." }
} -Probe {
  & $venvPython -m pip check | Out-Host
  if ($LASTEXITCODE -ne 0) { return $false }
  $inventory = & $venvPython -m pip freeze --all
  if ($LASTEXITCODE -ne 0) { return $false }
  return (Get-DepoInstallFingerprint -Files @() -Values @($inventory))
}
if ($isolatedServices) {
  & (Join-Path $PSScriptRoot 'install-depo-service.ps1') -ServiceId all -EnvFile $EnvFile -Python $venvPython -EnableOcr:$EnableOcr -ForceReinstall:$ForceReinstall
} else {
Push-Location $root
try {
  # Do not use ``python -c`` here. Windows PowerShell removes embedded double
  # quotes while constructing native-process arguments, which turns
  # ``print("Agentic...")`` into invalid Python. Standard input preserves the
  # smoke-check source exactly on Windows PowerShell and PowerShell 7.
  @'
import importlib
import json
from pathlib import Path

manifest = json.loads(Path("infra/deployment/services.json").read_text(encoding="utf-8"))
for item in manifest["services"]:
    module_name, attribute = item["module"].split(":", 1)
    app = getattr(importlib.import_module(module_name), attribute)
    assert app.openapi()["paths"], f"{item['id']} generated an empty OpenAPI contract"
    print(f"PASS: {item['id']} import and OpenAPI")
for item in manifest.get("workers", []):
    importlib.import_module(item["module"])
    print(f"PASS: {item['id']} worker import")
'@ | & $venvPython -
  if ($LASTEXITCODE -ne 0) { throw 'Service installation import/OpenAPI smoke check failed.' }
} finally { Pop-Location }
}
if (-not $SkipFrontend) {
  $frontend = Join-Path $root "frontend"
  Push-Location $frontend
  try {
    if (-not (Test-Path (Join-Path $frontend "package-lock.json"))) { throw "Missing frontend/package-lock.json; restore the release lockfile before installation." }
    $frontendFingerprint = Get-DepoInstallFingerprint -Files @((Join-Path $frontend 'package-lock.json'), (Join-Path $frontend 'package.json')) -Values @($nodeVersion, $npmVersion)
    Invoke-DepoDependencyStage -Root $root -Name 'frontend' -Fingerprint $frontendFingerprint -Force:$ForceReinstall -Action {
    # Preserve the exact reviewed lockfile. An npm install fallback may select
    # a different graph after a transient Windows EBUSY and rewrite the lock.
    for ($attempt = 1; $attempt -le 3; $attempt++) {
      npm.cmd ci --no-audit --no-fund
      if ($LASTEXITCODE -eq 0) { break }
      if ($attempt -lt 3) {
        Write-Warning "npm ci attempt $attempt failed. Close Vite/Node processes that may hold frontend/node_modules; retrying the locked install."
        Start-Sleep -Seconds 2
      }
    }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend locked dependency installation failed after three attempts. Close Vite/Node processes, then rerun install-depo.ps1.' }
    } -Probe {
      if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules/.bin/vite.cmd'))) { return $false }
      & npm.cmd ls --depth=0 --offline *> $null
      return ($LASTEXITCODE -eq 0)
    }
    & (Join-Path $PSScriptRoot 'build-depo-frontend.ps1') -EnvFile $EnvFile
  } finally { Pop-Location }
}
Write-Host 'Backend installed in backend/.dt_venv.'
if (-not $SkipFrontend) { Write-Host 'Frontend installed and built in frontend/dist. Rebuild after changing browser configuration.' }
Write-Host 'Configuration and lifecycle are managed through the repository-root commands documented in INSTALLATION.md.'

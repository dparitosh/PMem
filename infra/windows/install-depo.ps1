param(
  [string]$Python = "py",
  [switch]$SkipFrontend,
  [switch]$Development,
  [switch]$CheckPrerequisites
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
if (-not $SkipFrontend) {
  foreach ($command in @('node', 'npm.cmd')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Missing $command. Install Node.js 24+ and npm 10.2+." }
  }
  $nodeVersion = & node --version
  if ($LASTEXITCODE -ne 0 -or [version]($nodeVersion.TrimStart('v')) -lt [version]'24.0.0') { throw 'Node.js 24 or newer is required.' }
  $npmVersion = & npm.cmd --version
  if ($LASTEXITCODE -ne 0 -or [version]$npmVersion -lt [version]'10.2.0') { throw 'npm 10.2 or newer is required.' }
  if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend/package-lock.json'))) { throw 'Missing frontend/package-lock.json.' }
}
$productionLock = Join-Path $root 'backend\requirements-lock.txt'
if (-not $Development) {
  if (-not (Test-Path -LiteralPath $productionLock -PathType Leaf)) { throw 'Missing backend/requirements-lock.txt.' }
  $unhashed = Get-Content -LiteralPath $productionLock | Where-Object { $_ -and -not $_.StartsWith('#') -and $_ -notmatch ' --hash=sha256:[0-9a-f]{64}$' }
  if ($unhashed) { throw 'Every production dependency must be exact-version and SHA-256 pinned in backend/requirements-lock.txt.' }
}
if ($CheckPrerequisites) {
  Write-Host 'Installation prerequisites passed. No dependencies were installed.'
  return
}
if (-not (Test-Path $venvPython)) {
  & $Python -m venv $VenvPath
  if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed." }
}
$requirements = if ($Development) { Join-Path $root 'backend/requirements-dev.txt' } else { $productionLock }
if ($Development) { & $venvPython -m pip install -r $requirements }
else { & $venvPython -m pip install --require-hashes -r $requirements }
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
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
if (-not $SkipFrontend) {
  $frontend = Join-Path $root "frontend"
  Push-Location $frontend
  try {
    if (Test-Path (Join-Path $frontend "package-lock.json")) { npm.cmd ci }
    else { throw "Missing frontend/package-lock.json; restore the release lockfile before installation." }
    if ($LASTEXITCODE -ne 0) {
      # npm ci removes node_modules first. Windows returns EBUSY when a stale
      # Vite/Node process still has a package directory open. Retry using the
      # existing tree so a transient lock does not make installation fail.
      Write-Warning 'npm ci could not replace frontend/node_modules. Retrying with npm install; close running Vite/Node processes if this also fails.'
      npm.cmd install --no-audit --no-fund
    }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. Close running node.exe/Vite processes and rerun install-depo.ps1.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
  } finally { Pop-Location }
}
Write-Host 'Backend installed in backend/.dt_venv.'
if (-not $SkipFrontend) { Write-Host 'Frontend installed and built in frontend/dist. Rebuild after changing browser configuration.' }
Write-Host 'Configuration and lifecycle are managed through the repository-root commands documented in INSTALLATION.md.'

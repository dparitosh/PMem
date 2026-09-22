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
  throw 'Python was not found. Install Python 3.11 or newer and pass -Python <executable> if needed.'
}
$pythonVersion = & $pythonToCheck -c 'import sys; print(sys.version.split()[0])'
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]'3.11.0') {
  throw 'Python 3.11 or newer is required. Replace an incompatible backend/.dt_venv before installing.'
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
if ($CheckPrerequisites) {
  Write-Host 'Installation prerequisites passed. No dependencies were installed.'
  return
}
if (-not (Test-Path $venvPython)) {
  & $Python -m venv $VenvPath
  if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed." }
}
$requirements = if ($Development) { 'backend/requirements-dev.txt' } else { 'backend/requirements.txt' }
& $venvPython -m pip install -r (Join-Path $root $requirements)
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
if (-not $SkipFrontend) {
  $frontend = Join-Path $root "frontend"
  Push-Location $frontend
  try {
    if (Test-Path (Join-Path $frontend "package-lock.json")) { npm.cmd ci }
    else { throw "Missing frontend/package-lock.json; restore the release lockfile before installation." }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
  } finally { Pop-Location }
}
Write-Host 'Backend installed in backend/.dt_venv.'
if (-not $SkipFrontend) { Write-Host 'Frontend installed and built in frontend/dist. Rebuild after changing browser configuration.' }
Write-Host 'Configure root .env.local, then use infra/deployment/invoke-depo-lifecycle.ps1. See infra/deployment/README.md for the complete sequence.'

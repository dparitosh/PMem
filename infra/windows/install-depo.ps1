param(
  [string]$Python = "py",
  [string]$VenvPath = "",
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $VenvPath) { $VenvPath = Join-Path $root "backend\.dt_venv" }
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  & $Python -m venv $VenvPath
  if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed." }
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $venvPython -m pip install -r (Join-Path $root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
if (-not $SkipFrontend) {
  $frontend = Join-Path $root "frontend"
  Push-Location $frontend
  try {
    if (Test-Path (Join-Path $frontend "package-lock.json")) { npm.cmd ci }
    else { throw "Missing frontend/package-lock.json; restore the release lockfile before installation." }
    $code = $LASTEXITCODE
  } finally { Pop-Location }
  if ($code -ne 0) { throw "Frontend dependency installation failed." }
}
Write-Host "DEPO runtime dependencies installed. Configure .env.local, then run infra\deployment\invoke-depo-lifecycle.ps1 -Action Start."

param([string]$EnvFile = '.env.local', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$python = Join-Path $root 'backend/.dt_venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install backend dependencies before initializing or checking application tables.' }
Push-Location $root
try {
  if ($CheckOnly) { & $python -m backend.depo_platform.database_setup --check-only }
  else { & $python -m backend.depo_platform.database_setup }
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL schema migration/verification failed; no services should be started.' }
} finally { Pop-Location }

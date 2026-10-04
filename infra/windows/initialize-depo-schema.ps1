param([string]$EnvFile = '.env.local', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$databaseSettings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $databaseSettings['DEPO_DATABASE_URL'] -and -not $databaseSettings['DATABASE_URL']) {
  throw 'The selected environment file must configure DEPO_DATABASE_URL (or DATABASE_URL); inherited shell connection settings are not used for this diagnostic.'
}
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$python = Join-Path $root 'backend/.dt_venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install backend dependencies before initializing or checking application tables.' }
Push-Location $root
try {
  $arguments = @('-m', 'backend.depo_platform.database_setup')
  if ($CheckOnly) { $arguments += '--check-only' }
  & $python @arguments
  $databaseExitCode = $LASTEXITCODE
  if ($databaseExitCode -ne 0) {
    throw "PostgreSQL schema migration/verification failed with exit code $databaseExitCode. Use the structured error immediately above to correct connectivity, authentication, privileges, or schema compatibility; no services were started."
  }
} finally { Pop-Location }

<#
.SYNOPSIS
Tests the application PostgreSQL URL without creating or checking tables.
.DESCRIPTION
Loads the root environment file and uses the same psycopg driver and URL as
the DEPO services. Safe to run before the first schema migration.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $root 'infra\windows\runtime-config.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$python = Join-Path $root 'backend\.dt_venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw 'Backend Python runtime is missing. Run install-depo.ps1 before the connectivity test.'
}
Push-Location $root
try {
  & $python -m backend.depo_platform.database_setup --connection-only
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL connectivity failed. Follow the structured error immediately above.' }
} finally { Pop-Location }

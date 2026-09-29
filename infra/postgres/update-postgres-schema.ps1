<#
.SYNOPSIS
Applies pending DEPO PostgreSQL migrations and verifies the resulting schema.

.DESCRIPTION
This schema-only command does not install dependencies, build the frontend,
start services, contact Neo4j, or run Spark. It uses DEPO_DATABASE_URL and
DEPO_DATABASE_SCHEMA from the selected environment file. Migrations are
transactional, serialized by a PostgreSQL advisory lock, and recorded in the
configured schema's depo_schema_migrations table.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw "Missing configuration: $envPath" }
if (-not (Test-Path -LiteralPath (Join-Path $root 'backend\.dt_venv\Scripts\python.exe') -PathType Leaf)) {
  throw 'Backend runtime is absent. Run the repository-root .\install-depo.ps1 once before applying schema-only updates.'
}
Write-Host 'Applying pending PostgreSQL migrations. No application services will be started.' -ForegroundColor Cyan
& (Join-Path $root 'infra\windows\initialize-depo-schema.ps1') -EnvFile $envPath
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "PostgreSQL schema update failed with exit code $LASTEXITCODE." }
Write-Host 'PostgreSQL schema update and verification passed.' -ForegroundColor Green

<#
.SYNOPSIS
Performs read-only verification of the deployed DEPO PostgreSQL schema.

.DESCRIPTION
Checks expected relations, columns, data types, constraints, indexes, and the
complete migration history. It does not execute DDL or write application data.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw "Missing configuration: $envPath" }
if (-not (Test-Path -LiteralPath (Join-Path $root 'backend\.dt_venv\Scripts\python.exe') -PathType Leaf)) {
  throw 'Backend runtime is absent. Run .\install-depo.ps1 once before validating the schema.'
}
Write-Host 'Running read-only PostgreSQL schema validation.' -ForegroundColor Cyan
& (Join-Path $root 'infra\windows\initialize-depo-schema.ps1') -EnvFile $envPath -CheckOnly
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "PostgreSQL schema validation failed with exit code $LASTEXITCODE." }
Write-Host 'PostgreSQL schema validation passed.' -ForegroundColor Green

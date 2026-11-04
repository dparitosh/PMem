[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SourceSchema,
  [string]$TargetSchema,
  [string]$EnvFile,
  [string]$Python,
  [int]$Rows = 25,
  [int]$Seed = 42,
  [string]$Kpis,
  [string]$Output,
  [switch]$Execute
)
$ErrorActionPreference='Stop'
if(-not $EnvFile){$EnvFile=Join-Path $PSScriptRoot '../.env.local'}
if(-not $Python){$Python=Join-Path $PSScriptRoot '../backend/.dt_venv/Scripts/python.exe'}
if(-not $Output){$Output=Join-Path $PSScriptRoot '../outputs/synthetic-analytics-report.json'}
$arguments=@((Join-Path $PSScriptRoot 'synthetic_analytics.py'), '--source-schema', $SourceSchema,
  '--env-file', $EnvFile, '--rows', $Rows, '--seed', $Seed, '--output', $Output)
if($TargetSchema){$arguments+=@('--target-schema',$TargetSchema)}
if($Kpis){$arguments+=@('--kpis',$Kpis)}
if($Execute){$arguments+='--execute'}
& $Python @arguments
if($LASTEXITCODE -ne 0){throw 'Synthetic analytics validation failed. Inspect the SQLSTATE/constraint or unsupported-type message. No reset or deletion was attempted.'}

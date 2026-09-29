<# .SYNOPSIS Runs supported read-only DEPO installation diagnostics. #>
[CmdletBinding()]
param(
  [ValidateSet('Prerequisites','Configuration','Runtime','All')][string]$Phase = 'All',
  [string]$EnvFile = '.env.local',
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [string]$Python = 'py',
  [switch]$SkipFrontend,
  [switch]$LocalInsecureDemo
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }

function Invoke-Diagnostic([string]$Name, [scriptblock]$Action) {
  Write-Host "`n=== DEPO diagnostic: $Name ===" -ForegroundColor Cyan
  $global:LASTEXITCODE = 0
  & $Action
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
  Write-Host "PASS: $Name" -ForegroundColor Green
}

if ($Phase -in @('Prerequisites','All')) {
  Invoke-Diagnostic 'software prerequisites' {
    & (Join-Path $root 'infra\windows\install-depo.ps1') -Python $Python -SkipFrontend:$SkipFrontend -CheckPrerequisites
  }
}
if ($Phase -in @('Configuration','Runtime','All')) {
  if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw "Missing configuration: $envPath. Run .\configure-depo.ps1 first." }
  Invoke-Diagnostic 'deployment configuration' {
    & (Join-Path $root 'infra\deployment\test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile -SkipEndpointChecks
  }
}
if ($Phase -in @('Runtime','All')) {
  if (-not (Test-Path -LiteralPath (Join-Path $root 'backend\.dt_venv\Scripts\python.exe'))) { throw 'Backend runtime is absent. Run .\install-depo.ps1 before Runtime diagnostics.' }
  Invoke-Diagnostic 'database, graph and optional Spark release preflight' {
    $parameters = @{ EnvFile = $envPath }
    if ($Profile -eq 'Production') { $parameters.Production = $true } else { $parameters.Bootstrap = $true }
    if ($LocalInsecureDemo) { $parameters.LocalInsecureDemo = $true }
    & (Join-Path $root 'infra\windows\test-depo-release.ps1') @parameters
  }
  Invoke-Diagnostic 'running service endpoints' {
    & (Join-Path $root 'infra\deployment\test-depo-deployment.ps1') -EnvFile $envPath -Profile $Profile
  }
}
Write-Host "`nDEPO diagnostics completed successfully for phase: $Phase" -ForegroundColor Green

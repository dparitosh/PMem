<# .SYNOPSIS Starts or stops an installed DEPO Windows deployment. #>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('Start','Stop','Restart')][string]$Action,
  [string]$EnvFile = '.env.local',
  [ValidateSet('Bootstrap','Production')][string]$Profile = 'Production',
  [switch]$SkipPostgres,
  [switch]$SkipFrontend,
  [switch]$SkipBaselineProvisioning
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'infra/windows/native-install-command.ps1')
Invoke-DepoLoggedAction -Root $PSScriptRoot -Name ('manage-'+$Action) -Action {
function Invoke-ManagedStep([string]$Script,[hashtable]$Parameters=@{}) {
  $global:LASTEXITCODE=0
  & $Script @Parameters
  if($LASTEXITCODE -ne 0){throw "DEPO $Action failed; subsequent steps were not run."}
}
foreach($phase in $(if($Action -eq 'Restart'){@('Stop','Start')}else{@($Action)})) {
  if($phase -eq 'Stop' -and -not $SkipFrontend){Invoke-ManagedStep (Join-Path $PSScriptRoot 'infra/windows/stop-depo-frontend.ps1')}
  $parameters=@{Action=$phase;EnvFile=$EnvFile;Profile=$Profile}
  if($SkipPostgres){$parameters.SkipPostgres=$true}
  if($SkipBaselineProvisioning){$parameters.SkipBaselineProvisioning=$true}
  Invoke-ManagedStep (Join-Path $PSScriptRoot 'infra/deployment/invoke-depo-lifecycle.ps1') $parameters
  if($phase -eq 'Start' -and -not $SkipFrontend){Invoke-ManagedStep (Join-Path $PSScriptRoot 'infra/windows/start-depo-frontend.ps1') @{EnvFile=$EnvFile}}
}
Write-Host "DEPO $Action completed. Database servers were not stopped."

}

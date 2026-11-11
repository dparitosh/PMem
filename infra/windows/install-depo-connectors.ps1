<# .SYNOPSIS Install an operator-reviewed, hash-pinned optional connector SDK lock. #>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$LockFile,[string]$EnvFile='.env.local',[switch]$CheckOnly)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'service-runtimes.ps1')
. (Join-Path $PSScriptRoot 'native-install-command.ps1')
. (Join-Path $PSScriptRoot 'deployment-process-guards.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$lock=(Resolve-Path -LiteralPath $LockFile).Path
$pins=@(Get-Content -LiteralPath $lock | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
if(-not $pins.Count -or @($pins | Where-Object { $_ -notmatch '^[a-z0-9][a-z0-9._-]*==[^ ]+ --hash=sha256:[a-f0-9]{64}$' }).Count){throw 'Connector SDK lock must contain reviewed exact pins with SHA256 hashes; URLs and pip options are not accepted.'}
$python=Get-DepoServicePython -Root $root -ServiceId ontology
if(-not (Test-Path -LiteralPath $python -PathType Leaf)){throw 'Install the semantic runtime using the standard installer first.'}
if($CheckOnly){Write-Host "Validated $($pins.Count) hash-pinned connector SDK requirements. No runtime or database changes performed.";return}
Assert-DepoRuntimeIdle -Python $python
Push-Location $root
try{
 Invoke-DepoNativeCommand -Executable $python -NativeArguments @('-m','pip','install','--disable-pip-version-check','--require-hashes','-r',$lock)
 Invoke-DepoNativeCommand -Executable $python -NativeArguments @('-m','pip','check')
 Write-Host 'Optional SDK lock installed in the existing semantic runtime. Restart application services and test the configured source connection. No profiles were approved or executed.'
}finally{Pop-Location}

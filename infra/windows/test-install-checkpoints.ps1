$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'install-checkpoints.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('depo-install-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$script:count=0
$script:proof='inventory-one'
$action={ $script:count++; $global:LASTEXITCODE=0 }
$probe={ return $script:proof }
$inputFile=Join-Path $testRoot 'lock.txt'
Set-Content -LiteralPath $inputFile -Value 'version-one'
$first=Get-DepoInstallFingerprint -Files @($inputFile) -Values @('python312')
Invoke-DepoDependencyStage -Root $testRoot -Name backend -Fingerprint $first -Action $action -Probe $probe
Invoke-DepoDependencyStage -Root $testRoot -Name backend -Fingerprint $first -Action $action -Probe $probe
if($script:count -ne 1){throw 'Completed dependencies were installed twice'}
$failed=$false
try { Invoke-DepoDependencyStage -Root $testRoot -Name frontend -Fingerprint $first -Action {throw 'simulated npm failure'} -Probe $probe } catch {$failed=$true}
if(-not $failed){throw 'Failure was hidden'}
if(Test-Path (Join-Path $testRoot 'logs/installation/checkpoints/frontend.json')){throw 'Failed stage was checkpointed'}
Invoke-DepoDependencyStage -Root $testRoot -Name backend -Fingerprint $first -Action $action -Probe $probe
if($script:count -ne 1){throw 'Unrelated failure invalidated backend receipt'}
$script:proof='inventory-two'
Invoke-DepoDependencyStage -Root $testRoot -Name backend -Fingerprint $first -Action $action -Probe $probe
if($script:count -ne 2){throw 'Changed runtime inventory was not detected'}
Set-Content -LiteralPath $inputFile -Value 'version-two'
$second=Get-DepoInstallFingerprint -Files @($inputFile) -Values @('python312')
Invoke-DepoDependencyStage -Root $testRoot -Name backend -Fingerprint $second -Action $action -Probe $probe
if($script:count -ne 3){throw 'Changed dependency lock was not detected'}
Invoke-DepoDependencyStage -Root $testRoot -Name backend -Fingerprint $second -Action $action -Probe $probe -Force
if($script:count -ne 4){throw 'Force reinstall ignored'}
Write-Host 'PASS: install/resume, failed-stage isolation, inventory change, lock invalidation and force repair.'
Write-Host "Test receipts retained: $testRoot"

. (Join-Path $PSScriptRoot 'runtime-config.ps1')
foreach($case in @(@('v22.22.0',$false),@('v23.9.1',$false),@('v24.0.0',$true),@('v24.22.0',$true),@('v25.0.0',$true),@('v26.1.0',$true),@('invalid',$false))) {
  if((Test-DepoNodeVersion $case[0]) -ne $case[1]){throw "Wrong Node acceptance: $($case[0])"}
}
Write-Host 'PASS: Node.js 24+ contract accepts newer major versions and rejects older or invalid versions.'

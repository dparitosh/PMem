$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$tree=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'setup-depo.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Setup script syntax failed'}
$fn=$tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'ConvertTo-SetupEnvironmentValue'},$true)
. ([scriptblock]::Create($fn.Extent.Text))
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('setup-config-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
 # Execute the actual setup policy expression and installer command against a
 # stub installer. No real credentials, services or database are touched.
 $policyParameter=$tree.ParamBlock.Parameters | Where-Object {$_.Name.VariablePath.UserPath -eq 'CredentialPolicy'}
 if($policyParameter.DefaultValue.Value -ne 'Synchronize'){throw 'Guided setup must synchronize by default'}
 $policyAssignment=$tree.Find({param($node) $node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -eq '$synchronizeCredentials'},$true)
 $installerCall=$tree.Find({param($node) $node -is [Management.Automation.Language.CommandAst] -and $node.CommandElements.Extent.Text -contains '-ReplaceExistingCredentials:$synchronizeCredentials'},$true)
 if(-not $policyAssignment -or -not $installerCall){throw 'Missing guided credential policy forwarding'}
 $root=$testRoot; $envPath=Join-Path $testRoot '.env.local'; $Python='fixture'; $ForceReinstall=$false
 Set-Content -LiteralPath (Join-Path $testRoot 'install-depo.ps1') -Value @'
param($EnvFile,$Python,[switch]$ForceReinstall,[switch]$StageOntologyUpdates,[switch]$ReplaceExistingCredentials)
$global:capturedSetupSynchronization=[bool]$ReplaceExistingCredentials
'@
 foreach($case in @(
  @{Policy='Synchronize';Auth='token';Store='postgres';Expected=$true},
  @{Policy='Validate';Auth='token';Store='postgres';Expected=$false},
  @{Policy='Synchronize';Auth='token';Store='env';Expected=$false},
  @{Policy='Synchronize';Auth='entra';Store='postgres';Expected=$false}
 )) {
  $CredentialPolicy=$case.Policy; $setupConfiguration=@{AUTH_MODE=$case.Auth;DEPO_CREDENTIAL_STORE=$case.Store}
  . ([scriptblock]::Create($policyAssignment.Extent.Text))
  . ([scriptblock]::Create($installerCall.Extent.Text))
  if($global:capturedSetupSynchronization -ne $case.Expected){throw 'Guided credential policy was not forwarded correctly'}
 }
 foreach($value in @('simple',' value with spaces ','value # literal',('"quoted'),("'quoted"),'a=b#c')) {
  $encoded=ConvertTo-SetupEnvironmentValue $value
  [IO.File]::WriteAllText((Join-Path $testRoot '.env.local'),('EXAMPLE='+$encoded),[Text.UTF8Encoding]::new($false))
  $read=Read-DepoEnvironment -Root $testRoot -EnvFile '.env.local'
  if($read.EXAMPLE -cne $value){throw 'Environment value round trip failed'}
 }
 foreach($value in @("line`nbreak",(' '+[char]34+"' ambiguous"))) {
  $rejected=$false
  try {ConvertTo-SetupEnvironmentValue $value | Out-Null} catch {$rejected=$true}
  if(-not $rejected){throw 'Invalid configuration accepted'}
 }
 Write-Host 'PASS: setup configuration round trips, invalid-value rejection and credential-policy forwarding; no application settings were changed.'
} finally {
 $file=Join-Path $testRoot '.env.local'
 if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}
 Remove-Item -LiteralPath (Join-Path $testRoot 'install-depo.ps1') -Force
 Remove-Item -LiteralPath $testRoot
}

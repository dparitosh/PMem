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
 Write-Host 'PASS: setup configuration round trips and invalid-value rejection; no application settings were changed.'
} finally {
 $file=Join-Path $testRoot '.env.local'
 if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}
 Remove-Item -LiteralPath $testRoot
}

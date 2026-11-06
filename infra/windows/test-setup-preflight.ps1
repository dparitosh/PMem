# Offline guided-setup regression. Child checks are isolated stubs.
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$tree=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'setup-depo.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Setup syntax failed'}
$function=$tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-DepoSetupPreflight'},$true)
. ([scriptblock]::Create($function.Extent.Text))
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('pmem-preflight-'+[guid]::NewGuid().ToString('N'))
foreach($folder in @('infra/windows','infra/deployment','backend/.dt_venv/Scripts','artifacts')) { New-Item -ItemType Directory -Path (Join-Path $fixture $folder) -Force | Out-Null }
$global:setupPreflightTrace=[Collections.Generic.List[string]]::new()
$global:setupPreflightFailure=''
function Read-DepoEnvironment { @{ARTIFACT_STORAGE=(Join-Path $fixture 'artifacts')} }
foreach($path in @('infra/windows/update-depo-windows.ps1','infra/windows/install-depo.ps1','infra/deployment/test-installation-package.ps1','infra/deployment/test-depo-deployment.ps1','infra/deployment/test-depo-frontend-config.ps1')) {
  Set-Content -LiteralPath (Join-Path $fixture $path) -Value @'
$global:setupPreflightTrace.Add($MyInvocation.MyCommand.Name)
$global:LASTEXITCODE=0
if($global:setupPreflightFailure -eq $MyInvocation.MyCommand.Name){$global:LASTEXITCODE=17}
if($MyInvocation.MyCommand.Name -eq 'update-depo-windows.ps1' -and $args -notcontains '-PreflightOnly'){throw 'Upgrade preflight must not mutate the deployment'}
'@
}
try {
  foreach($failure in @('test-installation-package.ps1','test-depo-deployment.ps1','test-depo-frontend-config.ps1','install-depo.ps1')) {
    $global:setupPreflightTrace.Clear(); $global:setupPreflightFailure=$failure
    $stopped=$false; $rejected=$false
    try { Invoke-DepoSetupPreflight $fixture 'fixture.env' 'TestPython'; $stopped=$true } catch {$rejected=$true}
    if(-not $rejected -or $stopped -or $global:setupPreflightTrace[-1] -ne $failure){throw "Preflight did not stop at $failure"}
  }
  $global:setupPreflightFailure=''
  Invoke-DepoSetupPreflight $fixture 'fixture.env' 'TestPython'
  Set-Content -LiteralPath (Join-Path $fixture 'backend/.dt_venv/Scripts/python.exe') -Value 'not executed'
  $global:setupPreflightTrace.Clear()
  Invoke-DepoSetupPreflight $fixture 'fixture.env' 'TestPython'
  if($global:setupPreflightTrace.Count -ne 1 -or $global:setupPreflightTrace[0] -ne 'update-depo-windows.ps1'){throw 'Existing setup did not reuse upgrade preflight'}
  $global:setupPreflightFailure='update-depo-windows.ps1'
  $rejected=$false
  try { Invoke-DepoSetupPreflight $fixture 'fixture.env' 'TestPython' } catch {$rejected=$true}
  if(-not $rejected){throw 'Upgrade preflight failure was ignored'}
  if(@(Get-ChildItem -LiteralPath (Join-Path $fixture 'artifacts') -Force).Count){throw 'Storage probe was not cleaned up'}
  $source=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'setup-depo.ps1'))
  if($source.IndexOf('Invoke-DepoSetupPreflight -Root $root') -gt $source.IndexOf("foreach(`$name in @('stop-depo-frontend'")){throw 'Setup stops before preflight'}
  Write-Host 'PASS: fresh setup failure isolation, existing upgrade preflight, native exit propagation, ordering and storage probe cleanup.'
} finally {
  $resolved=[IO.Path]::GetFullPath($fixture)
  if(-not $resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()),[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe fixture cleanup'}
  Remove-Item -LiteralPath $resolved -Recurse -Force
  Remove-Variable -Name setupPreflightTrace,setupPreflightFailure -Scope Global
}

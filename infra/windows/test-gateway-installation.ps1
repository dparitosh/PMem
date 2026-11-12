# Local contract checks only: Azure CLI is mocked, no real environment is edited.
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$global:gatewayTestCalls=[Collections.Generic.List[object]]::new()
$global:gatewayTestFailure=''
function global:az {
  $arguments=@($args);$global:gatewayTestCalls.Add($arguments)
  $global:LASTEXITCODE=0
  if($global:gatewayTestFailure -and ($arguments -join ' ') -match $global:gatewayTestFailure){$global:LASTEXITCODE=42}
}
try {
 $registration=@{ResourceGroup='fixture-rg';SubscriptionId='fixture-subscription';ApimServiceName='fixture-apim'}
 foreach($name in @('Ontology','Graph','Ingestion','Oslc','Qif','Agentic','Catalog','DataProducts','Ceim','DataPipeline')){$registration[$name+'ServiceUrl']='https://fixture.invalid'}
 & (Join-Path $root 'infra/azure-apim/register-depo-apis.ps1') @registration
 if(@($global:gatewayTestCalls | Where-Object {($_ -join ' ') -match 'api import' -and ($_ -join ' ') -match '--protocols https'}).Count -ne 10){throw 'OpenAPI imports must expose HTTPS'}
 if($global:gatewayTestCalls.Count -ne 21){throw 'Expected subscription selection and twenty API imports'}
 if(($global:gatewayTestCalls[0] -join ' ') -notmatch 'account set --subscription fixture-subscription'){throw 'Azure subscription was not selected'}
 foreach($phase in @('account set','api import','rest')) {
  $global:gatewayTestCalls.Clear();$global:gatewayTestFailure=$phase;$rejected=$false
  try{& (Join-Path $root 'infra/azure-apim/register-depo-apis.ps1') @registration}catch{$rejected=$true}
  $expected=if($phase -eq 'account set'){1}elseif($phase -eq 'api import'){2}else{3}
  if(-not $rejected -or $global:gatewayTestCalls.Count -ne $expected){throw 'CLI failure did not stop subsequent imports'}
 }
 $global:gatewayTestFailure='';$global:gatewayTestCalls.Clear()
 $policy=@{ResourceGroup='fixture-rg';SubscriptionId='fixture-subscription';ApimServiceName='fixture-apim';OpenIdConfigUrl='https://fixture.invalid/.well-known/openid-configuration';Audience='fixture-audience'}
 & (Join-Path $root 'infra/azure-apim/register-depo-policies.ps1') @policy
 $calls=$global:gatewayTestCalls | ForEach-Object {$_ -join ' '}
 if($calls.Count -ne 21 -or -not ($calls -match '/apis/depo-schema-sets/policies/') -or -not ($calls -match '/apis/depo-ceim/policies/') -or -not ($calls -match '/apis/depo-data-pipeline/policies/')){throw 'Policies do not cover the manifest API IDs'}
 $global:gatewayTestFailure='rest';$global:gatewayTestCalls.Clear();$rejected=$false
 try{& (Join-Path $root 'infra/azure-apim/register-depo-policies.ps1') @policy}catch{$rejected=$true}
 if(-not $rejected -or $global:gatewayTestCalls.Count -ne 2){throw 'Policy failure did not stop subsequent updates'}
} finally {
 Remove-Item Function:global:az
 Remove-Variable gatewayTestCalls,gatewayTestFailure -Scope Global
 $global:LASTEXITCODE=0
}

. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$tempRoot=[IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$fixture=Join-Path $tempRoot ('gateway-configuration-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
try {
 foreach($relative in @('configure-depo.ps1','infra/deployment/new-depo-deployment-config.ps1','infra/deployment/set-depo-admin-key.ps1','infra/windows/runtime-config.ps1','config/deployment.env.example','frontend/.env.example')){
  $destination=Join-Path $fixture $relative
  New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $root $relative) -Destination $destination
 }
 & (Join-Path $fixture 'configure-depo.ps1') -AuthMode token -GatewayUrl 'https://gateway.invalid'
 $values=Read-DepoEnvironment -Root $fixture -EnvFile '.env.local'
 $browser=Read-DepoEnvironment -Root $fixture -EnvFile 'frontend/.env.local'
 if($values.DEPO_ROUTING_MODE -ne 'gateway' -or $values.DEPO_API_GATEWAY_URL -ne 'https://gateway.invalid' -or $browser.VITE_API_GATEWAY_URL -ne 'https://gateway.invalid'){throw 'Root and browser gateway routing diverged'}
 $before=(Get-FileHash -LiteralPath (Join-Path $fixture '.env.local')).Hash
 $rejected=$false
 try{& (Join-Path $fixture 'configure-depo.ps1') -Force -GatewayUrl 'https://user:password@gateway.invalid'}catch{$rejected=$true}
 if(-not $rejected -or (Get-FileHash -LiteralPath (Join-Path $fixture '.env.local')).Hash -ne $before){throw 'Invalid gateway changed generated configuration'}
 & (Join-Path $fixture 'configure-depo.ps1') -Force -AuthMode token
 $local=Read-DepoEnvironment -Root $fixture -EnvFile '.env.local'
 if($local.DEPO_ROUTING_MODE -ne 'local' -or $local.DEPO_API_GATEWAY_URL){throw 'Local configuration unexpectedly requires a gateway'}
 Write-Host 'PASS: twenty manifest API registrations and policies, CLI failure stops, Azure subscription selection, and isolated root/browser gateway configuration. No Azure deployment or customer configuration changed.'
} finally {
 $resolved=[IO.Path]::GetFullPath($fixture)
 if(-not $resolved.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'gateway-configuration-*'){throw 'Refusing unexpected fixture cleanup path'}
 Remove-Item -LiteralPath $resolved -Recurse -Force
}

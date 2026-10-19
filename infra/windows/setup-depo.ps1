<# .SYNOPSIS Guided workstation setup; reuse this launcher to resume installation. #>
[CmdletBinding()]
param([string]$Python='py', [switch]$ForceReinstall, [ValidateSet('Menu','Setup','Start','Stop','Restart')][string]$Action='Menu')
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'native-install-command.ps1')
Invoke-DepoLoggedAction -Root $root -Name ('setup-'+$Action) -Action {
Set-Location -LiteralPath $root
if($Action -eq 'Menu') {
  Write-Host '1. Install / update / repair'
  Write-Host '2. Start PMem'
  Write-Host '3. Stop PMem'
  Write-Host '4. Restart PMem'
  Write-Host '0. Exit'
  switch(Read-Host 'Choose an action') {
    '1' {$Action='Setup'}
    '2' {$Action='Start'}
    '3' {$Action='Stop'}
    '4' {$Action='Restart'}
    '0' {return}
    default {throw 'Choose 0, 1, 2, 3 or 4.'}
  }
}
if($Action -ne 'Setup') {
  & (Join-Path $root 'manage-depo.ps1') -Action $Action
  return
}
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
function Read-SetupValue([string]$Label,[string]$Default) {
  $value=Read-Host "$Label [$Default]"
  if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
  if ($value -match '[\r\n]') { throw 'Connection values must be one line.' }
  return $value
}
function Read-SetupSecret([string]$Label) {
  $secret=Read-Host $Label -AsSecureString
  $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
$nodeSettings=@{}
if(Test-Path -LiteralPath (Join-Path $root '.env.local')){$nodeSettings=Read-DepoEnvironment -Root $root -EnvFile '.env.local'}
$nodeRuntime=Get-DepoNodeRuntime -Root $root -NodeJsDir $nodeSettings['DEPO_NODEJS_DIR']
$env:Path=$nodeRuntime.Directory+';'+$env:Path
Write-Host "Setup using Node.js $($nodeRuntime.Version)"
if ($Python -eq 'py' -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
  $portablePython=Join-Path $root '../../Python312/python.exe'
  if(Test-Path -LiteralPath $portablePython){$Python=$portablePython}
}
$envPath=Join-Path $root '.env.local'
if (-not (Test-Path -LiteralPath $envPath)) {
  Write-Host 'First installation: application keys are generated automatically. Supply the existing PostgreSQL application database and running Neo4j connection. No database is deleted or recreated.'
  $dbHost=Read-SetupValue 'PostgreSQL host' '127.0.0.1'
  $dbPort=Read-SetupValue 'PostgreSQL port' '5432'
  $dbName=Read-SetupValue 'Existing application database' 'depo'
  $dbUser=Read-SetupValue 'Application database user' 'depo_app'
  $dbPassword=Read-SetupSecret 'Database password (hidden)'
  $graphUri=Read-SetupValue 'Neo4j URI' 'bolt://127.0.0.1:7687'
  $graphDatabase=Read-SetupValue 'Neo4j database' 'neo4j'
  $graphUser=Read-SetupValue 'Neo4j user' 'neo4j'
  $graphPassword=Read-SetupSecret 'Neo4j password (hidden)'
  if ([string]::IsNullOrEmpty($dbPassword) -or [string]::IsNullOrEmpty($graphPassword)) { throw 'Database passwords are required; no configuration was created.' }
  if ($dbHost -notmatch '^[a-zA-Z0-9.-]+$' -or $dbPort -notmatch '^\d+$' -or [int]$dbPort -lt 1 -or [int]$dbPort -gt 65535) { throw 'Invalid PostgreSQL host or port.' }
  $graphParsed=[Uri]$graphUri
  if ($graphParsed.Scheme -notin @('bolt','neo4j','bolt+s','neo4j+s') -or $graphParsed.UserInfo -or -not $graphParsed.Host) { throw 'Use a Neo4j URI without embedded credentials.' }
  if (($graphUser+$graphDatabase+$graphPassword) -match '[\r\n]') { throw 'Neo4j settings must be one line.' }
  $sslMode=if($dbHost -in @('127.0.0.1','localhost')){'disable'}else{'require'}
  $tls=if($graphParsed.Scheme.EndsWith('+s')){'required'}else{'disabled'}
  if ($tls -eq 'disabled' -and -not $graphParsed.IsLoopback) { throw 'Use bolt+s or neo4j+s for a remote Neo4j server.' }
  & (Join-Path $root 'infra/deployment/new-depo-deployment-config.ps1') -OutputPath '.env.local' -AuthMode token
  $updates=@{
    DEPO_DATABASE_URL=('postgresql://'+[Uri]::EscapeDataString($dbUser)+':'+[Uri]::EscapeDataString($dbPassword)+'@'+$dbHost+':'+$dbPort+'/'+[Uri]::EscapeDataString($dbName)+'?sslmode='+$sslMode)
    ARTIFACT_STORAGE=(Join-Path $root 'data/artifacts'); ALLOWED_ORIGINS='http://127.0.0.1:3000'; OSLC_BASE_URL='http://127.0.0.1:8015'
    NEO4J_URI=$graphUri; NEO4J_USER=$graphUser; NEO4J_PASS=$graphPassword; NEO4J_DATABASE=$graphDatabase
    NEO4J_TLS_MODE=$tls; NEO4J_ENCRYPTED=([string]($tls -eq 'required')).ToLower(); NEO4J_TLS_VERIFY='true'
    DEPO_BROWSER_AUTH_MODE='local'; DEPO_LOCAL_BROWSER_WRITES='true'; DEPO_LOCAL_SESSION_AUTHORITY_URL='http://127.0.0.1:8011'
    DEPO_TENANT_ID='local'; DEPO_PROJECT_ID='pmem'; AGENT_MEMORY_SCOPE='local:pmem'
  }
  $lines=[Collections.Generic.List[string]]::new()
  foreach($line in [IO.File]::ReadAllLines($envPath)) {
    if($line -match '^([A-Z0-9_]+)=') {
      $key=$Matches[1]
      if($updates.ContainsKey($key)) { $value=[string]$updates[$key]
        if ($value -match '^\s|\s$|\s+#|^["'']') {
          if (-not $value.Contains("'")) { $value="'"+$value+"'" }
          elseif (-not $value.Contains('"')) { $value='"'+$value+'"' }
          else { throw "Setting $key requires manual .env quoting; generated keys were preserved." }
        }
        $lines.Add($key+'='+$value); $updates.Remove($key); continue }
    }
    $lines.Add($line)
  }
  foreach($key in $updates.Keys) { $lines.Add($key+'='+$updates[$key]) }
  [IO.File]::WriteAllLines($envPath,$lines,[Text.UTF8Encoding]::new($false))
  $dbPassword=$null; $graphPassword=$null; $updates=$null
} else { Write-Host 'Existing configuration and application keys retained.' }
$browser=Join-Path $root 'frontend/.env.local'
if(-not(Test-Path -LiteralPath $browser)){Copy-Item -LiteralPath (Join-Path $root 'frontend/.env.example') -Destination $browser}
Write-Host 'Stopping tracked PMem processes before upgrade; database servers remain running.'
foreach($name in @('stop-depo-frontend','stop-depo-services')) {
  $global:LASTEXITCODE=0
  & (Join-Path $PSScriptRoot ($name+'.ps1'))
  if($LASTEXITCODE -ne 0){throw "Managed shutdown failed: $name"}
}
& (Join-Path $root 'install-depo.ps1') -EnvFile $envPath -Python $Python -ForceReinstall:$ForceReinstall -StageOntologyUpdates
Write-Host 'Setup finished. Application credentials were applied by the installer when central credential storage is enabled. Existing credentials were not rotated.'

}

param(
  [Parameter(Mandatory = $true)][string]$ZeppelinHome,
  [Parameter(Mandatory = $true)][string]$ConfigDir,
  [Parameter(Mandatory = $true)][string]$NotebookDir,
  [int]$Port = 8080
)
$ErrorActionPreference = 'Stop'
$cmd = Join-Path $ZeppelinHome 'bin\zeppelin.cmd'
$war = Join-Path $ZeppelinHome 'zeppelin-web-angular-0.12.1.war'
if (-not (Test-Path $cmd)) { throw "Zeppelin launcher not found: $cmd" }
if (-not (Test-Path $war)) { throw "Zeppelin web WAR not found: $war" }
if (-not (Test-Path $ConfigDir)) { New-Item -ItemType Directory -Force $ConfigDir | Out-Null }
$env:ZEPPELIN_HOME = $ZeppelinHome
$env:ZEPPELIN_CONF_DIR = $ConfigDir
$env:ZEPPELIN_WAR = $war
$env:ZEPPELIN_NOTEBOOK_DIR = $NotebookDir
$env:ZEPPELIN_LOG_DIR = Join-Path $ConfigDir 'logs'
$env:ZEPPELIN_PID_DIR = (Join-Path $ConfigDir 'run')
foreach ($d in @($env:ZEPPELIN_NOTEBOOK_DIR,$env:ZEPPELIN_LOG_DIR,$env:ZEPPELIN_PID_DIR)) { New-Item -ItemType Directory -Force $d | Out-Null }
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) { Write-Output "Zeppelin already listening on port $Port"; exit 0 }
Start-Process -FilePath $cmd -ArgumentList '--config', $ConfigDir -WorkingDirectory (Join-Path $ZeppelinHome 'bin') -WindowStyle Hidden | Out-Null
for ($i=0; $i -lt 30; $i++) {
  try { $r=Invoke-WebRequest "http://127.0.0.1:$Port/api/version" -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { Write-Output "Zeppelin ready: http://127.0.0.1:$Port"; exit 0 } } catch {}
  Start-Sleep -Seconds 2
}
throw "Zeppelin did not become ready on port $Port. Inspect $env:ZEPPELIN_LOG_DIR."

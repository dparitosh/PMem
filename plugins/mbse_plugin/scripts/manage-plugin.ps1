param(
  [Parameter(Mandatory=$true)][ValidateSet('Install','Configure','Start','Stop','Verify')][string]$Action,
  [string]$Python = 'python',
  [string]$WheelPath = '',
  [string]$InstallDir = '',
  [string]$IngestionUrl = 'http://127.0.0.1:8014/api/v1',
  [int]$Port = 8020
)
$ErrorActionPreference = 'Stop'
$packageRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $InstallDir) { $InstallDir = Join-Path $packageRoot '.runtime' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$runtimePython = Join-Path $InstallDir 'venv\Scripts\python.exe'
$configPath = Join-Path $InstallDir 'config.json'
$pidPath = Join-Path $InstallDir 'service.pid'
if ($Action -eq 'Install') {
  New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
  if (-not (Test-Path $runtimePython)) {
    & $Python -m venv (Join-Path $InstallDir 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
  }
  $installSource = if ($WheelPath) { (Resolve-Path $WheelPath).Path } else { $packageRoot }
  & $runtimePython -m pip install $installSource
  if ($LASTEXITCODE -ne 0) { throw 'Plugin installation failed' }
  Write-Host 'Installed MBSE and SMW. Next run Configure.'
  exit
}
if ($Action -eq 'Configure') {
  if (Test-Path $configPath) { throw 'Configuration already exists. Back it up and edit it explicitly; secrets will not be overwritten.' }
  if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Invalid port' }
  New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
  $bytes = New-Object byte[] 48
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  @{ MBSE_PLUGIN_TOKEN=[Convert]::ToBase64String($bytes); DEPO_INGESTION_URL=$IngestionUrl; DEPO_INGESTION_TOKEN=''; Port=$Port } | ConvertTo-Json | Set-Content -LiteralPath $configPath
  Write-Host "Created $configPath. Protect this file with user-only access; it contains a plaintext secret."
  exit
}
if (-not (Test-Path $runtimePython)) { throw 'Run Install first' }
if (-not (Test-Path $configPath)) { throw 'Run Configure first' }
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$Port = [int]$settings.Port
if (-not $settings.MBSE_PLUGIN_TOKEN -or $Port -lt 1024 -or $Port -gt 65535) { throw 'Invalid configuration' }
if ($Action -eq 'Stop') {
  if (-not (Test-Path $pidPath)) { Write-Host 'No tracked process'; exit }
  $servicePid = [int](Get-Content -LiteralPath $pidPath)
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$servicePid"
  if ($process) {
    if ($process.ExecutablePath -ne $runtimePython -or $process.CommandLine -notmatch 'mbse_plugin.app:app') { throw 'PID ownership mismatch; refusing to stop process' }
    Stop-Process -Id $servicePid
  }
  Remove-Item -LiteralPath $pidPath
  exit
}
if ($Action -eq 'Start') {
  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already occupied" }
  foreach ($key in @('MBSE_PLUGIN_TOKEN','DEPO_INGESTION_URL','DEPO_INGESTION_TOKEN')) { [Environment]::SetEnvironmentVariable($key, [string]$settings.$key, 'Process') }
  $process = Start-Process -FilePath $runtimePython -ArgumentList "-m uvicorn mbse_plugin.app:app --host 127.0.0.1 --port $Port" -WorkingDirectory $InstallDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $InstallDir 'stdout.log') -RedirectStandardError (Join-Path $InstallDir 'stderr.log') -PassThru
  Set-Content -LiteralPath $pidPath -Value $process.Id
  Write-Host "Started PID $($process.Id). Run Verify to check readiness."
  exit
}
$headers = @{ Authorization = "Bearer $($settings.MBSE_PLUGIN_TOKEN)" }
$base = "http://127.0.0.1:$Port"
$tools = Invoke-RestMethod "$base/tools" -Headers $headers -TimeoutSec 10
if ($tools.tools.Count -ne 6) { throw 'Expected six plugin tools' }
$template = Invoke-RestMethod "$base/teamcenter-smw/template" -Headers $headers -TimeoutSec 10
if ($template.connector_enabled -ne $false) { throw 'SMW must remain offline' }
Write-Host "MBSE and SMW endpoints verified at $base"

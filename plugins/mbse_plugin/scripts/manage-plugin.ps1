param(
  [Parameter(Mandatory=$true)][ValidateSet('Install','Configure','SyncCredentials','Start','Stop','Verify')][string]$Action,
  [string]$EnvFile = '',
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
function Get-ExecutionCredentials {
  $values = @{}
  if ($EnvFile) {
    $selectedFile = [IO.Path]::GetFullPath($EnvFile)
    if (-not (Test-Path -LiteralPath $selectedFile -PathType Leaf)) { throw 'Selected environment file does not exist' }
    foreach ($line in Get-Content -LiteralPath $selectedFile) {
      $entry = $line.Trim()
      if (-not $entry -or $entry.StartsWith('#')) { continue }
      if ($entry -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { throw 'Invalid environment entry; expected KEY=value' }
      $name = $Matches[1]
      if ($name -notin @('DATA_JOB_EXECUTION_TOKEN','DEPO_APIM_SUBSCRIPTION_KEY')) { continue }
      if ($values.ContainsKey($name)) { throw "Duplicate setting: $name" }
      $value = $Matches[2].Trim()
      if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) { $value = $value.Substring(1, $value.Length - 2) }
      $values[$name] = $value
    }
  } else {
    $values['DATA_JOB_EXECUTION_TOKEN'] = $env:DATA_JOB_EXECUTION_TOKEN
    $values['DEPO_APIM_SUBSCRIPTION_KEY'] = $env:DEPO_APIM_SUBSCRIPTION_KEY
  }
  if (-not $values['DATA_JOB_EXECUTION_TOKEN'] -or $values['DATA_JOB_EXECUTION_TOKEN'] -match '<.*>') { throw 'Supply -EnvFile with the current central DATA_JOB_EXECUTION_TOKEN before configuring or synchronizing the plugin' }
  return $values
}
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
  $credentials = Get-ExecutionCredentials
  $upstreamUri = $null
  if (-not [Uri]::TryCreate($IngestionUrl, [UriKind]::Absolute, [ref]$upstreamUri) -or $upstreamUri.Scheme -notin @('http','https') -or $upstreamUri.UserInfo -or $upstreamUri.Query -or $upstreamUri.Fragment -or -not $upstreamUri.AbsolutePath.TrimEnd('/').EndsWith('/api/v1')) { throw 'IngestionUrl must be an HTTP(S) URL ending in /api/v1' }
  New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
  $bytes = New-Object byte[] 48
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  @{ MBSE_PLUGIN_TOKEN=[Convert]::ToBase64String($bytes); DEPO_INGESTION_URL=$IngestionUrl; DEPO_INGESTION_TOKEN=$credentials['DATA_JOB_EXECUTION_TOKEN']; DEPO_APIM_SUBSCRIPTION_KEY=$credentials['DEPO_APIM_SUBSCRIPTION_KEY']; Port=$Port } | ConvertTo-Json | Set-Content -LiteralPath $configPath
  Write-Host "Created $configPath. Protect this file with user-only access; it contains a plaintext secret."
  exit
}
if (-not (Test-Path $runtimePython)) { throw 'Run Install first' }
if (-not (Test-Path $configPath)) { throw 'Run Configure first' }
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$Port = [int]$settings.Port
if (-not $settings.MBSE_PLUGIN_TOKEN -or $Port -lt 1024 -or $Port -gt 65535) { throw 'Invalid configuration' }
if ($Action -eq 'SyncCredentials') {
  $credentials = Get-ExecutionCredentials
  $settings | Add-Member -NotePropertyName DEPO_INGESTION_TOKEN -NotePropertyValue $credentials['DATA_JOB_EXECUTION_TOKEN'] -Force
  $settings | Add-Member -NotePropertyName DEPO_APIM_SUBSCRIPTION_KEY -NotePropertyValue $credentials['DEPO_APIM_SUBSCRIPTION_KEY'] -Force
  $settings | ConvertTo-Json | Set-Content -LiteralPath $configPath
  Write-Host 'Execution credentials synchronized. Restart the plugin, then run Verify. The plugin access token was preserved.'
  exit
}
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
  if (-not $settings.DEPO_INGESTION_TOKEN) { throw 'Run SyncCredentials with -EnvFile before Start' }
  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already occupied" }
  foreach ($key in @('MBSE_PLUGIN_TOKEN','DEPO_INGESTION_URL','DEPO_INGESTION_TOKEN','DEPO_APIM_SUBSCRIPTION_KEY')) { [Environment]::SetEnvironmentVariable($key, [string]$settings.$key, 'Process') }
  $process = Start-Process -FilePath $runtimePython -ArgumentList "-m uvicorn mbse_plugin.app:app --host 127.0.0.1 --port $Port" -WorkingDirectory $InstallDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $InstallDir 'stdout.log') -RedirectStandardError (Join-Path $InstallDir 'stderr.log') -PassThru
  Set-Content -LiteralPath $pidPath -Value $process.Id
  $deadline = (Get-Date).AddSeconds(60)
  $ready = $false
  while ((Get-Date) -lt $deadline) {
    $process.Refresh()
    if ($process.HasExited) { break }
    try {
      $result = Invoke-RestMethod "http://127.0.0.1:$Port/tools" -Headers @{Authorization="Bearer $($settings.MBSE_PLUGIN_TOKEN)"} -TimeoutSec 2
      if ($result.tools.Count -eq 6) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
  }
  if (-not $ready) {
    $process.Refresh()
    if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    Remove-Item -LiteralPath $pidPath -ErrorAction SilentlyContinue
    throw 'Plugin startup failed. Inspect stderr.log and stdout.log in InstallDir.'
  }
  Write-Host "Plugin ready on http://127.0.0.1:$Port. Run Verify to check upstream execution credentials."
  exit
}
$headers = @{ Authorization = "Bearer $($settings.MBSE_PLUGIN_TOKEN)" }
$base = "http://127.0.0.1:$Port"
$tools = Invoke-RestMethod "$base/tools" -Headers $headers -TimeoutSec 10
if ($tools.tools.Count -ne 6) { throw 'Expected six plugin tools' }
$template = Invoke-RestMethod "$base/teamcenter-smw/template" -Headers $headers -TimeoutSec 10
if ($template.connector_enabled -ne $false) { throw 'SMW must remain offline' }
$upstream = Invoke-RestMethod "$base/upstream-check" -Headers $headers -TimeoutSec 20
if ($upstream.status -ne 'ready' -or $upstream.job_executed -ne $false) { throw 'Upstream credential verification failed' }
Write-Host "MBSE and SMW endpoints verified at $base"

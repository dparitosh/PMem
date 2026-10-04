param(
  [string]$EnvFile = '.env.local',
  [ValidateRange(1, 65535)][int]$Port = 3000,
  [string]$BindHost = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root 'backend\.dt_venv\Scripts\python.exe'
$dist = Join-Path $root 'frontend\dist'
$index = Join-Path $dist 'index.html'
$stateDir = Join-Path $root 'logs\windows-services'
$pidFile = Join-Path $stateDir 'frontend.pid'
$stdout = Join-Path $stateDir 'frontend.out.log'
$stderr = Join-Path $stateDir 'frontend.err.log'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "Project Python runtime was not found: $python. Run infra/windows/install-depo.ps1 first."
}
if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
  throw "Built frontend was not found: $index. Run infra/windows/install-depo.ps1 or npm run build first."
}
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'process-control.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $BindHost) {
  $BindHost = if ($values['DEPO_FRONTEND_HOST']) { $values['DEPO_FRONTEND_HOST'] } elseif ($values['DEPO_SERVICE_HOST']) { $values['DEPO_SERVICE_HOST'] } else { '127.0.0.1' }
}
if (-not $PSBoundParameters.ContainsKey('Port') -and $values['DEPO_FRONTEND_PORT']) { $Port = [int]$values['DEPO_FRONTEND_PORT'] }
if ($Port -lt 1 -or $Port -gt 65535) { throw 'DEPO_FRONTEND_PORT must be between 1 and 65535.' }
if ($BindHost -notmatch '^[A-Za-z0-9.:-]+$') { throw 'Invalid frontend bind address.' }
$probeHost = Get-DepoProbeHost $BindHost

$routing = Resolve-DepoRouting $values
$browserRouting = @{}
foreach ($key in $routing.Keys) {
  if ($key.StartsWith('VITE_')) { $browserRouting[$key] = $routing[$key] }
}
if ($values['DEPO_ROUTING_MODE'] -and (Get-Content -LiteralPath $index -Raw) -notmatch 'depo-runtime-config.js') {
  throw 'This frontend predates runtime routing. Rebuild once using npm run build in frontend.'
}
$indexFile = Get-Item -LiteralPath $index
# Configuration, dependency and public asset changes also require a rebuild.
$frontendRoot = Join-Path $root 'frontend'
$buildInputs = @(Get-ChildItem -LiteralPath (Join-Path $frontendRoot 'src') -File -Recurse)
$publicRoot = Join-Path $frontendRoot 'public'
if (Test-Path -LiteralPath $publicRoot -PathType Container) {
  $buildInputs += @(Get-ChildItem -LiteralPath $publicRoot -File -Recurse)
}
$buildInputs += @(Get-ChildItem -LiteralPath $frontendRoot -File | Where-Object {
  $_.Name -like '.env*' -or $_.Name -like 'vite.config.*' -or
  $_.Name -in @('index.html', 'package.json', 'package-lock.json', 'buildReceipt.mjs')
})
# Compare content hashes as deployment copies may preserve timestamps.
$receiptPath = Join-Path $dist 'depo-build-receipt.json'
if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
  throw 'Frontend build has no build receipt. Run npm run build in frontend from the current release before starting it.'
}
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ($receipt.version -ne 1 -or -not $receipt.inputs) { throw 'Invalid frontend build receipt; rebuild frontend.' }
$expectedInputs = @{}
foreach ($property in $receipt.inputs.PSObject.Properties) { $expectedInputs[$property.Name] = [string]$property.Value }
if ($expectedInputs.Count -ne $buildInputs.Count) { throw 'Frontend build inputs were added or removed; rebuild frontend.' }
foreach ($inputFile in $buildInputs) {
  $relativeInput = $inputFile.FullName.Substring($frontendRoot.Length + 1).Replace('\', '/')
  if (-not $expectedInputs.ContainsKey($relativeInput) -or
      (Get-FileHash -LiteralPath $inputFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedInputs[$relativeInput]) {
    throw "Frontend build does not match input $relativeInput. Rebuild frontend before starting it."
  }
}
$indexContent = Get-Content -LiteralPath $index -Raw
$bundleMatch = [regex]::Match($indexContent, '<script[^>]+src="(/?assets/index-[^"]+\.js)"')
if (-not $bundleMatch.Success) { throw "Could not identify the production bundle in $index. Run npm run build in frontend." }
$bundleRelativePath = $bundleMatch.Groups[1].Value.TrimStart('/').Replace('/', [IO.Path]::DirectorySeparatorChar)
$bundlePath = Join-Path $dist $bundleRelativePath
if (-not (Test-Path -LiteralPath $bundlePath -PathType Leaf)) { throw "Frontend bundle referenced by index.html is missing: $bundlePath" }
if ($values['DEPO_ROUTING_MODE'] -and (Get-Content -LiteralPath $bundlePath -Raw) -notmatch 'DEPO_RUNTIME_CONFIG') {
  throw 'The frontend HTML includes runtime routing but the compiled application does not. Rebuild from the updated frontend source before serving it.'
}
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
Write-DepoBrowserRouting -Root $root -EnvFile $EnvFile

if (Test-Path -LiteralPath $pidFile) {
  $recordedPid = [int](Get-Content -LiteralPath $pidFile)
  $existing = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
  $details = if ($existing) { Get-CimInstance Win32_Process -Filter "ProcessId = $recordedPid" -ErrorAction SilentlyContinue } else { $null }
  if ($details -and $details.ExecutablePath -and $details.ExecutablePath.ToLowerInvariant() -eq $python.ToLowerInvariant() -and
      $details.CommandLine -match 'http\.server' -and $details.CommandLine -match 'frontend[\\/]dist') {
    try {
      $response = Invoke-WebRequest -Uri "http://${probeHost}:$Port/" -UseBasicParsing -TimeoutSec 5
      if ($response.StatusCode -eq 200 -and $response.Content -match '<div id="root"' -and
          $response.Content.Contains($bundleMatch.Groups[1].Value) -and
          (Test-DepoListener $recordedPid $python 'http.server' $Port $BindHost)) {
        Write-Host "DEPO frontend is already ready at http://${probeHost}:$Port/ using $($bundleMatch.Groups[1].Value)"
        return
      }
    } catch {}
    Stop-DepoProcessTree $recordedPid $python 'http.server'
  }
  Remove-Item -LiteralPath $pidFile -Force
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  throw "Port $Port is already in use by process $($listener.OwningProcess). Stop that process or choose -Port <number>."
}

$process = Start-Process -FilePath $python `
  -ArgumentList @('-m', 'http.server', $Port, '--bind', $BindHost, '--directory', 'frontend\dist') `
  -WorkingDirectory $root -WindowStyle Hidden `
  -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
try {
Set-Content -LiteralPath $pidFile -Value $process.Id

$deadline = (Get-Date).AddSeconds(30)
do {
  if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    throw "DEPO frontend exited during startup. Check $stderr."
  }
  try {
    $response = Invoke-WebRequest -Uri "http://${probeHost}:$Port/" -UseBasicParsing -TimeoutSec 3
    if ($response.StatusCode -eq 200 -and $response.Content -match '<div id="root"' -and
        $response.Content.Contains($bundleMatch.Groups[1].Value) -and
        (Test-DepoListener $process.Id $python 'http.server' $Port $BindHost)) {
      Write-Host "DEPO frontend is ready at http://${probeHost}:$Port/ using $($bundleMatch.Groups[1].Value)"
      return
    }
  } catch {}
  Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

throw "DEPO frontend did not become ready within 30 seconds. Check $stderr."

} catch {
  $startupFailure = $_
  try { Stop-DepoProcessTree $process.Id $python 'http.server' }
  catch { throw "Frontend startup failed: $($startupFailure.Exception.Message). Cleanup failed: $($_.Exception.Message). PID tracking is retained." }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  throw $startupFailure
}

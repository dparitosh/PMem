param(
  [ValidateRange(1, 65535)][int]$Port = 3000,
  [string]$BindHost = '127.0.0.1'
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
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

if (Test-Path -LiteralPath $pidFile) {
  $recordedPid = [int](Get-Content -LiteralPath $pidFile)
  $existing = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
  if ($existing -and $existing.Path -and $existing.Path.ToLowerInvariant() -eq $python.ToLowerInvariant()) {
    try {
      $response = Invoke-WebRequest -Uri "http://${BindHost}:$Port/" -UseBasicParsing -TimeoutSec 5
      if ($response.StatusCode -eq 200) {
        Write-Host "DEPO frontend is already ready at http://${BindHost}:$Port/"
        return
      }
    } catch {}
    Stop-Process -Id $recordedPid -Force -ErrorAction SilentlyContinue
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
Set-Content -LiteralPath $pidFile -Value $process.Id

$deadline = (Get-Date).AddSeconds(30)
do {
  if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    throw "DEPO frontend exited during startup. Check $stderr."
  }
  try {
    $response = Invoke-WebRequest -Uri "http://${BindHost}:$Port/" -UseBasicParsing -TimeoutSec 3
    if ($response.StatusCode -eq 200 -and $response.Content -match '<div id="root"') {
      Write-Host "DEPO frontend is ready at http://${BindHost}:$Port/"
      return
    }
  } catch {}
  Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
throw "DEPO frontend did not become ready within 30 seconds. Check $stderr."

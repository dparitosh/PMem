<# .SYNOPSIS Offline regression checks for process ownership, cleanup and launcher ordering. #>
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'process-control.ps1')
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
function Assert-Startup($condition, $message) { if (-not $condition) { throw $message } }
$created = [datetime]'2026-10-04T00:00:00Z'
$script:mockProcesses = @(
  [pscustomobject]@{ ProcessId=101; ParentProcessId=0; CreationDate=$created; ExecutablePath='C:\project\python.exe'; CommandLine='python -m http.server 3000 --bind 127.0.0.1 --directory frontend\dist' },
  [pscustomobject]@{ ProcessId=202; ParentProcessId=101; CreationDate=$created.AddSeconds(1); ExecutablePath='C:\base\python.exe'; CommandLine='python -m http.server 3000' },
  [pscustomobject]@{ ProcessId=303; ParentProcessId=202; CreationDate=$created.AddSeconds(2); ExecutablePath='C:\base\python.exe'; CommandLine='child' },
  [pscustomobject]@{ ProcessId=404; ParentProcessId=0; CreationDate=$created; ExecutablePath='C:\other\python.exe'; CommandLine='python -m http.server 3000' }
)
$script:mockListeners = @([pscustomobject]@{LocalPort=3000; LocalAddress='127.0.0.1'; OwningProcess=202})
$script:killed = @()
function Get-CimInstance { param($ClassName,$Filter,$ErrorAction)
  if ($Filter -match 'ProcessId = (\d+)') { return $script:mockProcesses | Where-Object ProcessId -eq ([int]$matches[1]) }
  return $script:mockProcesses
}
function Get-NetTCPConnection { param($LocalPort,$State,$ErrorAction)
  if ($LocalPort) { return $script:mockListeners | Where-Object LocalPort -eq $LocalPort }
  return $script:mockListeners
}
function Stop-Process { param($Id,[switch]$Force,$ErrorAction)
  $script:killed += $Id
  $script:mockProcesses = @($script:mockProcesses | Where-Object ProcessId -ne $Id)
  $script:mockListeners = @($script:mockListeners | Where-Object OwningProcess -ne $Id)
}
Assert-Startup ((@(Get-DepoProcessTree 101 'C:\project\python.exe' 'http.server')).Count -eq 3) 'Verified descendant discovery failed'
Assert-Startup (Test-DepoListener 101 'C:\project\python.exe' 'http.server' 3000 '127.0.0.1') 'Owned descendant listener rejected'
Assert-Startup (-not (Test-DepoListener 101 'C:\project\python.exe' 'http.server' 3000 '10.0.2.16')) 'Wrong bind address accepted'
$script:mockListeners = @([pscustomobject]@{LocalPort=3000; LocalAddress='127.0.0.1'; OwningProcess=404})
Assert-Startup (-not (Test-DepoListener 101 'C:\project\python.exe' 'http.server' 3000 '127.0.0.1')) 'Unrelated port owner accepted'
$refused=$false
try { Stop-DepoProcessTree 404 'C:\project\python.exe' 'http.server' } catch { $refused=$true }
Assert-Startup $refused 'Unrelated process was not refused'
Stop-DepoProcessTree 101 'C:\project\python.exe' 'http.server'
Assert-Startup (($script:killed -join ',') -eq '303,202,101') 'Cleanup did not stop children before launcher'
Assert-Startup (@($script:mockProcesses | Where-Object ProcessId -eq 404).Count -eq 1) 'Unrelated process was removed'
Assert-Startup ((Get-DepoProbeHost '::') -eq '[::1]') 'IPv6 wildcard probe is incorrect'

$backend=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'start-depo-services.ps1') -Raw
$frontend=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'start-depo-frontend.ps1') -Raw
Assert-Startup ($backend.IndexOf("initialize-depo-schema.ps1") -lt $backend.IndexOf('$sparkOptions =')) 'Schema import still overrides runtime switches'
Assert-Startup ($backend.IndexOf('$startedServices +=') -lt $backend.IndexOf('Set-Content -LiteralPath $pidFile')) 'Rollback tracking occurs after PID-file writing'
Assert-Startup ($backend.IndexOf('if (-not $ready) { throw') -lt $backend.IndexOf('/auth/access')) 'Auth probe still masks readiness failure'
Assert-Startup (-not $frontend.Contains('LastWriteTimeUtc -gt')) 'Timestamp freshness still overrides build hashes'
Assert-Startup ($frontend.Contains("DEPO_FRONTEND_HOST") -and $frontend.Contains("DEPO_FRONTEND_PORT")) 'Central frontend binding is missing'
Assert-Startup ($frontend.Contains('$response.Content.Contains($bundleMatch.Groups[1].Value)')) 'Frontend reuse does not verify its bundle'
Assert-Startup ($frontend.IndexOf('try {', $frontend.IndexOf('$process = Start-Process')) -lt $frontend.IndexOf('Set-Content -LiteralPath $pidFile')) 'Frontend PID write is not protected by cleanup'
$savedFlags=@{}
foreach ($key in @('DEPO_SPARK_ENABLED','DEPO_SPARK_NEO4J_ENABLED','DEPO_SPARK_POSTGRES_ENABLED','DEPO_PIPELINE_SCHEDULER_ENABLED')) { $savedFlags[$key]=[Environment]::GetEnvironmentVariable($key,'Process'); [Environment]::SetEnvironmentVariable($key,'false','Process') }
try {
  $options=Resolve-DepoSparkOptions @{EnablePipelineScheduler=$true}
  Assert-Startup ($options.EnablePipelineScheduler -and -not $options.EnableSpark) 'Non-Spark scheduling remains blocked'
  $rejected=$false
  try { Resolve-DepoSparkOptions @{EnableNeo4jSparkConnector=$true} | Out-Null } catch { $rejected=$true }
  Assert-Startup $rejected 'Spark connector incorrectly allowed without Spark'
} finally { foreach ($key in $savedFlags.Keys) { [Environment]::SetEnvironmentVariable($key,$savedFlags[$key],'Process') } }
Write-Output 'PASS: verified descendants, listener owner/binding, cleanup order, unrelated-process protection, startup ordering, frontend receipts/binding and non-Spark scheduling.'

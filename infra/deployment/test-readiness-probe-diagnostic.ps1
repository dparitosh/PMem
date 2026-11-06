# Execute the actual readiness loop against offline process/network fixtures.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$source = Get-Content -LiteralPath (Join-Path $root 'infra/windows/start-depo-services.ps1') -Raw
$start = $source.IndexOf('  $deadline = (Get-Date).AddSeconds($ServiceStartupTimeoutSeconds)')
$end = $source.IndexOf("  if (`$env:AUTH_MODE -eq 'token')", $start)
if ($start -lt 0 -or $end -lt 0) { throw 'Readiness loop was not found' }
$loop = [scriptblock]::Create($source.Substring($start, $end-$start))
function Get-Content { param($LiteralPath) return '1234' }
function Get-Process { param($Id, $ErrorAction) return [pscustomobject]@{ Id=$Id } }
function Invoke-WebRequest { param($UseBasicParsing, $Headers, $TimeoutSec) return [pscustomobject]@{StatusCode=200; Headers=@{'Access-Control-Allow-Origin'='http://localhost:3000'}} }
function Test-DepoListener { return $fixtureState.listenerVerified }
function Start-Sleep { param($Milliseconds) $fixtureState.sleeps++ }
$fixtureState = @{listenerVerified=$false; sleeps=0}
$service = @{Name='schema-sets'; Port=8010; Module='backend.qif.app:app'}
$ServiceStartupTimeoutSeconds = 0
$stateDir = 'fixture-logs'; $python = 'fixture-python'; $BindHost = '127.0.0.1'
$peerHost = '127.0.0.1'; $corsProbeOrigin = 'http://localhost:3000'
$failed = $false
try { & $loop } catch {
  $failed = $true
  if ($_.Exception.Message -notmatch 'HTTP 200 readiness response received, but Windows listener ownership/binding' -or
      $_.Exception.Message -match 'No readiness response received') { throw 'Ownership mismatch was reported as missing readiness' }
}
if (-not $failed -or $fixtureState.sleeps -ne 1) { throw 'Unverified listener must fail and retry with a delay' }
$fixtureState.listenerVerified = $true
& $loop
Write-Host 'PASS: HTTP 200 with unverified ownership has an accurate diagnostic; verified ownership passes.'

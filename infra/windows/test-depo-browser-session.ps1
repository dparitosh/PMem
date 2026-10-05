<#
.SYNOPSIS
Checks central browser-session authentication across all running DEPO APIs.
.DESCRIPTION
Creates a temporary read-only session using ADMIN_API_KEY from the selected
environment file, validates every service, and disconnects in finally.
No uploads, approvals or data jobs run. No keys or session tokens are printed.
Use -Gateway to check configured APIM routing; otherwise checks local APIs.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local', [switch]$Gateway)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'process-control.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if ($values['AUTH_MODE'] -ne 'token' -or $values['DEPO_CREDENTIAL_STORE'] -ne 'postgres') {
  throw 'Browser sessions require AUTH_MODE=token and DEPO_CREDENTIAL_STORE=postgres in the selected file.'
}
if (-not $values['ADMIN_API_KEY']) { throw 'The selected file must contain the current ADMIN_API_KEY.' }
$manifest = Get-Content -LiteralPath (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
$bases = @{}
if ($Gateway) {
  if ($values['DEPO_ROUTING_MODE'] -ne 'gateway') { throw 'For -Gateway configure DEPO_ROUTING_MODE=gateway and DEPO_API_GATEWAY_URL.' }
  $routing = Resolve-DepoRouting $values
  $names = @{ 'schema-sets'='QIF'; ontology='ONTOLOGY'; agentic='AGENTIC'; graph='GRAPH'; ingestion='INGESTION'; oslc='OSLC'; catalog='CATALOG'; 'data-products'='DATA_PRODUCT'; ceim='CEIM'; 'data-pipeline'='DATA_PIPELINE' }
  foreach ($service in $manifest.services) { $bases[$service.id] = $routing["VITE_$($names[$service.id])_SERVICE_URL"] }
} else {
  $bindHost = if ($values['DEPO_SERVICE_HOST']) { $values['DEPO_SERVICE_HOST'] } else { '127.0.0.1' }
  $probeHost = Get-DepoProbeHost $bindHost
  foreach ($service in $manifest.services) { $bases[$service.id] = "http://${probeHost}:$($service.port)" }
}
$headers = @{}
if ($Gateway -and $values['DEPO_APIM_SUBSCRIPTION_KEY']) { $headers['Ocp-Apim-Subscription-Key'] = $values['DEPO_APIM_SUBSCRIPTION_KEY'] }
$url = $bases['ontology'] + '/auth/browser-session'
$session = $null
$failed = $false
try {
  $headers['X-API-Key'] = $values['ADMIN_API_KEY']
  try { $session = Invoke-RestMethod -Uri $url -Method Post -ContentType 'application/json' -Body '{"include_writes":false}' -Headers $headers -MaximumRedirection 0 -TimeoutSec 15 }
  catch { throw 'Central browser connection failed. Verify the current ADMIN_API_KEY, PostgreSQL credential store, matching service release, and gateway /auth/browser-session route. Response bodies and credentials are hidden.' }
  $headers.Remove('X-API-Key')
  if (-not $session.token -or $session.token -notlike 'depo_session_*' -or $session.profiles -notcontains 'GRAPH_READ_TOKEN' -or $session.profiles.Count -ne 1) {
    throw 'Service returned an invalid read-only browser session.'
  }
  $headers.Authorization = 'Bearer ' + $session.token
  foreach ($service in $manifest.services) {
    try {
      $access = Invoke-RestMethod -Uri ($bases[$service.id] + '/auth/access') -Headers $headers -MaximumRedirection 0 -TimeoutSec 15
      if ($access.status -ne 'authorized') { throw 'Not authorized' }
    } catch { throw "Browser session rejected by $($service.id). Check matching backend files, shared PostgreSQL database/schema and credential-store mode, and gateway Authorization forwarding. Credentials are hidden." }
    Write-Host "PASS: central browser session accepted by $($service.id)."
  }
} catch { $failed = $true; throw }
finally {
  $disconnectFailed = $false
  if ($session -and $session.token -like 'depo_session_*') {
    $headers.Remove('X-API-Key')
    $headers.Authorization = 'Bearer ' + $session.token
    try {
      $disconnected = Invoke-RestMethod -Uri $url -Method Delete -Headers $headers -MaximumRedirection 0 -TimeoutSec 15
      if ($disconnected.status -ne 'disconnected') { throw 'Invalid disconnect response' }
    }
    catch {
      $disconnectFailed = $true
      if ($failed) { Write-Warning 'Temporary session disconnect failed; it expires within fifteen minutes.' }
    }
  }
  $headers.Clear(); $values.Clear(); $session = $null
  if ($disconnectFailed -and -not $failed) { throw 'Read checks passed, but browser-session disconnect failed. Check DELETE /auth/browser-session routing. The temporary session expires within fifteen minutes.' }
}
Write-Host 'Central browser-session checks passed. In Admin, connect using the administrator key once; this diagnostic does not sign the browser in.'

[CmdletBinding()]
param([string]$EnvFile = '.env.local', [Alias('Synchronize')][switch]$ReplaceExisting)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if ($values['DEPO_CREDENTIAL_STORE'] -ne 'postgres') { throw 'Set DEPO_CREDENTIAL_STORE=postgres in the selected root .env.local before applying central credentials.' }
if ($values['AUTH_MODE'] -and $values['AUTH_MODE'] -ne 'token') { throw 'This script applies token-mode application keys. Configure AUTH_MODE=token; Entra identity uses its separate gateway configuration.' }
if (-not $values['DEPO_DATABASE_URL'] -and -not $values['DATABASE_URL']) { throw 'The selected file must configure DEPO_DATABASE_URL or DATABASE_URL.' }
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$python = Join-Path $root 'backend/.dt_venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Install backend dependencies first.' }
Push-Location $root
$previousOutputEncoding = $OutputEncoding
try {
  $OutputEncoding = New-Object Text.UTF8Encoding($false)
  $profileJson = & $python -m backend.depo_platform.credential_import --list-profiles
  if ($LASTEXITCODE -ne 0) { throw 'Could not load credential profiles from this release.' }
  $profiles = $profileJson | ConvertFrom-Json
  $selected = @{}
  foreach ($profile in $profiles) {
    foreach ($name in @($profile, "${profile}_ACTOR", "${profile}_EXPIRES_AT")) {
      if ($values.ContainsKey($name)) { $selected[$name] = $values[$name] }
    }
  }
  $suppliedProfiles = @($profiles | Where-Object { $selected.ContainsKey($_) -and -not [string]::IsNullOrWhiteSpace([string]$selected[$_]) })
  if ($suppliedProfiles.Count -eq 0) { throw 'The selected environment file contains no nonempty application API keys.' }
  $omittedProfiles = @($profiles | Where-Object { $_ -notin $suppliedProfiles })
  Write-Host ('Applying {0} application credential profiles from the selected environment file.' -f $suppliedProfiles.Count)
  if ($omittedProfiles.Count -gt 0) { Write-Host ('Not supplied; central values are preserved: {0}' -f ($omittedProfiles -join ', ')) }
  if ($ReplaceExisting) { Write-Host 'Synchronization mode: changed supplied keys and actor/expiry metadata update central profiles atomically; matching and omitted profiles are retained. Changed keys may require clients to reconnect.' }
  else { Write-Host 'Validation mode: creates missing profiles and verifies existing profiles. To deliberately make the selected file authoritative, rerun with -Synchronize.' }
  if ($values.ContainsKey('DEPO_TOKEN_EXPIRES_AT')) { $selected['DEPO_TOKEN_EXPIRES_AT'] = $values['DEPO_TOKEN_EXPIRES_AT'] }
  $arguments = @('-m', 'backend.depo_platform.credential_import')
  if ($ReplaceExisting) { $arguments += '--replace-existing' }
  # Secret values travel only over stdin, never command-line arguments or logs.
  $selected | ConvertTo-Json -Compress | & $python @arguments
  if ($LASTEXITCODE -ne 0) { throw 'Central credential import failed. No partial batch was applied; follow the structured action above.' }
  Write-Host 'All supplied application credentials were verified and applied atomically in PostgreSQL. Database passwords, Neo4j credentials, Ollama keys and APIM subscription keys remain server configuration; they are not imported as application profiles. This does not sign a browser in.'
  if ($values['DEPO_BROWSER_AUTH_MODE'] -eq 'local') { Write-Host 'Local browser access connects registered services automatically through the loopback frontend broker. No API-key copy/paste is required.' }
  else { Write-Host 'Manual or gateway browser access: connect through Admin after startup using the configured administrator identity.' }
  $diagnosticPath = Join-Path $root 'infra\windows\test-depo-browser-session.ps1'
  $diagnosticEnv = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
  Write-Host 'After services are running, verify browser-session access with this command (works from any directory):'
  Write-Host ('& ''{0}'' -EnvFile ''{1}''' -f $diagnosticPath.Replace("'", "''"), $diagnosticEnv.Replace("'", "''"))
} finally { $OutputEncoding = $previousOutputEncoding; Pop-Location }

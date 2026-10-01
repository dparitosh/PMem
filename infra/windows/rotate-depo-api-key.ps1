[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [Parameter(Mandatory=$true)][string]$Key,
  [ValidateRange(1,3650)][int]$ValidDays = 90,
  [Parameter(Mandatory=$true)][string]$Actor
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$values = Read-DepoEnvironment $root $EnvFile
if ($Key -notmatch '^[A-Z][A-Z0-9_]*(?:_TOKEN|_API_KEY)$' -or -not $values.ContainsKey($Key)) {
  throw 'Key must name an existing deployment TOKEN or API_KEY setting.'
}
if ($Actor -notmatch '^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$') { throw 'Actor must be a simple service/user identifier.' }
$path = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
$bytes = New-Object byte[] 48
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
$changes = @{}
$changes[$Key] = $secret
$changes["${Key}_EXPIRES_AT"] = [DateTimeOffset]::UtcNow.AddDays($ValidDays).ToString('o')
$changes["${Key}_ACTOR"] = $Actor
$lines = @(Get-Content -LiteralPath $path -Encoding UTF8)
foreach ($name in $changes.Keys) {
  $found = $false
  $lines = @($lines | ForEach-Object {
    if ($_ -match "^\s*$name\s*=") { $found = $true; "$name=$($changes[$name])" } else { $_ }
  })
  if (-not $found) { $lines += "$name=$($changes[$name])" }
}
# Update the existing protected file; never print the replacement secret.
[IO.File]::WriteAllLines($path, $lines, (New-Object Text.UTF8Encoding($false)))
Write-Host "Rotated $Key. Restart every DEPO service/worker using this file. Retrieve the replacement from the protected environment file; clear and re-enter browser credentials."

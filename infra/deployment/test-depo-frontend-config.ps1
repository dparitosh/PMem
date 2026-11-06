<# .SYNOPSIS Checks browser configuration before building the frontend. #>
param([string]$EnvFile = 'frontend\.env.local', [string]$RootEnvFile = '.env.local')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $root 'infra\windows\runtime-config.ps1')
$rootPath = if ([IO.Path]::IsPathRooted($RootEnvFile)) { $RootEnvFile } else { Join-Path $root $RootEnvFile }
$unifiedRouting = $false
if (Test-Path -LiteralPath $rootPath -PathType Leaf) {
  $rootValues = Read-DepoEnvironment $root $rootPath
  if ($rootValues['DEPO_ROUTING_MODE']) {
    Resolve-DepoRouting $rootValues | Out-Null
    $unifiedRouting = $true
  }
}
$browserPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path -LiteralPath $browserPath -PathType Leaf)) {
  if ($unifiedRouting) { Write-Host 'Frontend routing validated from root environment; no frontend environment file required.'; return }
  throw 'Missing frontend/.env.local. Run .\configure-depo.ps1 for a new installation, or copy frontend/.env.example to frontend/.env.local and configure it before rebuilding.'
}
$browser = Read-DepoEnvironment -Root $root -EnvFile $browserPath
foreach ($key in $browser.Keys) {
  if ($key -match '^(VITE_|REACT_APP_).*(TOKEN|PASSWORD|SECRET|API_KEY)') {
    throw "Do not compile credentials into browser configuration: $key. Enter API keys through the application authentication UI."
  }
  if ($browser[$key] -match '<[^>]+>') { throw "Complete the browser configuration placeholder: $key" }
  if ($key -match '^(VITE_|REACT_APP_).*_URL$' -and $browser[$key]) {
    $parsed = $null
    if (-not [Uri]::TryCreate($browser[$key], [UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -notin @('http','https') -or -not $parsed.Host -or $parsed.UserInfo -or $parsed.Fragment -or $parsed.Query) {
      throw "Invalid browser URL: $key. Use an absolute http:// or https:// URL without credentials, query or fragment."
    }
  }
}
if ($unifiedRouting) {
  Write-Host 'Frontend configuration passed. Root runtime routing overrides browser service URLs. Rebuild once after source updates; restart the frontend launcher after root routing changes.'
} else {
  Write-Host 'Frontend configuration passed. Rebuild after changing frontend/.env.local; restarting services alone does not change the browser bundle.'
}

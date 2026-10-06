<# .SYNOPSIS Creates the two customer-editable DEPO configuration files. #>
[CmdletBinding()]
param(
  [ValidateSet('token','entra','disabled')][string]$AuthMode = 'token',
  [string]$GatewayUrl = '',
  [switch]$ConfirmInsecureLocalDemo,
  [switch]$CheckExisting,
  [switch]$Force
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$server = Join-Path $root '.env.local'
$browser = Join-Path $root 'frontend\.env.local'
$serverGenerator = Join-Path $root 'infra\deployment\new-depo-deployment-config.ps1'
$browserTemplate = Join-Path $root 'frontend\.env.example'

if ($CheckExisting) {
  if ($Force) { throw '-CheckExisting is read-only and cannot be combined with -Force.' }
  . (Join-Path $root 'infra/windows/runtime-config.ps1')
  foreach ($entry in @(@{ Path=$server; Template=(Join-Path $root 'config/deployment.env.example'); Name='Server' }, @{ Path=$browser; Template=$browserTemplate; Name='Frontend' })) {
    $existing = Read-DepoEnvironment -Root $root -EnvFile $entry.Path
    $defaults = Read-DepoEnvironment -Root $root -EnvFile $entry.Template
    $missing = @($defaults.Keys | Where-Object {
      $name = $_
      $otherAlias = if ($name.StartsWith('REACT_APP_')) { 'VITE_' + $name.Substring(10) } elseif ($name.StartsWith('VITE_')) { 'REACT_APP_' + $name.Substring(5) } else { '' }
      -not $existing.ContainsKey($name) -and (-not $otherAlias -or -not $existing.ContainsKey($otherAlias)) -and
        -not ($name -eq 'OLLAMA_BASE_URL' -and $existing['OLLAMA_API_URL'])
    } | Sort-Object)
    if ($missing.Count) { Write-Warning ('{0} settings absent from the existing file: {1}. Review template defaults and add settings needed for your features; existing values were preserved.' -f $entry.Name, ($missing -join ', ')) }
    else { Write-Host ('{0}: current template settings are represented.' -f $entry.Name) }
    foreach ($name in @($existing.Keys | Where-Object { $_.StartsWith('VITE_') })) {
      $alias = 'REACT_APP_' + $name.Substring(5)
      if ($existing.ContainsKey($alias) -and $existing[$name] -and $existing[$alias] -and $existing[$name] -ne $existing[$alias]) { throw "Conflicting frontend aliases: $name and $alias. Keep one or make values identical. Values are hidden." }
    }
    if ($existing['OLLAMA_API_URL'] -and $existing['OLLAMA_BASE_URL']) { Write-Warning 'Both Ollama URL settings exist. Keep one or ensure they resolve to the same API root.' }
  }
  Write-Host 'Read-only configuration audit completed. No keys were generated, credentials synchronized or files modified. Missing settings require review; this is not runtime certification.'
  return
}

if ((Test-Path -LiteralPath $server) -and -not $Force) { throw "$server already exists. Edit it in place, or use -Force only after preserving customer secrets." }
if ((Test-Path -LiteralPath $browser) -and -not $Force) { throw "$browser already exists. Edit it in place, or use -Force only after preserving it." }
if ($GatewayUrl -and $GatewayUrl -notmatch '^https://') { throw 'GatewayUrl must be empty for direct local services or an https:// customer URL.' }

$parameters = @{ OutputPath = '.env.local'; AuthMode = $AuthMode }
if ($Force) { $parameters.Force = $true }
$global:LASTEXITCODE = 0
if ($ConfirmInsecureLocalDemo) { $parameters.ConfirmInsecureLocalDemo = $true }
& $serverGenerator @parameters
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Server configuration generation failed with exit code $LASTEXITCODE." }

Copy-Item -LiteralPath $browserTemplate -Destination $browser -Force
$content = Get-Content -LiteralPath $browser -Raw
$content = [regex]::Replace($content, '(?m)^VITE_API_GATEWAY_URL=.*$', "VITE_API_GATEWAY_URL=$GatewayUrl")
Set-Content -LiteralPath $browser -Value $content -NoNewline
Write-Host 'Created exactly two configuration files:' -ForegroundColor Green
Write-Host "  $server"
Write-Host "  $browser"
Write-Host 'Complete the server placeholders, then run .\diagnose-depo.ps1 -Phase Prerequisites.'

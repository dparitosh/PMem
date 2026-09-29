<# .SYNOPSIS Creates the two customer-editable DEPO configuration files. #>
[CmdletBinding()]
param(
  [ValidateSet('token','entra','disabled')][string]$AuthMode = 'token',
  [string]$GatewayUrl = '',
  [switch]$ConfirmInsecureLocalDemo,
  [switch]$Force
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$server = Join-Path $root '.env.local'
$browser = Join-Path $root 'frontend\.env.local'
$serverGenerator = Join-Path $root 'infra\deployment\new-depo-deployment-config.ps1'
$browserTemplate = Join-Path $root 'frontend\.env.example'

if ((Test-Path -LiteralPath $server) -and -not $Force) { throw "$server already exists. Edit it in place, or use -Force only after preserving customer secrets." }
if ((Test-Path -LiteralPath $browser) -and -not $Force) { throw "$browser already exists. Edit it in place, or use -Force only after preserving it." }
if ($GatewayUrl -and $GatewayUrl -notmatch '^https://') { throw 'GatewayUrl must be empty for direct local services or an https:// customer URL.' }

$parameters = @{ OutputPath = '.env.local'; AuthMode = $AuthMode }
if ($Force) { $parameters.Force = $true }
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

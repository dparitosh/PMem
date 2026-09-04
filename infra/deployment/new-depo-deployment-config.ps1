param(
  [string]$OutputPath = ".env.deployment",
  [ValidateSet("token", "entra", "disabled")][string]$AuthMode = "token",
  [switch]$ConfirmInsecureLocalDemo,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$template = Join-Path $root ".env.postgres.example"
$target = if ([System.IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $root $OutputPath }
if (-not (Test-Path $template)) { throw "Missing deployment configuration template: $template" }
if ((Test-Path $target) -and -not $Force) { throw "Refusing to overwrite existing configuration: $target. Use -Force only after preserving customer secrets." }
Copy-Item -LiteralPath $template -Destination $target -Force
if ($AuthMode -eq "disabled" -and -not $ConfirmInsecureLocalDemo) {
  Remove-Item -LiteralPath $target -Force
  throw "Disabled authentication requires -ConfirmInsecureLocalDemo and is restricted to loopback-only local demonstrations."
}
function New-DeploymentSecret {
  $bytes = New-Object byte[] 48
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
$content = Get-Content -LiteralPath $target -Raw
$content = $content -replace '(?m)^AUTH_MODE=.*$', "AUTH_MODE=$AuthMode"
$content = [regex]::Replace($content, '(?m)^(?<key>[A-Z0-9_]*TOKEN)=<long-random-secret>$', {
  param($match)
  "$($match.Groups['key'].Value)=$(New-DeploymentSecret)"
})
if ($AuthMode -eq "disabled") {
  $content = $content -replace '(?m)^DEPO_ALLOW_INSECURE_LOCAL_AUTH=.*$', 'DEPO_ALLOW_INSECURE_LOCAL_AUTH=true'
  $content = $content -replace '(?m)^DEPO_SERVICE_HOST=.*$', 'DEPO_SERVICE_HOST=127.0.0.1'
  $content = $content -replace '(?m)^ALLOWED_ORIGINS=.*$', 'ALLOWED_ORIGINS=http://127.0.0.1:3000'
}
Set-Content -LiteralPath $target -Value $content -NoNewline
Write-Host "Created $target with generated bootstrap secrets. Set database and graph credentials before starting services. Secrets were not printed."

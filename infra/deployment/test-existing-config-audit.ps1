# Isolated test: never opens customer .env.local files.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$parent = Join-Path $root '.release-test-tmp'
$fixture = Join-Path $parent ('audit-' + [guid]::NewGuid().ToString('N'))
$previousWarnings = $WarningPreference
try {
  $WarningPreference = 'SilentlyContinue'
  New-Item -ItemType Directory -Force -Path (Join-Path $fixture 'infra/windows'), (Join-Path $fixture 'frontend'), (Join-Path $fixture 'config') | Out-Null
  Copy-Item -LiteralPath (Join-Path $root 'configure-depo.ps1') -Destination $fixture
  Copy-Item -LiteralPath (Join-Path $root 'infra/windows/runtime-config.ps1') -Destination (Join-Path $fixture 'infra/windows/runtime-config.ps1')
  Copy-Item -LiteralPath (Join-Path $root 'config/deployment.env.example') -Destination (Join-Path $fixture 'config/deployment.env.example')
  Copy-Item -LiteralPath (Join-Path $root 'frontend/.env.example') -Destination (Join-Path $fixture 'frontend/.env.example')
  $server = Join-Path $fixture '.env.local'
  $browser = Join-Path $fixture 'frontend/.env.local'
  Set-Content -LiteralPath $server -Value "AUTH_MODE=token`nOLLAMA_API_URL=http://fixture/ollama"
  Set-Content -LiteralPath $browser -Value 'VITE_AGENTIC_SERVICE_URL=http://fixture:8012'
  $serverHash = (Get-FileHash -LiteralPath $server).Hash
  $browserHash = (Get-FileHash -LiteralPath $browser).Hash
  & (Join-Path $fixture 'configure-depo.ps1') -CheckExisting
  if ((Get-FileHash -LiteralPath $server).Hash -ne $serverHash -or (Get-FileHash -LiteralPath $browser).Hash -ne $browserHash) { throw 'Read-only audit modified configuration.' }
  Add-Content -LiteralPath $browser -Value 'REACT_APP_AGENTIC_SERVICE_URL=http://conflicting:8012'
  $rejected = $false
  try { & (Join-Path $fixture 'configure-depo.ps1') -CheckExisting } catch { if ($_.Exception.Message -notlike '*Conflicting frontend aliases*') { throw }; $rejected = $true }
  if (-not $rejected) { throw 'Conflicting browser aliases were accepted.' }
  Write-Output 'PASS: existing-configuration audit preserves both files and rejects conflicting aliases.'
} finally {
  $WarningPreference = $previousWarnings
  if (Test-Path -LiteralPath $fixture) {
    $resolved = (Resolve-Path -LiteralPath $fixture).Path
    if (-not $resolved.StartsWith([IO.Path]::GetFullPath($parent) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup target.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}

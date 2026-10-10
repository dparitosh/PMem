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
  & (Join-Path $fixture 'configure-depo.ps1') -UpdateMissing
  . (Join-Path $fixture 'infra/windows/runtime-config.ps1')
  $updatedServer = Read-DepoEnvironment -Root $fixture -EnvFile $server
  $updatedBrowser = Read-DepoEnvironment -Root $fixture -EnvFile $browser
  if ($updatedServer['AUTH_MODE'] -ne 'token' -or $updatedServer['OLLAMA_API_URL'] -ne 'http://fixture/ollama') { throw 'Missing-setting update replaced existing server values.' }
  if ($updatedServer.ContainsKey('OLLAMA_BASE_URL')) { throw 'Missing-setting update introduced a conflicting Ollama alias.' }
  if ($updatedBrowser['VITE_AGENTIC_SERVICE_URL'] -ne 'http://fixture:8012') { throw 'Missing-setting update replaced the existing browser service URL.' }
  if (-not $updatedServer.ContainsKey('DEPO_DATABASE_URL') -or -not $updatedBrowser.ContainsKey('VITE_API_GATEWAY_URL')) { throw 'Missing template fields were not appended.' }
  $serverHash = (Get-FileHash -LiteralPath $server).Hash
  $browserHash = (Get-FileHash -LiteralPath $browser).Hash
  & (Join-Path $fixture 'configure-depo.ps1') -UpdateMissing
  if ((Get-FileHash -LiteralPath $server).Hash -ne $serverHash -or (Get-FileHash -LiteralPath $browser).Hash -ne $browserHash) { throw 'Repeated update changed complete configuration.' }
  $savedBrowser = [IO.File]::ReadAllText($browser)
  Remove-Item -LiteralPath $browser
  & (Join-Path $fixture 'configure-depo.ps1') -UpdateMissing
  $newBrowser = Read-DepoEnvironment -Root $fixture -EnvFile $browser
  if (-not $newBrowser.ContainsKey('VITE_API_GATEWAY_URL')) { throw 'Missing frontend configuration was not created.' }
  [IO.File]::WriteAllText($browser, $savedBrowser)
  Add-Content -LiteralPath $browser -Value 'REACT_APP_AGENTIC_SERVICE_URL=http://conflicting:8012'
  $rejected = $false
  try { & (Join-Path $fixture 'configure-depo.ps1') -CheckExisting } catch { if ($_.Exception.Message -notlike '*Conflicting frontend aliases*') { throw }; $rejected = $true }
  if (-not $rejected) { throw 'Conflicting browser aliases were accepted.' }
  Write-Output 'PASS: existing-configuration audit and missing-setting update preserve both files, retain aliases, are idempotent and reject conflicting aliases.'
} finally {
  $WarningPreference = $previousWarnings
  if (Test-Path -LiteralPath $fixture) {
    $resolved = (Resolve-Path -LiteralPath $fixture).Path
    if (-not $resolved.StartsWith([IO.Path]::GetFullPath($parent) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup target.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}

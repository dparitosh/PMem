# Offline validation only: no customer credentials or running services.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$testParent = Join-Path $root '.release-test-tmp'
New-Item -ItemType Directory -Force -Path $testParent | Out-Null
$testFile = Join-Path $testParent ('api-key-' + [guid]::NewGuid().ToString('N') + '.env.local')
try {
  $content = Get-Content -LiteralPath (Join-Path $root 'config/deployment.env.example') -Raw
  $content = [regex]::Replace($content, '(?m)^([A-Z0-9_]*TOKEN)=<[^>]+>', '$1=' + ('a' * 64))
  $replacements = @{
    DEPO_DATABASE_URL='postgresql://app:fixture@db.example/depo'; NEO4J_URI='neo4j+s://graph.example'
    NEO4J_PASS='fixture'; ALLOWED_ORIGINS='https://app.example'; OSLC_BASE_URL='https://api.example'
  }
  foreach ($key in $replacements.Keys) { $content = $content -replace "(?m)^$key=.*$", "$key=$($replacements[$key])" }
  Set-Content -LiteralPath $testFile -Value $content
  & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $testFile -Profile Production -SkipEndpointChecks
  Set-Content -LiteralPath $testFile -Value ($content -replace '(?m)^AGENTIC_APPROVAL_TOKEN=.*$', 'AGENTIC_APPROVAL_TOKEN=short')
  $rejected = $false
  try { & (Join-Path $PSScriptRoot 'test-depo-deployment.ps1') -EnvFile $testFile -Profile Production -SkipEndpointChecks }
  catch { if ($_.Exception.Message -notlike '*at least 32 characters*') { throw }; $rejected = $true }
  if (-not $rejected) { throw 'Weak production key accepted.' }
  Write-Output 'PASS: API-key production profile without Entra, and weak-key rejection.'
} finally {
  if (Test-Path -LiteralPath $testFile) { Remove-Item -LiteralPath $testFile }
}

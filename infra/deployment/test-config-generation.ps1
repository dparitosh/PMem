# Isolated configuration contract test. Never reads or changes customer settings.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$testParent = Join-Path $root '.release-test-tmp'
$testRoot = Join-Path $testParent ('config-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $testRoot 'infra/deployment'), (Join-Path $testRoot 'config') | Out-Null
try {
  Copy-Item -LiteralPath (Join-Path $root 'config/deployment.env.example') -Destination (Join-Path $testRoot 'config/deployment.env.example')
  foreach ($name in @('new-depo-deployment-config.ps1', 'set-depo-admin-key.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $testRoot 'infra/deployment')
  }
  $generator = Join-Path $testRoot 'infra/deployment/new-depo-deployment-config.ps1'
  & $generator
  $config = Join-Path $testRoot '.env.local'
  if (-not (Test-Path -LiteralPath $config)) { throw 'Default .env.local was not generated.' }
  $content = [IO.File]::ReadAllText($config)
  $secrets = @([regex]::Matches($content, '(?m)^(?:[A-Z0-9_]*TOKEN|ADMIN_API_KEY)=(.+)$') | ForEach-Object { $_.Groups[1].Value.Trim() } | Where-Object { $_ })
  if ($secrets.Count -lt 17 -or @($secrets | Select-Object -Unique).Count -ne $secrets.Count -or @($secrets | Where-Object { $_ -notmatch '^[A-Za-z0-9_-]{64}$' }).Count) {
    throw 'Expected distinct 384-bit bootstrap tokens and admin key.'
  }
  $before = (Get-FileHash -LiteralPath $config).Hash
  $rejected = $false
  try { & $generator } catch {
    if ($_.Exception.Message -notlike '*Refusing to overwrite*') { throw }
    $rejected = $true
  }
  if (-not $rejected -or (Get-FileHash -LiteralPath $config).Hash -ne $before) { throw 'Overwrite protection failed.' }
  Write-Output 'PASS: default configuration path, distinct secrets, admin key and overwrite protection.'
} finally {
  $resolved = (Resolve-Path -LiteralPath $testRoot).Path
  if (-not $resolved.StartsWith([IO.Path]::GetFullPath($testParent) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing cleanup outside the isolated test directory.'
  }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

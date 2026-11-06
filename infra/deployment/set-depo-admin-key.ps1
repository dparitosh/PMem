param(
  [string]$EnvFile = '.env.local',
  [switch]$Rotate
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$target = if ([IO.Path]::IsPathRooted($EnvFile)) { [IO.Path]::GetFullPath($EnvFile) } else { [IO.Path]::GetFullPath((Join-Path $root $EnvFile)) }
if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Configuration must be inside the deployment directory.'
}
if ([IO.Path]::GetFileName($target) -ne '.env.local') {
  throw 'Use an existing ignored .env.local file; do not store credentials in tracked templates.'
}
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'Create .env.local before configuring the admin key.' }
$content = [IO.File]::ReadAllText($target)
$pattern = '(?m)^\s*ADMIN_API_KEY\s*=.*$'
$matchesFound = [regex]::Matches($content, $pattern)
if ($matchesFound.Count -gt 1) { throw 'Duplicate ADMIN_API_KEY entries: resolve them before generating a key.' }
if ($matchesFound.Count -eq 1 -and -not $Rotate) {
  if (($matchesFound[0].Value -split '=', 2)[1].Trim()) {
    Write-Host 'Existing admin key preserved. Use -Rotate for deliberate rotation.'
    return
  }
}
$bytes = New-Object byte[] 48
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$entry = 'ADMIN_API_KEY=' + [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
if ($matchesFound.Count) { $content = [regex]::Replace($content, $pattern, $entry) }
else { $content = $content.TrimEnd() + "`r`n" + $entry + "`r`n" }
[IO.File]::WriteAllText($target, $content, (New-Object Text.UTF8Encoding($false)))
Write-Host 'Admin key configured (384 bits). Value not printed. Restart backend services with this environment file.'

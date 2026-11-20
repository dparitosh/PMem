<# .SYNOPSIS Reports or removes exact retired vendor files; preserves customized files. #>
[CmdletBinding()]
param(
  [string]$Root = (Join-Path $PSScriptRoot '../..'),
  [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$resolvedRoot = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\','/')
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot 'install-depo.ps1') -PathType Leaf)) {
  throw 'Retired-file cleanup requires the application release root.'
}
$manifest = Get-Content -LiteralPath (Join-Path $resolvedRoot 'infra/deployment/retired-files.json') -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1) { throw 'Unsupported retired-file manifest.' }
function Get-RetiredFileHash([string]$Path) {
  $algorithm = [Security.Cryptography.SHA256]::Create()
  $stream = [IO.File]::OpenRead($Path)
  try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
  finally { $stream.Dispose(); $algorithm.Dispose() }
}
$plan = @()
foreach ($entry in $manifest.files) {
  $relative = [string]$entry.path
  if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[/\\])\.\.([/\\]|$)' -or $relative.Contains(':')) {
    throw 'Unsafe retired-file path in release manifest.'
  }
  $target = [IO.Path]::GetFullPath((Join-Path $resolvedRoot $relative))
  if (-not $target.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Retired-file target is outside the release root.'
  }
  if (-not (Test-Path -LiteralPath $target)) { continue }
  $item = Get-Item -LiteralPath $target -Force
  if ($item.PSIsContainer) { throw 'Retired-file cleanup refuses directories.' }
  $parent = $item
  while ($parent -and $parent.FullName -ne $resolvedRoot) {
    if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Retired-file cleanup refuses linked paths.' }
    $parent = if ($parent -is [IO.DirectoryInfo]) { $parent.Parent } else { $parent.Directory }
  }
  $hash = (Get-RetiredFileHash $target)
  if (@($entry.sha256) -notcontains $hash) {
    Write-Warning "Preserved customized or unknown retired file: $relative. Review it before using old commands."
    continue
  }
  $plan += [pscustomobject]@{path=$relative; target=$target; sha256=$hash}
}
foreach ($entry in $plan) {
  if ($CheckOnly) { Write-Host "Retired vendor file would be removed after shutdown: $($entry.path)"; continue }
  if ((Get-RetiredFileHash $entry.target) -ne $entry.sha256) {
    throw 'A retired file changed after planning; cleanup stopped.'
  }
  Remove-Item -LiteralPath $entry.target -Force
  Write-Host "Removed retired vendor file: $($entry.path)"
}
[pscustomobject]@{status='ok'; check_only=[bool]$CheckOnly; matching_files=$plan.Count} | ConvertTo-Json -Compress

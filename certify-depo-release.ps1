<# .SYNOPSIS Runs production diagnostics and records the required customer acceptance evidence. #>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [string]$Python = 'py',
  [Parameter(Mandatory=$true)][string]$SupervisorEvidencePath,
  [Parameter(Mandatory=$true)][string]$BackupRestoreEvidencePath,
  [Parameter(Mandatory=$true)][string]$BrowserAcceptanceEvidencePath,
  [Parameter(Mandatory=$true)][string]$RollbackEvidencePath,
  [string]$OutputDirectory = 'release-evidence'
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
function Resolve-Evidence([string]$Path, [string]$Name) {
  $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $root $Path }
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Missing $Name evidence file: $candidate" }
  $item = Get-Item -LiteralPath $candidate
  if ($item.Length -eq 0) { throw "$Name evidence file is empty: $candidate" }
  return $item
}
$evidence = [ordered]@{
  supervisor = Resolve-Evidence $SupervisorEvidencePath 'process supervision and reboot recovery'
  backup_restore = Resolve-Evidence $BackupRestoreEvidencePath 'backup and restore drill'
  browser_acceptance = Resolve-Evidence $BrowserAcceptanceEvidencePath 'browser acceptance'
  rollback = Resolve-Evidence $RollbackEvidencePath 'rollback rehearsal'
}

& (Join-Path $root 'diagnose-depo.ps1') -Phase All -EnvFile $EnvFile -Profile Production -Python $Python
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Production diagnostics failed with exit code $LASTEXITCODE." }

$output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $root $OutputDirectory }
New-Item -ItemType Directory -Force -Path $output | Out-Null
$trackedReleaseFiles = @(
  'INSTALLATION.md', 'backend/requirements-lock.txt', 'frontend/package-lock.json',
  'infra/deployment/services.json',
  'infra/deployment/neo4j-publication-index.cypher'
)
$trackedReleaseFiles += @(Get-ChildItem -LiteralPath (Join-Path $root 'infra\postgres\migrations') -Filter '*.sql' -File |
  Sort-Object Name | ForEach-Object { 'infra/postgres/migrations/' + $_.Name })
$hashes = foreach ($relative in $trackedReleaseFiles) {
  $path = Join-Path $root $relative
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing release artifact: $relative" }
  [ordered]@{ path = $relative; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() }
}
$evidenceHashes = foreach ($entry in $evidence.GetEnumerator()) {
  [ordered]@{ type = $entry.Key; path = $entry.Value.FullName; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Value.FullName).Hash.ToLowerInvariant() }
}
$commit = (& git -C $root rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $commit = 'unavailable' }
$record = [ordered]@{
  generated_utc = [DateTime]::UtcNow.ToString('o')
  profile = 'Production'
  git_commit = $commit
  diagnostics = 'passed'
  release_artifacts = @($hashes)
  acceptance_evidence = @($evidenceHashes)
}
$destination = Join-Path $output ('depo-release-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $destination -Encoding utf8
Write-Host "Production release evidence created: $destination" -ForegroundColor Green

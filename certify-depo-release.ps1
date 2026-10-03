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
$releaseCommit = (& git -C $root rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $releaseCommit) { throw 'A Git release commit is required for certification.' }
$releaseCommit = $releaseCommit.Trim()
$certificationSettings = $null
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$certificationSettings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
$deploymentId = [string]$certificationSettings['DEPO_DEPLOYMENT_ID']
if (-not $deploymentId -or $deploymentId -match '[<>\s]') { throw 'Set a completed DEPO_DEPLOYMENT_ID in the selected root environment for release evidence.' }
function Resolve-Evidence([string]$Path, [string]$Name) {
  $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $root $Path }
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Missing $Name evidence file: $candidate" }
  $item = Get-Item -LiteralPath $candidate
  if ($item.Length -eq 0) { throw "$Name evidence file is empty: $candidate" }
  try { $acceptance = Get-Content -LiteralPath $candidate -Raw | ConvertFrom-Json } catch { throw "$Name evidence must be a structured JSON acceptance record." }
  if ($acceptance.contract_version -ne 'depo-acceptance-v1' -or $acceptance.status -ne 'passed' -or
      $acceptance.git_commit -ne $releaseCommit -or $acceptance.deployment_id -ne $deploymentId -or
      $acceptance.evidence_type -ne $Name -or -not $acceptance.reviewer -or -not $acceptance.executed_at -or
      -not $acceptance.checks -or @($acceptance.checks | Where-Object { $_.status -ne 'passed' -or -not $_.name }).Count) {
    throw "$Name evidence must record reviewed passing checks for this commit, deployment and evidence type."
  }
  $timestamp = if ($acceptance.executed_at -is [DateTime]) { $acceptance.executed_at.ToString('o') } else { [string]$acceptance.executed_at }
  $executed = [DateTimeOffset]::MinValue
  if (-not [DateTimeOffset]::TryParse($timestamp, [ref]$executed) -or
      $timestamp -notmatch '(Z|[+-]\d{2}:\d{2})$' -or $executed -gt [DateTimeOffset]::UtcNow) {
    throw "$Name evidence requires a valid non-future executed_at timestamp with timezone."
  }
  return $item
}
$evidence = [ordered]@{
  supervisor = Resolve-Evidence $SupervisorEvidencePath 'supervisor'
  backup_restore = Resolve-Evidence $BackupRestoreEvidencePath 'backup_restore'
  browser_acceptance = Resolve-Evidence $BrowserAcceptanceEvidencePath 'browser_acceptance'
  rollback = Resolve-Evidence $RollbackEvidencePath 'rollback'
}

$global:LASTEXITCODE = 0
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

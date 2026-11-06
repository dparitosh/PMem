$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$fixtureRoot = Join-Path $root ('.release-test-tmp/blockers-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
try {
  $fixture = Join-Path $fixtureRoot 'env'
  Set-Content -LiteralPath $fixture -Value @('DEPO_POSTGRES_MODE=external')
  $previousSpark = $env:DEPO_SPARK_ENABLED
  $env:DEPO_SPARK_ENABLED = 'fixture-preserved'
  & (Join-Path $root 'infra/windows/start-depo-postgres.ps1') -EnvFile $fixture
  if ($env:DEPO_SPARK_ENABLED -ne 'fixture-preserved') { throw 'Postgres helper modified unrelated runtime settings.' }
  $env:DEPO_SPARK_ENABLED = $previousSpark
  $started = $false
  function Get-Service { param($Name, $ErrorAction) return [pscustomobject]@{ Name=$Name; Status='Running' } }
  function Start-Service { param($Name) throw 'Running service should not be started again.' }
  Set-Content -LiteralPath $fixture -Value @('DEPO_POSTGRES_MODE=service','DEPO_POSTGRES_SERVICE_NAME=fixture-postgres')
  & (Join-Path $root 'infra/windows/start-depo-postgres.ps1') -EnvFile $fixture
  $parseTokens=$null; $parseErrors=$null
  $tree=[Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'certify-depo-release.ps1'),[ref]$parseTokens,[ref]$parseErrors)
  if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
  $functionNode=$tree.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Resolve-Evidence'},$true)
  Invoke-Expression $functionNode.Extent.Text
  $releaseCommit='fixture-commit'; $deploymentId='fixture-deployment'
  $evidencePath=Join-Path $fixtureRoot 'evidence.json'
  $record=@{contract_version='depo-acceptance-v1';status='passed';git_commit=$releaseCommit;deployment_id=$deploymentId;evidence_type='browser_acceptance';reviewer='reviewer';executed_at='2026-01-01T00:00:00Z';checks=@(@{name='fixture check';status='passed'})}
  $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidencePath
  Resolve-Evidence $evidencePath 'browser_acceptance' | Out-Null
  foreach ($badCase in @('failed','wrong-commit','failed-check')) {
    $candidate=$record.Clone()
    if ($badCase -eq 'failed') { $candidate.status='failed' }
    if ($badCase -eq 'wrong-commit') { $candidate.git_commit='other' }
    if ($badCase -eq 'failed-check') { $candidate.checks=@(@{name='test';status='failed'}) }
    $candidate | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidencePath
    $rejected=$false
    try { Resolve-Evidence $evidencePath 'browser_acceptance' | Out-Null } catch { $rejected=$true }
    if (-not $rejected) { throw "Invalid evidence accepted: $badCase" }
  }
  Write-Host 'PASS: external/local PostgreSQL helper and release evidence acceptance/rejection (simulated service).'
} finally {
  if ($fixtureRoot.StartsWith((Join-Path $root '.release-test-tmp') + [IO.Path]::DirectorySeparatorChar)) {
    Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
  }
}

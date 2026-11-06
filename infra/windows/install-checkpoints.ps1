# Dependency receipts contain hashes only; never persist environment values or keys.
function Get-DepoInstallFingerprint([string[]]$Files, [string[]]$Values) {
  $parts = @($Values)
  foreach ($file in $Files) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing installation input: $file" }
    $stream=[IO.File]::OpenRead($file)
    $hasher=[Security.Cryptography.SHA256]::Create()
    try { $parts += ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose(); $hasher.Dispose() }
  }
  $sha = [Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))))).Replace('-', '') }
  finally { $sha.Dispose() }
}
function Invoke-DepoDependencyStage {
  param([string]$Root, [string]$Name, [string]$Fingerprint, [scriptblock]$Action, [scriptblock]$Probe, [switch]$Force)
  if ($Name -notmatch '^[a-z0-9-]+$') { throw 'Invalid dependency stage name' }
  $folder = Join-Path $Root 'logs/installation/checkpoints'
  New-Item -ItemType Directory -Path $folder -Force | Out-Null
  $receipt = Join-Path $folder ($Name + '.json')
  if (-not $Force -and (Test-Path -LiteralPath $receipt)) {
    try {
      $saved = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
      $proof = & $Probe
      if ($saved.fingerprint -eq $Fingerprint -and $proof -and $saved.proof -eq $proof) {
        Write-Host "RESUME: $Name dependencies verified; installation skipped."
        $global:LASTEXITCODE = 0
        return
      }
    } catch { Write-Verbose "Dependency receipt unavailable; reinstalling $Name." }
  }
  if (Test-Path -LiteralPath $receipt) { Remove-Item -LiteralPath $receipt -Force }
  $global:LASTEXITCODE = 0
  & $Action
  if ($LASTEXITCODE -ne 0) { throw "Dependency stage failed: $Name. Rerun the same installer to resume." }
  $proof = & $Probe
  if (-not $proof) { throw "Dependency verification failed: $Name. No completion checkpoint saved." }
  $temporary = $receipt + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
  try {
    @{fingerprint=$Fingerprint; proof=$proof; completedUtc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $receipt -Force
  } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
  $global:LASTEXITCODE = 0
}

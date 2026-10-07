# Offline regression checks; no network requests or customer credentials.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$diagnostic = Join-Path $root 'infra/windows/test-depo-ollama.ps1'
$fixture = New-TemporaryFile
$fixtureState = @{ calls = (New-Object 'System.Collections.Generic.List[object]'); missingTags = $false; malformedModels = $false; arrayTags = $false; arrayGeneration = $false }
function Invoke-WebRequest {
  param($Uri, $Method, $Headers, $TimeoutSec, $UseBasicParsing, $MaximumRedirection,
        $ErrorAction, $ContentType, $Body)
  $fixtureState.calls.Add(@{ uri=$Uri; method=$Method; body=$Body })
  if ($Headers['api-key'] -ne 'fixture-secret-never-print') { throw 'Unexpected fixture header' }
  if ($Method -eq 'GET') {
    if ($fixtureState.missingTags) {
      $failure = New-Object System.Exception 'fixture-secret-never-print'
      Add-Member -InputObject $failure -NotePropertyName Response -NotePropertyValue ([pscustomobject]@{StatusCode=404})
      throw $failure
    }
    $content = if ($fixtureState.malformedModels) { '{"models":[{"name":42}]}' } else { '{"models":[{"name":"llama3:latest"}]}' }
    if ($fixtureState.arrayTags) { $content = '[' + $content + ']' }
    return [pscustomobject]@{ StatusCode=200; Content=$content }
  }
  $content = '{"response":"OK","done":true}'
  if ($fixtureState.arrayGeneration) { $content = '[' + $content + ']' }
  return [pscustomobject]@{ StatusCode=200; Content=$content }
}
try {
  Set-Content -LiteralPath $fixture.FullName -Encoding UTF8 -Value @'
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_API_URL=http://127.0.0.1:11434/api/generate
OLLAMA_API_KEY=fixture-secret-never-print
OLLAMA_API_KEY_HEADER=" api-key "
LLM_MODEL_NAME=llama3:latest
'@
  $script:output = ''
  try { & $diagnostic -EnvFile $fixture.FullName -ProbeGeneration 6>&1 | ForEach-Object { $script:output += [string]$_ + "`n" } } catch { throw }
  $output = $script:output
  if ($output.Contains('fixture-secret-never-print')) { throw 'Credential leaked in output' }
  if ($fixtureState.calls.Count -ne 2 -or $fixtureState.calls[0].uri -ne 'http://127.0.0.1:11434/api/tags' -or
      $fixtureState.calls[1].uri -ne 'http://127.0.0.1:11434/api/generate') { throw 'Incorrect native routes' }
  $sentBody = [Text.Encoding]::UTF8.GetString($fixtureState.calls[1].body) | ConvertFrom-Json
  if ($sentBody.prompt -ne 'Reply with OK.' -or $sentBody.stream -ne $false) { throw 'Expected bounded native generate prompt' }
  $fixtureState.calls.Clear(); $fixtureState.missingTags = $true
  $script:captured = ''
  $failed = $false
  try { & $diagnostic -EnvFile $fixture.FullName -ProbeGeneration 6>&1 | ForEach-Object { $script:captured += [string]$_ + "`n" } }
  catch { $failed = $true }
  if (-not $failed -or $fixtureState.calls.Count -ne 2 -or $script:captured -notmatch 'HTTP 404') { throw 'Discovery 404 must remain a failure while generation is tested separately' }
  if ($script:captured.Contains('fixture-secret-never-print')) { throw 'Upstream secret leaked in failure output' }
  $fixtureState.missingTags = $false
  foreach ($arrayCase in @('arrayTags', 'arrayGeneration')) {
    $fixtureState.calls.Clear(); $fixtureState[$arrayCase] = $true
    $failed = $false; $script:captured = ''
    try { & $diagnostic -EnvFile $fixture.FullName -ProbeGeneration 6>&1 | ForEach-Object { $script:captured += [string]$_ + "`n" } }
    catch { $failed = $true }
    if (-not $failed -or $script:captured -notmatch 'Expected a native Ollama JSON object' -or $fixtureState.calls.Count -ne 2) {
      throw "Array-wrapped response must fail: $arrayCase"
    }
    $fixtureState[$arrayCase] = $false
  }
  $fixtureState.calls.Clear(); $fixtureState.missingTags = $false; $fixtureState.malformedModels = $true
  $failed = $false; $script:captured = ''
  try { & $diagnostic -EnvFile $fixture.FullName 6>&1 | ForEach-Object { $script:captured += [string]$_ + "`n" } } catch { $failed = $true }
  if (-not $failed -or $script:captured -notmatch 'invalid model entries') { throw 'Malformed model entries must not be reported as missing models' }
  Set-Content -LiteralPath $fixture.FullName -Value 'OLLAMA_BASE_URL=http://127.0.0.1:11434/Ollama', 'OLLAMA_API_URL=http://127.0.0.1:11434/ollama/api/generate'
  $fixtureState.calls.Clear(); $failed = $false
  try { & $diagnostic -EnvFile $fixture.FullName 6>&1 | Out-Null } catch { $failed = $true }
  if (-not $failed -or $fixtureState.calls.Count) { throw 'Case-sensitive path mismatch must fail before transport' }
  foreach ($modelSetting in @('LLM_MODEL_NAME', 'OLLAMA_MODEL')) {
    Set-Content -LiteralPath $fixture.FullName -Value 'OLLAMA_BASE_URL=http://127.0.0.1:11434', ($modelSetting + '="   "')
    $fixtureState.calls.Clear(); $failed = $false; $failureMessage = ''
    try { & $diagnostic -EnvFile $fixture.FullName -ProbeGeneration 6>&1 | Out-Null }
    catch { $failed = $true; $failureMessage = $_.Exception.Message }
    if (-not $failed -or $fixtureState.calls.Count -or $failureMessage -notmatch 'model name is blank') {
      throw "Blank model must fail before network requests: $modelSetting"
    }
  }
  Set-Content -LiteralPath $fixture.FullName -Value 'OLLAMA_BASE_URL=http://gateway.example/ollama', 'OLLAMA_API_KEY=fixture-secret-never-print'
  $fixtureState.calls.Clear(); $failed = $false
  try { & $diagnostic -EnvFile $fixture.FullName 6>&1 | Out-Null } catch { $failed = $true }
  if (-not $failed -or $fixtureState.calls.Count) { throw 'Remote plaintext credentials must be rejected before transport' }
  Write-Host 'PASS: native routes, separate discovery/generation failures, secret redaction, invalid JSON roots, blank models, malformed model entries, case-sensitive paths and HTTPS credential protection.'
} finally {
  Remove-Item -LiteralPath $fixture.FullName -Force
}

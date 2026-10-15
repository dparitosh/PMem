<# .SYNOPSIS Updates slow-LLM timeout budgets in the selected root environment file. #>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [ValidateRange(1,900)][int]$LlmTimeoutSeconds = 300
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$path = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
$path = (Resolve-Path -LiteralPath $path).Path
$settings = Read-DepoEnvironment -Root $root -EnvFile $path
function Read-TimeoutBudget([string]$Name, [int]$Default, [int]$Maximum) {
  if (-not $settings[$Name]) { return $Default }
  $value = 0
  if (-not [int]::TryParse([string]$settings[$Name], [ref]$value) -or $value -lt 1 -or $value -gt $Maximum) {
    throw "$Name must be an integer between 1 and $Maximum; correct it before upgrading."
  }
  return $value
}
$llm = [Math]::Max($LlmTimeoutSeconds, (Read-TimeoutBudget 'LLM_REQUEST_TIMEOUT_SECONDS' 300 900))
$tool = [Math]::Max($llm + 30, (Read-TimeoutBudget 'AGENTIC_TOOL_TIMEOUT_SECONDS' 30 3600))
$preparation = Read-TimeoutBudget 'GRAPH_PUBLICATION_TIMEOUT_SECONDS' 180 3600
$write = Read-TimeoutBudget 'GRAPH_PUBLICATION_WRITE_TIMEOUT_SECONDS' $preparation 3600
$activation = Read-TimeoutBudget 'GRAPH_PUBLICATION_ACTIVATION_TIMEOUT_SECONDS' $preparation 3600
$merge = Read-TimeoutBudget 'MERGE_VALIDATION_TIMEOUT_SECONDS' 180 900
$publicationRun = 2 * $preparation + $write + $activation + $merge + 150
$service = Read-TimeoutBudget 'SERVICE_REQUEST_TIMEOUT_SECONDS' 90 3600
$conversion = Read-TimeoutBudget 'ENGINEERING_CONVERSION_TIMEOUT_SECONDS' 180 900
$engineeringDefault = [Math]::Min(3600, $conversion + 4 * $service + 2 * $preparation + $write + $activation + 90)
$engineering = Read-TimeoutBudget 'ENGINEERING_WORKFLOW_TIMEOUT_SECONDS' $engineeringDefault 3600
$publicationRun = [Math]::Max($publicationRun, $engineering + 90)
$run = [Math]::Max([Math]::Max([Math]::Max(900, $tool + 60), $publicationRun), (Read-TimeoutBudget 'AGENTIC_RUN_TIMEOUT_SECONDS' 300 3600))
if ($run -gt 3600) { throw 'The configured tool budget leaves no margin inside the maximum 3600-second agent run. Correct the budgets before upgrading.' }
$updates = [ordered]@{
  LLM_REQUEST_TIMEOUT_SECONDS = $llm
  AGENTIC_TOOL_TIMEOUT_SECONDS = $tool
  AGENTIC_RUN_TIMEOUT_SECONDS = $run
}
$raw = [IO.File]::ReadAllText($path)
$newline = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
$written = @{}
$lines = [Collections.Generic.List[string]]::new()
foreach ($line in ($raw -split '\r?\n')) {
  if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
    $name = $matches[1]
    if ($updates.Contains($name)) {
      if (-not $written.ContainsKey($name)) { $lines.Add("$name=$($updates[$name])"); $written[$name] = $true }
      continue
    }
  }
  $lines.Add($line)
}
foreach ($name in $updates.Keys) {
  if (-not $written.ContainsKey($name)) { $lines.Add("$name=$($updates[$name])") }
}
$replacement = ($lines -join $newline).TrimEnd([char[]]"`r`n") + $newline
if ($replacement -ne $raw) {
  $temporary = Join-Path (Split-Path -Parent $path) ('.depo-env-update-' + [Guid]::NewGuid().ToString('N') + '.tmp')
  try {
    [IO.File]::WriteAllText($temporary, $replacement, [Text.UTF8Encoding]::new($false))
    Set-Acl -LiteralPath $temporary -AclObject (Get-Acl -LiteralPath $path)
    [IO.File]::Replace($temporary, $path, [System.Management.Automation.Language.NullString]::Value)
  } finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
  }
}
Read-DepoEnvironment -Root $root -EnvFile $path | Out-Null
Write-Host "Timeouts configured: Ollama=${llm}s, agent tool=${tool}s, agent run=${run}s. Restart backend services to apply."

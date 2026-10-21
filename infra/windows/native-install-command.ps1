# Shared audit capture for customer entry points and native installers.
function ConvertTo-DepoAuditMessage([string]$Message, [string]$Root='', [string]$EnvFile='.env.local') {
  $values=@()
  foreach($entry in [Environment]::GetEnvironmentVariables().GetEnumerator()) {
    if($entry.Key -match '(?i)(TOKEN|PASSWORD|PASS$|API_KEY|SECRET|DATABASE_URL)') { $values += [string]$entry.Value }
  }
  $envPaths=@()
  if($Root){
    $envPaths += Join-Path $Root '.env.local'
    $envPaths += $(if([IO.Path]::IsPathRooted($EnvFile)){$EnvFile}else{Join-Path $Root $EnvFile})
  }
  foreach($envPath in @($envPaths | Select-Object -Unique)) {
  if($envPath -and (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    foreach($line in [IO.File]::ReadAllLines($envPath)) {
      if($line -match '^\s*([A-Z0-9_]*(?:TOKEN|PASSWORD|PASS|API_KEY|SECRET|DATABASE_URL)[A-Z0-9_]*)\s*=\s*(.*)$') {
        $value=$Matches[2].Trim()
        if($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) { $value=$value.Substring(1,$value.Length-2) }
        $values += $value
      }
    }
  }
  }
  foreach($value in @($values | Where-Object {$_} | Sort-Object Length -Descending -Unique)) { $Message=$Message.Replace($value,'[REDACTED]') }
  $Message=[regex]::Replace($Message,'(?i)(postgres(?:ql)?://[^:\s/@]+:)[^@\s]+@','$1[REDACTED]@')
  $Message=[regex]::Replace($Message,'(?i)(Bearer\s+)[A-Za-z0-9._~-]+','$1[REDACTED]')
  return $Message
}
function Invoke-DepoLoggedAction {
  param([string]$Root,[string]$Name,[Alias("Action")][scriptblock]$Body,[string]$AuditEnvFile='.env.local')
  $safeName=$Name -replace '[^A-Za-z0-9_-]','-'
  $folder=Join-Path $Root 'logs/installation/runs'
  New-Item -ItemType Directory -Path $folder -Force | Out-Null
  $id=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
  $console=Join-Path $folder ($safeName+'-'+$id+'.log')
  $events=Join-Path $folder ($safeName+'-'+$id+'.jsonl')
  function Write-AuditEvent([string]$Level,[string]$Message) {
    $clean=ConvertTo-DepoAuditMessage -Message $Message -Root $Root -EnvFile $AuditEnvFile
    [IO.File]::AppendAllText($console,$clean+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    $record=@{atUtc=[DateTime]::UtcNow.ToString('o');runId=$id;action=$Name;level=$Level;message=$clean}|ConvertTo-Json -Compress
    [IO.File]::AppendAllText($events,$record+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-Host $clean
  }
  Write-Host "Audit log: $console"
  Write-AuditEvent 'started' "Starting $Name"
  $global:LASTEXITCODE=0
  try {
    $hadErrors=$false
    & $Body *>&1 | ForEach-Object {
      $level=if($_ -is [Management.Automation.ErrorRecord]){'error'}elseif($_ -is [Management.Automation.WarningRecord]){'warning'}else{'output'}
      if($level -eq 'error'){$hadErrors=$true}
      Write-AuditEvent $level ([string]$_)
    }
    if($hadErrors){throw "Action $Name reported errors; see the retained audit log"}
    if($LASTEXITCODE -ne 0){throw "Action $Name exited with native code $LASTEXITCODE"}
    Write-AuditEvent 'succeeded' "Completed $Name"
  } catch {
    $failure=$_
    Write-AuditEvent 'failed' ($failure.ToString()+[Environment]::NewLine+$failure.InvocationInfo.PositionMessage+[Environment]::NewLine+$failure.ScriptStackTrace)
    Write-Host "FAILED. Audit log retained: $console" -ForegroundColor Red
    throw (ConvertTo-DepoAuditMessage -Message $failure.ToString() -Root $Root -EnvFile $AuditEnvFile)
  }
}

function Invoke-DepoInstallCommand {
  param([string]$Executable, [string[]]$NativeArguments, [string]$LogPath)
  $previousPreference = $ErrorActionPreference
  try {
    # Windows PowerShell treats native stderr as ErrorRecord objects. A pip
    # notice/warning must not terminate installation before checking exit code.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    & $Executable @NativeArguments 2>&1 | ForEach-Object {
      $line = ConvertTo-DepoAuditMessage -Message $_.ToString()
      Write-Host $line
      Add-Content -LiteralPath $LogPath -Value $line -ErrorAction Stop
    }
    return $LASTEXITCODE
  } finally { $ErrorActionPreference = $previousPreference }
}

# Keep native stderr out of PowerShell's terminating-error stream, while retaining
# stdout separately for JSON consumers. Exit status remains authoritative.
function Invoke-DepoNativeCommand {
  param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [string[]]$NativeArguments,
    [switch]$AllowFailure,
    [Parameter(ValueFromPipeline=$true)][string]$InputText
  )
  begin { $inputLines=[Collections.Generic.List[string]]::new() }
  process { if($PSBoundParameters.ContainsKey('InputText')){ $inputLines.Add($InputText) } }
  end {
    $savedPreference=$ErrorActionPreference
    try {
      $ErrorActionPreference='Continue'
      $PSNativeCommandUseErrorActionPreference=$false
      $consume={
        if($_ -is [Management.Automation.ErrorRecord]) {
          Write-Host (ConvertTo-DepoAuditMessage -Message $_.ToString() -Root $Root)
        } else { $_ }
      }
      if($inputLines.Count) {
        $inputLines | & $Executable @NativeArguments 2>&1 | ForEach-Object $consume
      } else {
        & $Executable @NativeArguments 2>&1 | ForEach-Object $consume
      }
      $exitCode=$LASTEXITCODE
      $global:LASTEXITCODE=$exitCode
      if($exitCode -ne 0 -and -not $AllowFailure){throw "Native command failed with exit code $exitCode ($Executable)"}
    } finally { $ErrorActionPreference=$savedPreference }
  }
}

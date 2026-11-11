# Process identity and listener checks shared by Windows launchers.
function Test-DepoAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  return ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-DepoVisibleManagement {
  [CmdletBinding()]
  param([string]$Root,[string]$Action,[string]$EnvFile,[string]$Profile,
    [switch]$SkipPostgres,[switch]$SkipFrontend,[switch]$SkipBaselineProvisioning,[switch]$ElevatedRetry)
  $tracking = Join-Path $Root 'logs/windows-services'
  if(-not(Test-Path -LiteralPath $tracking)){return $false}
  $tracked = @(Get-ChildItem -LiteralPath $tracking -Filter '*.pid' -File | Where-Object { -not $SkipFrontend -or $_.Name -ne 'frontend.pid' })
  if(-not $tracked.Count){return $false}
  $hidden = $false
  try {
    $snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach($file in $tracked) {
      $trackedId = 0
      if(-not [int]::TryParse(([string](Get-Content -LiteralPath $file.FullName -Raw)).Trim(),[ref]$trackedId)){continue}
      $process = $snapshot | Where-Object {$_.ProcessId -eq $trackedId} | Select-Object -First 1
      if($process -and (-not $process.ExecutablePath -or -not $process.CommandLine)){$hidden=$true;break}
    }
  } catch {$hidden=$true}
  if(-not $hidden){return $false}
  if($ElevatedRetry -or (Test-DepoAdministrator)) {
    throw 'Windows still hides tracked process identities in the elevated session. No lifecycle action was started. Inspect Windows CIM/WMI and process-access policy; do not delete PID files or disable ownership checks.'
  }
  $scriptPath = Join-Path $Root 'manage-depo.ps1'
  $selectedEnv = if([IO.Path]::IsPathRooted($EnvFile)){$EnvFile}else{Join-Path $Root $EnvFile}
  # Encode a command made exclusively from individually quoted literal arguments.
  # This preserves spaces, apostrophes and the selected environment without shell interpolation.
  $quote = {param([string]$Value) "'"+$Value.Replace("'","''")+"'"}
  $command = '& '+(& $quote $scriptPath)+' -Action '+(& $quote $Action)+' -EnvFile '+(& $quote $selectedEnv)+' -Profile '+(& $quote $Profile)+' -ElevatedRetry'
  foreach($name in @('SkipPostgres','SkipFrontend','SkipBaselineProvisioning')) {
    if(Get-Variable -Name $name -ValueOnly){$command+=' -'+$name}
  }
  $command = 'try { '+$command+'; if(-not $?){exit 1}; exit 0 } catch { Write-Error $_; exit 1 }'
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
  Write-Host 'Windows is hiding tracked process identities. Requesting UAC elevation before any lifecycle action. Audit logs remain under logs/installation/runs.'
  try {
    $child = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') -Verb RunAs -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$encoded) -ErrorAction Stop
  } catch {
    throw 'Windows elevation was cancelled or unavailable. No lifecycle action was started. Open PowerShell with Run as administrator and rerun the same manage-depo.ps1 command.'
  }
  # Start-Process -Wait also waits for newly launched service descendants.
  # Wait only for the lifecycle process; PMem services intentionally remain alive.
  $child.WaitForExit()
  if($child.ExitCode -ne 0){throw 'The elevated PMem lifecycle command failed. Inspect the latest manage log under logs/installation/runs; tracking and ownership checks were retained.'}
  return $true
}

function Get-DepoProcessTree([int]$ProcessId, [string]$ExpectedPython, [string]$Module) {
  $snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
  $rootProcess = $snapshot | Where-Object { $_.ProcessId -eq $ProcessId } | Select-Object -First 1
  if (-not $rootProcess) { return @() }
  if (-not $rootProcess.ExecutablePath -or $rootProcess.ExecutablePath -ine $ExpectedPython -or
      $rootProcess.CommandLine -notmatch ('(?<![A-Za-z0-9_.])' + [regex]::Escape($Module) + '(?![A-Za-z0-9_.])')) {
    throw "Process $ProcessId does not match the expected DEPO runtime and module; refusing to control it."
  }
  $nodes = @(@{ Process = $rootProcess; Depth = 0 })
  $known = [Collections.Generic.HashSet[int]]::new()
  [void]$known.Add($ProcessId)
  for ($index = 0; $index -lt $nodes.Count; $index++) {
    $parent = $nodes[$index]
    foreach ($child in $snapshot) {
      if ($child.ParentProcessId -eq $parent.Process.ProcessId -and
          $child.CreationDate -ge $parent.Process.CreationDate -and $known.Add([int]$child.ProcessId)) {
        $nodes += @{ Process = $child; Depth = $parent.Depth + 1 }
      }
    }
  }
  return $nodes
}

function Test-DepoListener([int]$ProcessId, [string]$ExpectedPython, [string]$Module, [int]$Port, [string]$BindHost) {
  $tree = @(Get-DepoProcessTree $ProcessId $ExpectedPython $Module)
  $owners = @($tree | ForEach-Object { [int]$_.Process.ProcessId })
  $addresses = if ($BindHost -in @('0.0.0.0','::')) { @($BindHost) } else {
    @([Net.Dns]::GetHostAddresses($BindHost) | ForEach-Object { $_.ToString() })
  }
  # Query all listeners: a port-filtered query raises ObjectNotFound during
  # normal startup. Do not hide genuine CIM/access failures as a closed port.
  try { $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop) }
  catch { throw "Windows listener inspection failed for port ${Port}: $($_.Exception.Message)" }
  return [bool](@($listeners |
    Where-Object { $_.LocalPort -eq $Port -and $_.OwningProcess -in $owners -and $_.LocalAddress -in $addresses }).Count)
}

function Stop-DepoProcessTree([int]$ProcessId, [string]$ExpectedPython, [string]$Module, [datetime]$BatchDeadline = [datetime]::MaxValue) {
  $tree = @(Get-DepoProcessTree $ProcessId $ExpectedPython $Module)
  $rootNode = $tree | Where-Object { $_.Depth -eq 0 } | Select-Object -First 1
  if ($rootNode -and $rootNode.Process.CommandLine -match 'backend\.depo_platform\.windows_runtime') {
    $repository = Split-Path (Split-Path (Split-Path $ExpectedPython -Parent) -Parent) -Parent
    $repository = Split-Path $repository -Parent
    $requestPath = Join-Path $repository "logs\windows-services\stop-$ProcessId.request"
    $graceSeconds = 60
    $configuredGrace = 0
    if ([int]::TryParse($env:DEPO_SHUTDOWN_GRACE_SECONDS, [ref]$configuredGrace)) {
      $graceSeconds = [Math]::Max(5, [Math]::Min(600, $configuredGrace))
    }
    Set-Content -LiteralPath $requestPath -Value 'stop' -NoNewline
    $graceDeadline = (Get-Date).AddSeconds($graceSeconds)
    if ($BatchDeadline -lt $graceDeadline) { $graceDeadline = $BatchDeadline }
    do {
      $liveRoot = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
      if (-not $liveRoot -or $liveRoot.CreationDate -ne $rootNode.Process.CreationDate) { break }
      Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $graceDeadline)
    Remove-Item -LiteralPath $requestPath -Force -ErrorAction SilentlyContinue
  }
  foreach ($node in @($tree | Sort-Object Depth -Descending)) {
    # Recheck creation time to avoid killing a reused PID after taking a snapshot.
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($node.Process.ProcessId)" -ErrorAction Stop
    if ($current -and $current.CreationDate -eq $node.Process.CreationDate) {
      try { Stop-Process -Id $current.ProcessId -Force -ErrorAction Stop }
      catch {
        # The process can exit between the identity check and Stop-Process.
        # Preserve real access/termination failures if it is still alive.
        if (Get-Process -Id $current.ProcessId -ErrorAction SilentlyContinue) { throw }
      }
    }
  }
  $owners = @($tree | ForEach-Object { [int]$_.Process.ProcessId })
  $deadline = (Get-Date).AddSeconds(5)
  do {
    $remaining = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.OwningProcess -in $owners })
    if (-not $remaining.Count) { return }
    Start-Sleep -Milliseconds 100
  } while ((Get-Date) -lt $deadline)
  throw 'DEPO process cleanup left an owned listener; tracking is retained for diagnosis.'
}

function Get-DepoProbeHost([string]$BindHost) {
  if ($BindHost -eq '0.0.0.0') { return '127.0.0.1' }
  if ($BindHost -eq '::') { return '[::1]' }
  if ($BindHost.Contains(':') -and -not $BindHost.StartsWith('[')) { return '[' + $BindHost + ']' }
  return $BindHost
}

# A PID file is a hint, not proof of ownership. Never control an unrelated PID.
function Get-DepoTrackedProcessState($Process, [string[]]$AllowedRuntimes, [string]$Module) {
  if (-not $Process) { return 'exited' }
  if (-not $Process.ExecutablePath -or -not $Process.CommandLine) {
    throw 'Cannot inspect tracked process identity; tracking retained. Retry with sufficient process inspection permissions.'
  }
  $pattern = '(?<![A-Za-z0-9_.])' + [regex]::Escape($Module) + '(?![A-Za-z0-9_.])'
  if ($Process.CommandLine -notmatch $pattern) { return 'reused' }
  if ($Process.ExecutablePath -notin $AllowedRuntimes) {
    throw 'Tracked service module uses an unapproved runtime; tracking retained. Inspect its executable path before retrying.'
  }
  return 'owned'
}

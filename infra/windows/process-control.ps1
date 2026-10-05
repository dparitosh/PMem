# Process identity and listener checks shared by Windows launchers.
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
  return [bool](@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -in $owners -and $_.LocalAddress -in $addresses }).Count)
}

function Stop-DepoProcessTree([int]$ProcessId, [string]$ExpectedPython, [string]$Module) {
  $tree = @(Get-DepoProcessTree $ProcessId $ExpectedPython $Module)
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
    $remaining = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $owners })
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

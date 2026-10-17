# Shared guards for dependency installation and tracked process reuse.
function Add-DepoRuntimePath([string]$Directory) {
  $comparison = $Directory.Trim().Trim('"').Replace('/', '\').TrimEnd('\')
  $remaining = @($env:PATH -split ';' | Where-Object {
    $_.Trim().Trim('"').Replace('/', '\').TrimEnd('\') -ine $comparison
  })
  $env:PATH = (@($Directory) + $remaining) -join ';'
}

function Assert-DepoRuntimeIdle([string]$Python) {
  $running = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $Python, [StringComparison]::OrdinalIgnoreCase)
  })
  if ($running.Count) {
    throw 'The selected Python runtime is in use. Stop DEPO services before installing dependencies; use update-depo.ps1 for an existing deployment.'
  }
}

function Assert-DepoDeploymentStopped([string]$Root) {
  $manifest = Get-Content -LiteralPath (Join-Path $Root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
  $runtimes = @((Join-Path $Root 'backend/.dt_venv/Scripts/python.exe'))
  foreach ($entry in (@($manifest.services) + @($manifest.workers))) {
    $runtimes += Join-Path $Root ("backend/.dt_venv-" + $entry.id + '/Scripts/python.exe')
  }
  if (@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.ExecutablePath -in $runtimes }).Count) {
    throw 'DEPO backend processes are running. Stop services before installation or schema migration; use update-depo.ps1 for an existing deployment.'
  }
}

function Get-DepoConfigurationFingerprint([string]$Root, [string]$EnvFile, [hashtable]$Overrides = @{}) {
  $path = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $Root $EnvFile }
  # Persist only the digest. Configuration, including credentials, stays private.
  $values = Read-DepoEnvironment -Root $Root -EnvFile $EnvFile
  $parts = @('DEPO configuration v1', [IO.File]::ReadAllText($path))
  # Include inherited deployment settings as well as file-defined settings.
  # Ignore volatile shell variables (PID, prompt, terminal state).
  $keys = @{} + $values
  foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
    # Python services can consume any inherited variable. Exclude only shell
    # presentation state and Spark paths assigned separately for each runtime.
    if ([string]$entry.Key -notmatch '^(PROMPT|SHLVL|_|PWD|OLDPWD|TERM|LINES|COLUMNS|WT_SESSION|WINDOWID|PYSPARK_PYTHON|PYSPARK_DRIVER_PYTHON)$') {
      $keys[[string]$entry.Key] = $null
    }
  }
  foreach ($key in @($keys.Keys | Sort-Object)) {
    $parts += $key + '=' + [Environment]::GetEnvironmentVariable($key, 'Process')
  }
  foreach ($key in @($Overrides.Keys | Sort-Object)) { $parts += $key + '=' + [string]$Overrides[$key] }
  $hash = [Security.Cryptography.SHA256]::Create()
  try {
    return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))))).Replace('-', '').ToLowerInvariant()
  } finally { $hash.Dispose() }
}

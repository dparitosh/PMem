<# .SYNOPSIS Builds the frontend using authoritative root service routing.
.DESCRIPTION
Does not install dependencies or edit configuration. Overrides both Vite and
legacy CRA aliases for all root routing values for this build only,
then restores the process environment. Other alias conflicts still fail.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local', [string]$NodeJsDir = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
. (Join-Path $PSScriptRoot 'native-install-command.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
$routing = Resolve-DepoRouting $values
if (-not $NodeJsDir) { $NodeJsDir = $values['DEPO_NODEJS_DIR'] }
$runtime = Get-DepoNodeRuntime -Root $root -NodeJsDir $NodeJsDir
$NodeJsDir = $runtime.Directory
$node = $runtime.Node
$npm = $runtime.Npm
Write-Host "Frontend build using Node.js $($runtime.Version)"
$previous = @{}
$previous['PATH'] = [Environment]::GetEnvironmentVariable('PATH', 'Process')
$overrideName = 'DEPO_BROWSER_ROUTING_OVERRIDE_JSON'
$previous[$overrideName] = [Environment]::GetEnvironmentVariable($overrideName, 'Process')
try {
  $env:Path = $NodeJsDir + [IO.Path]::PathSeparator + $env:Path
  $browser = @{}
  foreach ($key in $routing.Keys) {
    if ($key.StartsWith('VITE_')) {
      $browser[$key] = [string]$routing[$key]
      foreach ($alias in @($key, ('REACT_APP_' + $key.Substring(5)))) {
        $previous[$alias] = [Environment]::GetEnvironmentVariable($alias, 'Process')
        [Environment]::SetEnvironmentVariable($alias, [string]$routing[$key], 'Process')
      }
    }
  }
  # Windows PowerShell removes empty process variables. Carry explicit empty
  # routing values separately so dotenv cannot reintroduce an old gateway.
  [Environment]::SetEnvironmentVariable($overrideName, (ConvertTo-Json -InputObject $browser -Compress), 'Process')
  Push-Location (Join-Path $root 'frontend')
  try {
    if (-not (Test-Path -LiteralPath 'node_modules/.bin/vite.cmd' -PathType Leaf)) {
      throw 'Frontend dependencies are absent. Run the supported installer or npm.cmd ci before building.'
    }
    # Build away from the served directory. Preserve old hashed assets for open
    # tabs and publish index.html only after every new asset is available.
    $frontendRoot = (Get-Location).Path
    $stageName = '.depo-build-' + [guid]::NewGuid().ToString('N')
    $stage = Join-Path $frontendRoot $stageName
    $dist = Join-Path $frontendRoot 'dist'
    try {
      Invoke-DepoNativeCommand -Executable $npm -NativeArguments @('run','build','--','--outDir',$stageName)
      if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. Existing served files were retained.' }
      if (-not (Test-Path -LiteralPath (Join-Path $stage 'index.html') -PathType Leaf)) { throw 'Frontend build produced no index. Existing served files were retained.' }
      New-Item -ItemType Directory -Path $dist -Force | Out-Null
      foreach ($item in Get-ChildItem -LiteralPath $stage -Force) {
        if ($item.Name -ne 'index.html') { Copy-Item -LiteralPath $item.FullName -Destination $dist -Recurse -Force }
      }
      Write-DepoBrowserRouting -Root $root -EnvFile $EnvFile
      $nextIndex = Join-Path $dist ('index-' + [guid]::NewGuid().ToString('N') + '.tmp')
      Copy-Item -LiteralPath (Join-Path $stage 'index.html') -Destination $nextIndex
      $index = Join-Path $dist 'index.html'
      if (Test-Path -LiteralPath $index) {
        $previousIndex = $nextIndex + '.previous'
        [IO.File]::Replace($nextIndex, $index, $previousIndex)
        Remove-Item -LiteralPath $previousIndex -Force
      }
      else { [IO.File]::Move($nextIndex, $index) }
    } finally {
      if (Test-Path -LiteralPath $stage) {
        $resolvedStage = (Resolve-Path -LiteralPath $stage).Path
        if (-not $resolvedStage.StartsWith($frontendRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path $resolvedStage -Leaf) -notmatch '^\.depo-build-[a-f0-9]{32}$') { throw 'Unsafe frontend staging cleanup path.' }
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
      }
    }
  } finally { Pop-Location }
} finally {
  foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
  $values.Clear()
}
Write-Host 'Frontend build and public runtime routing completed. Start or restart the frontend launcher next.'

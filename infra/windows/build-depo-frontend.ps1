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
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
$routing = Resolve-DepoRouting $values
# Explicit configuration wins; support portable Node beside the Apps folder.
if (-not $NodeJsDir) { $NodeJsDir = $values['DEPO_NODEJS_DIR'] }
if (-not $NodeJsDir) {
  $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
  if ($nodeCommand) { $NodeJsDir = Split-Path $nodeCommand.Source }
  else { $NodeJsDir = Join-Path (Split-Path (Split-Path $root)) 'NodeJS' }
}
$node = Join-Path $NodeJsDir 'node.exe'
$npm = Join-Path $NodeJsDir 'npm.cmd'
if (-not (Test-Path -LiteralPath $node -PathType Leaf) -or -not (Test-Path -LiteralPath $npm -PathType Leaf)) {
  throw 'Node.js runtime missing. Set DEPO_NODEJS_DIR in root environment or pass -NodeJsDir containing node.exe and npm.cmd.'
}
$nodeVersion = & $node --version
if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v24\.') { throw 'PMem frontend requires Node.js 24. Select its directory with -NodeJsDir or DEPO_NODEJS_DIR.' }
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
    & $npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. Review non-routing browser aliases and build output; services were not started.' }
    Write-DepoBrowserRouting -Root $root -EnvFile $EnvFile
  } finally { Pop-Location }
} finally {
  foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
  $values.Clear()
}
Write-Host 'Frontend build and public runtime routing completed. Start or restart the frontend launcher next.'

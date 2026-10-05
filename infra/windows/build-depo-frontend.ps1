<# .SYNOPSIS Builds the frontend using authoritative root service routing.
.DESCRIPTION
Does not install dependencies or edit configuration. Overrides both Vite and
legacy CRA aliases for nonempty root routing values for this build only,
then restores the process environment. Other alias conflicts still fail.
#>
[CmdletBinding()]
param([string]$EnvFile = '.env.local')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
$routing = Resolve-DepoRouting $values
$previous = @{}
try {
  foreach ($key in $routing.Keys) {
    if ($key.StartsWith('VITE_') -and $routing[$key]) {
      foreach ($alias in @($key, ('REACT_APP_' + $key.Substring(5)))) {
        $previous[$alias] = [Environment]::GetEnvironmentVariable($alias, 'Process')
        [Environment]::SetEnvironmentVariable($alias, [string]$routing[$key], 'Process')
      }
    }
  }
  Push-Location (Join-Path $root 'frontend')
  try {
    if (-not (Test-Path -LiteralPath 'node_modules/.bin/vite.cmd' -PathType Leaf)) {
      throw 'Frontend dependencies are absent. Run the supported installer or npm.cmd ci before building.'
    }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. Review non-routing browser aliases and build output; services were not started.' }
    Write-DepoBrowserRouting -Root $root -EnvFile $EnvFile
  } finally { Pop-Location }
} finally {
  foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
  $values.Clear()
}
Write-Host 'Frontend build and public runtime routing completed. Start or restart the frontend launcher next.'

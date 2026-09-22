# No downloads, subprocess installation or database access. Run in a fresh shell.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$testParent = Join-Path $root '.release-test-tmp'
$testRoot = Join-Path $testParent ('install-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $testRoot 'infra/windows'), (Join-Path $testRoot 'frontend') | Out-Null
function TestPython {
  if ($args[0] -ne '-c') { throw 'Unexpected Python installation attempted.' }
  $global:LASTEXITCODE = 0
  $global:depoTestPythonVersion
}
function node {
  if ($args[0] -ne '--version') { throw 'Unexpected Node execution.' }
  $global:LASTEXITCODE = 0
  $global:depoTestNodeVersion
}
function npm.cmd {
  if ($args[0] -ne '--version') { throw 'Unexpected npm installation attempted.' }
  $global:LASTEXITCODE = 0
  $global:depoTestNpmVersion
}
function Assert-Rejected([string]$Expected) {
  $message = ''
  try { & $script:installer -Python TestPython -CheckPrerequisites } catch { $message = $_.Exception.Message }
  if ($message -notlike "*$Expected*") { throw "Expected rejection containing '$Expected'; received '$message'." }
}
try {
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-depo.ps1') -Destination (Join-Path $testRoot 'infra/windows')
  Set-Content -LiteralPath (Join-Path $testRoot 'frontend/package-lock.json') -Value '{}'
  $script:installer = Join-Path $testRoot 'infra/windows/install-depo.ps1'
  $global:depoTestPythonVersion = '3.11.9'
  $global:depoTestNodeVersion = 'v24.0.0'
  $global:depoTestNpmVersion = '10.2.0'
  & $script:installer -Python TestPython -CheckPrerequisites -Development
  $global:depoTestPythonVersion = '3.10.9'
  Assert-Rejected 'Python 3.11'
  $global:depoTestPythonVersion = '3.11.9'
  $global:depoTestNodeVersion = 'v20.0.0'
  Assert-Rejected 'Node.js 24'
  $global:depoTestNodeVersion = 'v24.0.0'
  $global:depoTestNpmVersion = '10.1.0'
  Assert-Rejected 'npm 10.2'
  # Backend-only checking must not require a compatible frontend runtime.
  & $script:installer -Python TestPython -CheckPrerequisites -SkipFrontend
  $global:depoTestNpmVersion = '10.2.0'
  Remove-Item -LiteralPath (Join-Path $testRoot 'frontend/package-lock.json')
  Assert-Rejected 'Missing frontend/package-lock.json'
  if (Test-Path -LiteralPath (Join-Path $testRoot 'backend/.dt_venv')) { throw 'Check-only mode created an environment.' }
  Write-Output 'PASS: prerequisite acceptance, old Python/Node/npm rejection, backend-only mode, missing lockfile and no installation side effects.'
} finally {
  $resolved = (Resolve-Path -LiteralPath $testRoot).Path
  if (-not $resolved.StartsWith([IO.Path]::GetFullPath($testParent) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path.' }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

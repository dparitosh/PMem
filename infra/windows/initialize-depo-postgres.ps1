param(
  [Parameter(Mandatory = $true)][string]$BinDir,
  [Parameter(Mandatory = $true)][string]$DataDir
)
$ErrorActionPreference = 'Stop'
foreach ($path in @($BinDir, $DataDir)) {
  if (-not [IO.Path]::IsPathRooted($path)) { throw 'PostgreSQL binary and data paths must be absolute.' }
}
$initdb = Join-Path $BinDir 'initdb.exe'
if (-not (Test-Path -LiteralPath $initdb -PathType Leaf)) { throw 'Install approved PostgreSQL binaries before initializing a cluster.' }
if (Test-Path -LiteralPath $DataDir) { throw 'DataDir already exists. Refusing to initialize or change an existing cluster.' }
# initdb prompts on the terminal; passwords are never command arguments or files.
& $initdb -D $DataDir -U postgres --encoding=UTF8 --auth-local=scram-sha-256 --auth-host=scram-sha-256 --pwprompt
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed. Preserve output for diagnosis; do not retry over existing data.' }
Write-Host 'Cluster initialized with password authentication. Configure listen address, TLS, port, access rules and backup policy before starting it. See INSTALLATION.md.'

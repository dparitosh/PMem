[CmdletBinding()]
param([string]$Maven = 'mvn.cmd')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$binary = Get-Command $Maven -ErrorAction Stop
& $binary.Source -B -f (Join-Path $PSScriptRoot 'pom.xml') package
if($LASTEXITCODE -ne 0){throw 'OWL-DL worker build failed'}
$destination = Join-Path $root 'backend/ontology_service/resources/reasoner'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$jar = Join-Path $destination 'depo-owl-dl.jar'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'target/depo-owl-dl-1.0.0.jar') -Destination $jar -Force
$metadata = @{engine='HermiT';version='1.4.5.519';worker_version='1.0.0';file='depo-owl-dl.jar';sha256=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash.ToLowerInvariant();build='infra/reasoner/pom.xml'} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $destination 'manifest.json'),$metadata,(New-Object Text.UTF8Encoding($false)))
Write-Host 'OWL-DL worker bundled with SHA-256 manifest. No system configuration changed.'

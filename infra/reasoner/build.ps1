[CmdletBinding()]
param([string]$Maven = 'mvn.cmd', [switch]$UseBundledDependencies)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$destination = Join-Path $root 'backend/ontology_service/resources/reasoner'
$jar = Join-Path $destination 'depo-owl-dl.jar'
if ($UseBundledDependencies) {
  $existing = Get-Content -LiteralPath (Join-Path $destination 'manifest.json') -Raw | ConvertFrom-Json
  if ((Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $existing.sha256) {throw 'Bundled reasoner digest mismatch; refusing offline rebuild'}
  $compiler = (Get-Command javac -ErrorAction Stop).Source
  $archiver = (Get-Command jar -ErrorAction Stop).Source
  $stage = Join-Path ([IO.Path]::GetTempPath()) ('nexus-reasoner-build-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $stage | Out-Null
  try {
    $source = Join-Path $PSScriptRoot 'src/main/java/org/depo/reasoner/Main.java'
    & $compiler --release 11 -encoding UTF-8 -cp $jar -d $stage $source
    if ($LASTEXITCODE -ne 0) {throw 'OWL-DL offline compilation failed'}
    $candidate = Join-Path $stage 'depo-owl-dl.jar'
    Copy-Item -LiteralPath $jar -Destination $candidate
    & $archiver --update --file $candidate -C $stage 'org/depo/reasoner/Main.class'
    if ($LASTEXITCODE -ne 0) {throw 'OWL-DL offline packaging failed'}
    Copy-Item -LiteralPath $candidate -Destination $jar -Force
  } finally {
    $resolvedStage = [IO.Path]::GetFullPath($stage)
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolvedStage.StartsWith($temporaryRoot,[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolvedStage -Leaf).StartsWith('nexus-reasoner-build-')) {Remove-Item -LiteralPath $resolvedStage -Recurse -Force}
  }
} else {
  $binary = Get-Command $Maven -ErrorAction Stop
  & $binary.Source -B -f (Join-Path $PSScriptRoot 'pom.xml') package
  if ($LASTEXITCODE -ne 0) {throw 'OWL-DL worker build failed'}
  New-Item -ItemType Directory -Path $destination -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'target/depo-owl-dl-1.0.0.jar') -Destination $jar -Force
}
$metadata = @{engine='HermiT';version='1.4.5.519';worker_version='1.0.0';file='depo-owl-dl.jar';sha256=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash.ToLowerInvariant();build=$(if ($UseBundledDependencies) {'infra/reasoner/build.ps1 -UseBundledDependencies'} else {'infra/reasoner/pom.xml'});source_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'src/main/java/org/depo/reasoner/Main.java') -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $destination 'manifest.json'),$metadata,(New-Object Text.UTF8Encoding($false)))
Write-Host 'OWL-DL worker bundled with SHA-256 manifest. No system configuration changed.'

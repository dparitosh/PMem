<#
.SYNOPSIS
Builds Hadoop 3.4.2 native Windows helpers from verified Apache source.

.DESCRIPTION
Run only on an approved build workstation from an x64 Native Tools Command
Prompt for Visual Studio 2019. The script downloads and verifies Apache source,
pins vcpkg to the commit specified by Hadoop 3.4.2, builds the native Windows
distribution, and stages winutils.exe and hadoop.dll with a hash manifest.
It does not install binaries on the DEPO application VM.
#>
param(
  [ValidateSet('3.4.2')][string]$HadoopVersion = '3.4.2',
  [string]$BuildRoot = 'C:\DEPO\hadoop-build',
  [string]$VcpkgRoot = 'C:\vcpkg',
  [string]$OutputDirectory = 'C:\DEPO\approved\hadoop-3.4.2-windows-x64',
  [switch]$Resume,
  [switch]$SkipSignatureVerification
)

$ErrorActionPreference = 'Stop'
$vcpkgCommit = '7ffa425e1db8b0c3edf9c50f2f3a0f25a324541d'
$baseUri = "https://archive.apache.org/dist/hadoop/common/hadoop-$HadoopVersion"
$archiveName = "hadoop-$HadoopVersion-src.tar.gz"
$downloadDirectory = Join-Path $BuildRoot 'downloads'
$archive = Join-Path $downloadDirectory $archiveName
$sourceDirectory = Join-Path $BuildRoot "hadoop-$HadoopVersion-src"
$outputBin = Join-Path $OutputDirectory 'bin'

function Require-Command([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $command) { throw "Required build command is unavailable: $Name" }
  return $command.Source
}

foreach ($path in @($BuildRoot, $VcpkgRoot, $OutputDirectory)) {
  if (-not [IO.Path]::IsPathRooted($path)) { throw "Build paths must be absolute: $path" }
}
if ((Test-Path -LiteralPath $sourceDirectory) -and -not $Resume) {
  throw "Source directory already exists: $sourceDirectory. Inspect it and rerun with -Resume, or use a new BuildRoot."
}
if ((Test-Path -LiteralPath $outputBin) -and -not $Resume) {
  throw "Output directory already exists: $outputBin. Inspect it and rerun with -Resume, or use a new OutputDirectory."
}

$git = Require-Command 'git.exe'
$tar = Require-Command 'tar.exe'
$maven = Require-Command 'mvn.cmd'
$null = Require-Command 'cmake.exe'
$null = Require-Command 'cl.exe'
$java = Require-Command 'java.exe'
$gpg = if ($SkipSignatureVerification) { $null } else { Require-Command 'gpg.exe' }

$javaVersion = (& $java -version 2>&1 | Out-String)
if ($javaVersion -notmatch 'version\s+"1\.8\.') {
  throw 'The Hadoop 3.4.2 Windows build workstation must use JDK 8. Set JAVA_HOME and PATH before running this script.'
}

New-Item -ItemType Directory -Force $downloadDirectory | Out-Null
foreach ($suffix in @('', '.sha512', '.asc')) {
  $target = "$archive$suffix"
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    Invoke-WebRequest -Uri "$baseUri/$archiveName$suffix" -OutFile $target
  }
}

$checksumText = Get-Content -LiteralPath "$archive.sha512" -Raw
$checksumMatch = [regex]::Match($checksumText, '(?i)\b[0-9a-f]{128}\b')
if (-not $checksumMatch.Success) { throw 'Apache SHA-512 file did not contain a valid digest.' }
$expectedSha512 = $checksumMatch.Value.ToLowerInvariant()
$actualSha512 = (Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash.ToLowerInvariant()
if ($actualSha512 -ne $expectedSha512) { throw 'Hadoop source SHA-512 verification failed.' }

if (-not $SkipSignatureVerification) {
  $keys = Join-Path $downloadDirectory 'apache-hadoop-KEYS'
  if (-not (Test-Path -LiteralPath $keys -PathType Leaf)) {
    Invoke-WebRequest -Uri 'https://downloads.apache.org/hadoop/common/KEYS' -OutFile $keys
  }
  & $gpg --import $keys
  if ($LASTEXITCODE -ne 0) { throw 'Apache Hadoop signing-key import failed.' }
  & $gpg --verify "$archive.asc" $archive
  if ($LASTEXITCODE -ne 0) { throw 'Hadoop source PGP signature verification failed.' }
}

if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
  & $tar -xzf $archive -C $BuildRoot
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
    throw "Hadoop source extraction failed: $sourceDirectory"
  }
}

if (-not (Test-Path -LiteralPath (Join-Path $VcpkgRoot '.git') -PathType Container)) {
  if (Test-Path -LiteralPath $VcpkgRoot) { throw "VcpkgRoot exists but is not a Git checkout: $VcpkgRoot" }
  & $git clone https://github.com/microsoft/vcpkg.git $VcpkgRoot
  if ($LASTEXITCODE -ne 0) { throw 'vcpkg clone failed.' }
}
Push-Location $VcpkgRoot
try {
  & $git fetch --tags origin
  if ($LASTEXITCODE -ne 0) { throw 'vcpkg fetch failed.' }
  & $git checkout --detach $vcpkgCommit
  if ($LASTEXITCODE -ne 0) { throw 'vcpkg commit checkout failed.' }
  & (Join-Path $VcpkgRoot 'bootstrap-vcpkg.bat')
  if ($LASTEXITCODE -ne 0) { throw 'vcpkg bootstrap failed.' }
  & (Join-Path $VcpkgRoot 'vcpkg.exe') install boost:x64-windows protobuf:x64-windows openssl:x64-windows zlib:x64-windows
  if ($LASTEXITCODE -ne 0) { throw 'vcpkg dependency installation failed.' }
} finally {
  Pop-Location
}

$dependencyRoot = Join-Path $VcpkgRoot 'installed\x64-windows'
$env:CLASSPATH = ''
$env:PROTOBUF_HOME = $dependencyRoot
$env:MAVEN_OPTS = '-Xmx2048M -Xss128M'
$mavenArguments = @(
  'clean', 'package', '-Dhttps.protocols=TLSv1.2', '-DskipTests', '-DskipDocs',
  '-Pnative-win,dist', '-Drequire.openssl', '-Drequire.test.libhadoop', '-Pyarn-ui',
  '-Dshell-executable=C:\Git\bin\bash.exe', '-Dtar',
  "-Dopenssl.prefix=$dependencyRoot", "-Dcmake.prefix.path=$dependencyRoot",
  "-Dwindows.cmake.toolchain.file=$VcpkgRoot\scripts\buildsystems\vcpkg.cmake",
  '-Dwindows.cmake.build.type=RelWithDebInfo', '-Dwindows.build.hdfspp.dll=off',
  '-Dwindows.no.sasl=on', '-Duse.platformToolsetVersion=v142'
)
Push-Location $sourceDirectory
try {
  & $maven @mavenArguments
  if ($LASTEXITCODE -ne 0) { throw 'Hadoop 3.4.2 native Windows build failed.' }
} finally {
  Pop-Location
}

$nativeBin = Join-Path $sourceDirectory 'hadoop-common-project\hadoop-common\target\bin'
$winutils = Join-Path $nativeBin 'winutils.exe'
$hadoopDll = Join-Path $nativeBin 'hadoop.dll'
foreach ($file in @($winutils, $hadoopDll)) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Expected Hadoop build output was not produced: $file" }
}

New-Item -ItemType Directory -Force $outputBin | Out-Null
Copy-Item -LiteralPath $winutils -Destination (Join-Path $outputBin 'winutils.exe') -Force
Copy-Item -LiteralPath $hadoopDll -Destination (Join-Path $outputBin 'hadoop.dll') -Force
$manifest = [ordered]@{
  hadoop_version = $HadoopVersion
  spark_version = '4.1.2'
  architecture = 'windows-x64'
  apache_source_url = "$baseUri/$archiveName"
  source_sha512 = $actualSha512
  signature_verified = -not [bool]$SkipSignatureVerification
  vcpkg_commit = $vcpkgCommit
  winutils_sha256 = (Get-FileHash -LiteralPath (Join-Path $outputBin 'winutils.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
  hadoop_dll_sha256 = (Get-FileHash -LiteralPath (Join-Path $outputBin 'hadoop.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'build-manifest.json') -Encoding utf8

Write-Host "Hadoop $HadoopVersion Windows helpers built and staged at $outputBin" -ForegroundColor Green
$manifest | Format-List

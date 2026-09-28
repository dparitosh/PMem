[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$WinutilsPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[A-Fa-f0-9]{64}$')]
  [string]$WinutilsSha256,
  [Parameter(Mandatory = $true)]
  [string]$HadoopDllPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[A-Fa-f0-9]{64}$')]
  [string]$HadoopDllSha256,
  [string]$Destination = 'C:\DEPO\runtime\hadoop',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Assert-ApprovedFile([string]$Path, [string]$ExpectedHash, [string]$Name) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "$Name was not found: $Path"
  }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $actual = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash
  if ($actual -ne $ExpectedHash.ToUpperInvariant()) {
    throw "$Name SHA-256 mismatch. Expected $ExpectedHash; received $actual."
  }
  return $resolved
}

$approvedWinutils = Assert-ApprovedFile $WinutilsPath $WinutilsSha256 'winutils.exe'
$approvedHadoopDll = Assert-ApprovedFile $HadoopDllPath $HadoopDllSha256 'hadoop.dll'

if (-not [IO.Path]::IsPathFullyQualified($Destination)) { throw 'Destination must be an absolute Windows path.' }
$destinationRoot = [IO.Path]::GetFullPath($Destination)
$destinationBin = Join-Path $destinationRoot 'bin'
$targetWinutils = Join-Path $destinationBin 'winutils.exe'
if ((Test-Path -LiteralPath $targetWinutils) -and -not $Force) {
  throw "Destination already contains winutils.exe: $targetWinutils. Re-run with -Force only after approving replacement."
}
$targetHadoopDll = Join-Path $destinationBin 'hadoop.dll'
if ((Test-Path -LiteralPath $targetHadoopDll) -and -not $Force) {
  throw "Destination already contains hadoop.dll: $targetHadoopDll. Re-run with -Force only after approving replacement."
}

# Finish every validation before changing the destination.
New-Item -ItemType Directory -Path $destinationBin -Force | Out-Null
Copy-Item -LiteralPath $approvedWinutils -Destination $targetWinutils -Force
Unblock-File -LiteralPath $targetWinutils

Copy-Item -LiteralPath $approvedHadoopDll -Destination $targetHadoopDll -Force
Unblock-File -LiteralPath $targetHadoopDll

& $targetWinutils ls $destinationRoot | Out-Null
if ($LASTEXITCODE -ne 0) { throw "winutils.exe could not execute successfully from $targetWinutils" }

Write-Host 'Windows Hadoop helper installation passed.' -ForegroundColor Green
Write-Host "DEPO_HADOOP_HOME=$destinationRoot"
Write-Host "HADOOP_HOME=$destinationRoot"
Write-Host "PATH entry=$destinationBin"
Write-Host "winutils SHA-256=$((Get-FileHash -LiteralPath $targetWinutils -Algorithm SHA256).Hash)"
Write-Host "hadoop.dll SHA-256=$((Get-FileHash -LiteralPath $targetHadoopDll -Algorithm SHA256).Hash)"

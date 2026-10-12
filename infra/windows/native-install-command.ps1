function Invoke-DepoInstallCommand {
  param([string]$Executable, [string[]]$NativeArguments, [string]$LogPath)
  $previousPreference = $ErrorActionPreference
  try {
    # Windows PowerShell treats native stderr as ErrorRecord objects. A pip
    # notice/warning must not terminate installation before checking exit code.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    & $Executable @NativeArguments 2>&1 | ForEach-Object {
      $line = $_.ToString()
      Write-Host $line
      Add-Content -LiteralPath $LogPath -Value $line -ErrorAction Stop
    }
    return $LASTEXITCODE
  } finally { $ErrorActionPreference = $previousPreference }
}

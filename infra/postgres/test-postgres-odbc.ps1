<#
.SYNOPSIS
Tests an existing 64-bit PostgreSQL System DSN without changing it.
.DESCRIPTION
This is for an external ODBC consumer. DEPO itself connects with psycopg.
The password is entered interactively and never printed or saved in a DSN.
#>
[CmdletBinding()]
param([string]$Dsn = 'DEPO_PG_REMOTE', [string]$User = 'depo_app')
$ErrorActionPreference = 'Stop'
$driver = @(Get-OdbcDriver -Name '*PostgreSQL*' -ErrorAction SilentlyContinue | Where-Object Platform -eq '64-bit')
if (-not $driver.Count) { throw 'No 64-bit PostgreSQL ODBC driver is installed.' }
$source = @(Get-OdbcDsn -Name $Dsn -DsnType System -Platform '64-bit' -ErrorAction SilentlyContinue)
if (-not $source.Count) { throw "64-bit PostgreSQL ODBC DSN '$Dsn' was not found. Create a 64-bit System DSN first." }
if ($source[0].DriverName -notmatch 'PostgreSQL') { throw "System DSN '$Dsn' does not use a PostgreSQL ODBC driver." }
$secure = Read-Host "Password for PostgreSQL user $User" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$password = $null
$connection = $null
try {
  $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  $builder = [System.Data.Odbc.OdbcConnectionStringBuilder]::new()
  $builder['DSN'] = $Dsn
  $builder['UID'] = $User
  $builder['PWD'] = $password
  $connection = [System.Data.Odbc.OdbcConnection]::new($builder.ConnectionString)
  $connection.Open()
  $command = $connection.CreateCommand()
  try {
    $command.CommandText = 'SELECT current_database(), current_user'
    $reader = $command.ExecuteReader()
    try {
      if (-not $reader.Read()) { throw 'PostgreSQL ODBC probe returned no row.' }
      [pscustomobject]@{ Status = 'ok'; Database = $reader.GetString(0); User = $reader.GetString(1); Dsn = $Dsn }
    } finally { $reader.Dispose() }
  } finally { $command.Dispose() }
} finally {
  if ($connection) { $connection.Dispose() }
  $password = $null
  if ($secure) { $secure.Dispose() }
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

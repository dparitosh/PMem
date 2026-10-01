$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$parent = Join-Path $root '.release-test-tmp'
$fixture = Join-Path $parent ('runtime-' + [guid]::NewGuid().ToString('N'))
$oldOutput = $env:DEPO_SPARK_OUTPUT_ROOT
function Assert-Rejected([scriptblock]$Action, [string]$Expected) {
  $message = ''
  try { & $Action } catch { $message = $_.Exception.Message }
  if ($message -notlike "*$Expected*") { throw "Expected '$Expected'; got '$message'" }
}
try {
  New-Item -ItemType Directory -Path $fixture -Force | Out-Null
  $envPath = Join-Path $fixture '.env.local'
  Set-Content -LiteralPath $envPath -Value @('DEPO_AUDIT_FIXTURE=one','DEPO_AUDIT_FIXTURE=two')
  Assert-Rejected { Import-DepoEnvironment $fixture '.env.local' } 'Duplicate'
  if ($env:DEPO_AUDIT_FIXTURE) { throw 'Invalid configuration partially changed environment.' }
  Set-Content -LiteralPath $envPath -Encoding UTF8 -Value @('# valid comment', 'DEPO_AUDIT_FIXTURE = "value with spaces" # comment', 'BROKEN PRIVATE VALUE')
  Assert-Rejected { Import-DepoEnvironment $fixture '.env.local' } 'line 3'
  $secretSafeMessage = ''
  try { Read-DepoEnvironment $fixture '.env.local' | Out-Null } catch { $secretSafeMessage = $_.Exception.Message }
  if ($secretSafeMessage.Contains('PRIVATE VALUE')) { throw 'Parser error leaked the invalid input.' }
  if ($env:DEPO_AUDIT_FIXTURE) { throw 'Malformed configuration partially changed environment.' }
  Set-Content -LiteralPath $envPath -Encoding UTF8 -Value @('DEPO_AUDIT_FIXTURE = "value with spaces" # comment', 'LITERAL=''$(Write-Output unexpected)''', 'PATH_VALUE=C:\DEPO\data', 'HASH_VALUE=value#hash', 'BOOL_VALUE=false # explanation')
  $parsed = Read-DepoEnvironment $fixture '.env.local'
  if ($parsed.DEPO_AUDIT_FIXTURE -ne 'value with spaces' -or $parsed.LITERAL -ne '$(Write-Output unexpected)' -or $parsed.PATH_VALUE -ne 'C:\DEPO\data' -or $parsed.HASH_VALUE -ne 'value#hash' -or $parsed.BOOL_VALUE -ne 'false') { throw 'Literal dotenv parsing failed.' }
  Set-Content -LiteralPath $envPath -Value 'DEPO_AUDIT_FIXTURE="unclosed'
  Assert-Rejected { Read-DepoEnvironment $fixture '.env.local' } 'Invalid quoted value'
  Assert-Rejected { Import-DepoEnvironment $fixture 'missing.env' } 'Missing environment'
  foreach ($baseUrl in @('http://127.0.0.1:8015', 'http://10.10.12.21:8015', 'https://api.example', 'http://api.example/prefix')) {
    Assert-DepoOslcConfiguration @{ OSLC_BASE_URL=$baseUrl } -Required
  }
  foreach ($baseUrl in @('', 'https://<customer-api-host>', 'http:////127.0.0.1:8015', 'ftp://api.example', 'http://user:secret@api.example', 'http://api.example?key=secret', 'http://api.example#fragment')) {
    Assert-Rejected { Assert-DepoOslcConfiguration @{ OSLC_BASE_URL=$baseUrl } -Required } 'HTTP or HTTPS'
  }
  $savedFlags = @{}
  foreach ($key in @('DEPO_SPARK_ENABLED','DEPO_SPARK_NEO4J_ENABLED','DEPO_SPARK_POSTGRES_ENABLED','DEPO_PIPELINE_SCHEDULER_ENABLED')) {
    $savedFlags[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, 'false', 'Process')
  }
  try {
    $env:DEPO_SPARK_ENABLED = 'true'
    $env:DEPO_SPARK_NEO4J_ENABLED = 'true'
    $env:DEPO_SPARK_POSTGRES_ENABLED = 'true'
    $options = Resolve-DepoSparkOptions @{}
    if (-not $options.EnableSpark -or -not $options.EnableNeo4jSparkConnector -or -not $options.EnablePostgresSparkConnector) { throw 'Environment flags ignored.' }
    Assert-Rejected { Resolve-DepoSparkOptions @{ EnableSpark = $false } } 'require Spark'
    $options = Resolve-DepoSparkOptions @{ EnableSpark = $false; EnableNeo4jSparkConnector = $false; EnablePostgresSparkConnector = $false }
    if ($options.EnableSpark -or $options.EnableNeo4jSparkConnector -or $options.EnablePostgresSparkConnector) { throw 'Explicit false overrides ignored.' }
    $env:DEPO_SPARK_ENABLED = 'invalid'
    Assert-Rejected { Resolve-DepoSparkOptions @{} } 'Invalid boolean'
  } finally {
    foreach ($key in $savedFlags.Keys) { [Environment]::SetEnvironmentVariable($key, $savedFlags[$key], 'Process') }
  }
  $neo = @{ NEO4J_URI = 'neo4j+s://graph.example.com'; NEO4J_USER = 'app'; NEO4J_PASS = 'fixture'; NEO4J_DATABASE = 'neo4j' }
  Assert-DepoNeo4jConfiguration $neo -Production
  $neo.NEO4J_URI = 'bolt+s://graph.example.com:7687'
  Assert-DepoNeo4jConfiguration $neo -Production
  foreach ($scheme in @('neo4j','bolt','neo4j+ssc','bolt+ssc')) {
    $neo.NEO4J_URI = "${scheme}://graph.example.com"
    Assert-DepoNeo4jConfiguration $neo
    Assert-Rejected { Assert-DepoNeo4jConfiguration $neo -Production } 'Production TLS mode'
  }
  $neo = @{ NEO4J_URI = 'bolt://graph.internal:7687'; NEO4J_USER = 'app'; NEO4J_PASS = 'fixture'; NEO4J_DATABASE = 'neo4j'; NEO4J_TLS_MODE = 'disabled'; NEO4J_ENCRYPTED = 'false' }
  Assert-DepoNeo4jConfiguration $neo -Production
  $neo.NEO4J_ENCRYPTED = 'true'
  Assert-Rejected { Assert-DepoNeo4jConfiguration $neo -Production } 'NEO4J_ENCRYPTED=false'
  $neo.NEO4J_ENCRYPTED = 'false'; $neo.NEO4J_URI = 'neo4j+s://graph.example.com'
  Assert-Rejected { Assert-DepoNeo4jConfiguration $neo -Production } 'non-TLS'
  $neo.NEO4J_URI = 'neo4j+s://user:password@graph.example.com'
  Assert-Rejected { Assert-DepoNeo4jConfiguration $neo } 'Invalid Neo4j URI'
  Set-Content -LiteralPath $envPath -Value 'DEPO_AUDIT_FIXTURE=read-only'
  $parsed = Read-DepoEnvironment $fixture $envPath
  if ($parsed.DEPO_AUDIT_FIXTURE -ne 'read-only' -or $env:DEPO_AUDIT_FIXTURE) { throw 'Reader changed process environment.' }
  Assert-Rejected { Assert-DepoSparkRuntime '' '' '' } 'absolute runtime path'
  $spark = Join-Path $fixture 'spark'; $java = Join-Path $fixture 'java'; $hadoop = Join-Path $fixture 'hadoop'
  foreach ($file in @('spark/bin/spark-submit.cmd','spark/python/lib/pyspark.zip','spark/python/lib/py4j-test-src.zip','spark/jars/spark-core_2.13-4.1.2.jar','java/bin/java.exe','hadoop/bin/winutils.exe','hadoop/bin/hadoop.dll')) {
    $target = Join-Path $fixture $file
    New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
    Set-Content -LiteralPath $target -Value ''
  }
  Set-Content -LiteralPath (Join-Path $java 'release') -Value 'JAVA_VERSION="21.0.1"'
  $env:DEPO_SPARK_OUTPUT_ROOT = Join-Path $fixture 'output'
  Assert-DepoSparkRuntime $spark $java $hadoop
  Set-Content -LiteralPath (Join-Path $java 'release') -Value 'JAVA_VERSION="11.0.1"'
  Assert-Rejected { Assert-DepoSparkRuntime $spark $java $hadoop } 'JDK 21'
  Set-Content -LiteralPath (Join-Path $java 'release') -Value 'JAVA_VERSION="21.0.1"'
  Remove-Item -LiteralPath (Join-Path $hadoop 'bin/hadoop.dll')
  Assert-Rejected { Assert-DepoSparkRuntime $spark $java $hadoop } 'hadoop.dll'
  Set-Content -LiteralPath (Join-Path $hadoop 'bin/hadoop.dll') -Value ''
  Remove-Item -LiteralPath (Join-Path $spark 'python/lib/py4j-test-src.zip')
  Assert-Rejected { Assert-DepoSparkRuntime $spark $java $hadoop } 'Py4J'
  Write-Output 'PASS: missing/duplicate configuration, atomic validation, explicit runtime paths, Java/Spark/Hadoop layout and missing native/Py4J checks.'
} finally {
  $env:DEPO_SPARK_OUTPUT_ROOT = $oldOutput
  $resolved = [IO.Path]::GetFullPath($fixture)
  if (-not $resolved.StartsWith([IO.Path]::GetFullPath($parent) + [IO.Path]::DirectorySeparatorChar)) { throw 'Unsafe fixture cleanup path' }
  if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}

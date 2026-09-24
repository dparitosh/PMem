# Shared configuration reader. Never prints values or changes machine environment.
function Read-DepoEnvironment([string]$Root, [string]$EnvFile) {
  $path = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $Root $EnvFile }
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing environment file: $path" }
  $seen = @{}
  foreach ($line in Get-Content -LiteralPath $path) {
    if ($line -match '^\s*(?:#.*)?$') { continue }
    if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { throw 'Invalid environment entry; use KEY=value without shell expressions.' }
    $key = $matches[1]; $value = $matches[2].Trim()
    if ($seen.ContainsKey($key)) { throw "Duplicate environment setting: $key" }
    $seen[$key] = $value
  }
  return $seen
}

function Import-DepoEnvironment([string]$Root, [string]$EnvFile) {
  $values = Read-DepoEnvironment -Root $Root -EnvFile $EnvFile
  foreach ($key in $values.Keys) { [Environment]::SetEnvironmentVariable($key, $values[$key], 'Process') }
}

function Assert-DepoNeo4jConfiguration([hashtable]$Values, [switch]$Production) {
  foreach ($key in @('NEO4J_URI','NEO4J_USER','NEO4J_PASS','NEO4J_DATABASE')) {
    if (-not $Values[$key] -or $Values[$key] -match '<.*>') { throw "Missing Neo4j setting: $key" }
  }
  $uri = $null
  if (-not [Uri]::TryCreate($Values.NEO4J_URI, [UriKind]::Absolute, [ref]$uri) -or
      -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -notin @('', '/') -or
      $uri.Scheme -notin @('neo4j','bolt','neo4j+s','bolt+s','neo4j+ssc','bolt+ssc')) {
    throw 'Invalid Neo4j URI. Configure credentials separately from the URI.'
  }
  if ($Production -and $uri.Scheme -notin @('neo4j+s','bolt+s')) {
    throw 'Production requires certificate-verified TLS: neo4j+s:// or bolt+s://.'
  }
}

function Assert-DepoSparkRuntime([string]$SparkHome, [string]$JavaHome, [string]$HadoopHome) {
  foreach ($entry in @(@('DEPO_SPARK_HOME',$SparkHome), @('DEPO_JAVA_HOME',$JavaHome), @('DEPO_HADOOP_HOME',$HadoopHome))) {
    if (-not $entry[1] -or -not [IO.Path]::IsPathRooted($entry[1])) { throw "$($entry[0]) must be an explicit absolute runtime path." }
  }
  foreach ($path in @((Join-Path $SparkHome 'bin/spark-submit.cmd'), (Join-Path $SparkHome 'python/lib/pyspark.zip'), (Join-Path $JavaHome 'bin/java.exe'), (Join-Path $HadoopHome 'bin/winutils.exe'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing Spark runtime component: $path" }
  }
  if (-not @(Get-ChildItem -LiteralPath (Join-Path $SparkHome 'python/lib') -Filter 'py4j-*-src.zip').Count) { throw 'Spark distribution is missing its matching Py4J archive.' }
  if (-not (Test-Path -LiteralPath (Join-Path $SparkHome 'jars/spark-core_2.13-4.1.2.jar'))) { throw 'Expected the Spark 4.1.2 / Scala 2.13 binary distribution.' }
  $javaRelease = Join-Path $JavaHome 'release'
  if (-not (Test-Path -LiteralPath $javaRelease) -or (Get-Content -LiteralPath $javaRelease -Raw) -notmatch '(?m)^JAVA_VERSION="21(?:\.|"|\+)') { throw 'The release baseline requires JDK 21.' }
  if (-not $env:DEPO_SPARK_OUTPUT_ROOT -or -not [IO.Path]::IsPathRooted($env:DEPO_SPARK_OUTPUT_ROOT)) { throw 'DEPO_SPARK_OUTPUT_ROOT must be an explicit absolute data path.' }
}

function Resolve-DepoSparkOptions([hashtable]$Overrides) {
  $EnableSpark = [bool]$Overrides['EnableSpark']
  $EnableNeo4jSparkConnector = [bool]$Overrides['EnableNeo4jSparkConnector']
  $EnablePipelineScheduler = [bool]$Overrides['EnablePipelineScheduler']
foreach ($key in @('DEPO_SPARK_ENABLED','DEPO_SPARK_NEO4J_ENABLED','DEPO_PIPELINE_SCHEDULER_ENABLED')) {
  $value = [Environment]::GetEnvironmentVariable($key, 'Process')
  if ($value -and $value -notin @('true','false')) { throw "Invalid boolean setting: $key" }
}
if (-not $Overrides.ContainsKey('EnableSpark')) { $EnableSpark = $env:DEPO_SPARK_ENABLED -eq 'true' }
if (-not $Overrides.ContainsKey('EnableNeo4jSparkConnector')) { $EnableNeo4jSparkConnector = $env:DEPO_SPARK_NEO4J_ENABLED -eq 'true' }
if (-not $Overrides.ContainsKey('EnablePipelineScheduler')) { $EnablePipelineScheduler = $env:DEPO_PIPELINE_SCHEDULER_ENABLED -eq 'true' }
if (($EnableNeo4jSparkConnector -or $EnablePipelineScheduler) -and -not $EnableSpark) { throw 'Spark connector and scheduler require Spark enabled.' }
  return @{ EnableSpark = [bool]$EnableSpark; EnableNeo4jSparkConnector = [bool]$EnableNeo4jSparkConnector; EnablePipelineScheduler = [bool]$EnablePipelineScheduler }
}

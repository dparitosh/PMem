# Shared configuration reader. Never prints values or changes machine environment.
function Read-DepoEnvironment([string]$Root, [string]$EnvFile) {
  $path = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $Root $EnvFile }
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing environment file: $path" }
  $seen = @{}
  $lineNumber = 0
  foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
    $lineNumber++
    if ($lineNumber -eq 1) { $line = $line.TrimStart([char]0xFEFF) }
    if ($line -match '^\s*(?:#.*)?$') { continue }
    if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
      throw "Invalid environment entry in '$path' at line ${lineNumber}. Use KEY=value; remove PowerShell commands, JSON, Markdown fences and wrapped value lines. The value is intentionally hidden."
    }
    $key = $matches[1]; $value = $matches[2].Trim()
    if ($value.StartsWith('"') -or $value.StartsWith("'")) {
      $quote = $value.Substring(0, 1)
      # Quotes are literal delimiters; never expand variables, escapes or code.
      $closingQuote = $value.LastIndexOf($quote)
      if ($closingQuote -lt 1 -or $value.Substring($closingQuote + 1).Trim() -notmatch '^(?:#.*)?$') {
        throw "Invalid quoted value for $key in '$path' at line ${lineNumber}. Close the quote on the same line. The value is intentionally hidden."
      }
      $value = $value.Substring(1, $closingQuote - 1)
    } else {
      # A hash without preceding whitespace belongs to the value (e.g. a URL).
      $value = ($value -replace '\s+#.*$', '').TrimEnd()
    }
    if ($seen.ContainsKey($key)) { throw "Duplicate environment setting: $key in '$path' at line ${lineNumber}. The value is intentionally hidden." }
    $seen[$key] = $value
  }
  return $seen
}

function Resolve-DepoRouting([hashtable]$Values) {
  $mode = [string]$Values['DEPO_ROUTING_MODE']
  $result = @{}
  if (-not $mode) { return $result } # Preserve existing explicit deployments.
  $mode = $mode.Trim().ToLowerInvariant()
  if ($mode -notin @('local','gateway')) { throw 'DEPO_ROUTING_MODE must be local or gateway.' }
  if ($mode -eq 'local' -and $Values['AUTH_MODE'] -ne 'token') { throw 'Local routing requires AUTH_MODE=token.' }
  $hostName = if ($Values['DEPO_LOCAL_SERVICE_HOST']) { $Values['DEPO_LOCAL_SERVICE_HOST'] } elseif ($Values['DEPO_SERVICE_HOST'] -and $Values['DEPO_SERVICE_HOST'] -notin @('0.0.0.0','::')) { $Values['DEPO_SERVICE_HOST'] } else { '127.0.0.1' }
  if ($mode -eq 'local' -and ($hostName -notmatch '^[A-Za-z0-9.-]+$' -or $hostName -in @('0.0.0.0','*'))) { throw 'DEPO_LOCAL_SERVICE_HOST must be a reachable IPv4 address or hostname without a port.' }
  $base = [string]$Values['DEPO_API_GATEWAY_URL']
  if ($mode -eq 'gateway') {
    $uri = $null
    if (-not [Uri]::TryCreate($base, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -notin @('http','https') -or -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $base -match '[<>\s\\]' -or $base -notmatch '^https?://[^/]') { throw 'DEPO_API_GATEWAY_URL must be a completed HTTP or HTTPS gateway base URL without credentials, query or fragment.' }
    $base = $base.TrimEnd('/')
    if ($Values['AUTH_MODE'] -eq 'entra' -and $uri.Scheme -ne 'https') { throw 'Entra gateway routing requires HTTPS.' }
  }
  $result['VITE_API_GATEWAY_URL'] = if ($mode -eq 'gateway') { $base } else { '' }
  $result['VITE_BACKEND_URL'] = ''
  $names = @('QIF','ONTOLOGY','AGENTIC','GRAPH','INGESTION','OSLC','CATALOG','DATA_PRODUCT','CEIM','DATA_PIPELINE')
  $paths = @('qif','ontology','agentic','graph','ingestion','oslc','catalog','data-products','ceim','data-pipeline')
  for ($i = 0; $i -lt $names.Count; $i++) {
    $path = if ($Values["DEPO_GATEWAY_$($names[$i])_PATH"]) { [string]$Values["DEPO_GATEWAY_$($names[$i])_PATH"] } else { $paths[$i] }
    if ($mode -eq 'gateway' -and ($path -notmatch '^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$' -or $path -match '(^|/)api/v1$')) { throw "Invalid gateway path for $($names[$i]); use relative segments without /api/v1." }
    $url = if ($mode -eq 'local') { "http://${hostName}:$(8010 + $i)" } else { "$base/$path" }
    $result["VITE_$($names[$i])_SERVICE_URL"] = $url
    $key = if ($names[$i] -eq 'CATALOG') { 'DATA_CATALOG_URL' } else { "$($names[$i])_SERVICE_URL" }
    $result[$key] = "$url/api/v1"
  }
  return $result
}

function Write-DepoBrowserRouting([string]$Root, [string]$EnvFile = '.env.local') {
  $values = Read-DepoEnvironment $Root $EnvFile
  $routing = Resolve-DepoRouting $values
  $browser = @{}
  foreach ($key in $routing.Keys) { if ($key.StartsWith('VITE_')) { $browser[$key] = $routing[$key] } }
  $dist = Join-Path $Root 'frontend/dist'
  if (-not (Test-Path -LiteralPath $dist -PathType Container)) { throw 'Build the frontend before writing runtime routing.' }
  $json = ConvertTo-Json -InputObject $browser -Compress
  $target = Join-Path $dist 'depo-runtime-config.js'
  $temporary = Join-Path $dist ('depo-routing-' + [guid]::NewGuid().ToString('N') + '.tmp')
  $backup = $temporary + '.bak'
  try {
    [IO.File]::WriteAllText($temporary, "window.DEPO_RUNTIME_CONFIG = $json;", (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $target) { [IO.File]::Replace($temporary, $target, $backup) } else { [IO.File]::Move($temporary, $target) }
  } finally {
    foreach ($leftover in @($temporary, $backup)) { if (Test-Path -LiteralPath $leftover) { Remove-Item -LiteralPath $leftover -Force } }
  }
  if ((Get-Item -LiteralPath (Join-Path $dist 'depo-runtime-config.js')).Length -eq 0) { throw 'Runtime routing file is empty.' }
}

function Import-DepoEnvironment([string]$Root, [string]$EnvFile) {
  $values = Read-DepoEnvironment -Root $Root -EnvFile $EnvFile
  # These aliases are one setting. Clear a previously imported alias when the
  # selected file explicitly configures the other, so Python cannot prefer it.
  if ($values.ContainsKey('DEPO_DATABASE_URL') -or $values.ContainsKey('DATABASE_URL')) {
    foreach ($databaseKey in @('DEPO_DATABASE_URL','DATABASE_URL')) {
      if (-not $values.ContainsKey($databaseKey)) { [Environment]::SetEnvironmentVariable($databaseKey, $null, 'Process') }
    }
  }
  $routing = Resolve-DepoRouting $values
  foreach ($key in $routing.Keys) { $values[$key] = $routing[$key] }
  foreach ($key in $values.Keys) { [Environment]::SetEnvironmentVariable($key, $values[$key], 'Process') }
  [Environment]::SetEnvironmentVariable('DEPO_ENV_INJECTED', 'true', 'Process')
}

function Assert-DepoNeo4jConfiguration([hashtable]$Values, [switch]$Production) {
  $authMode = if ($Values['NEO4J_AUTH_MODE']) { $Values['NEO4J_AUTH_MODE'].ToLowerInvariant() } else { 'token' }
  $tlsMode = if ($Values['NEO4J_TLS_MODE']) { $Values['NEO4J_TLS_MODE'].ToLowerInvariant() } else { 'required' }
  if ($authMode -notin @('token','none')) { throw 'NEO4J_AUTH_MODE must be token or none.' }
  if ($tlsMode -notin @('required','disabled')) { throw 'NEO4J_TLS_MODE must be required or disabled.' }
  foreach ($key in @('NEO4J_URI','NEO4J_DATABASE')) {
    if (-not $Values[$key] -or $Values[$key] -match '<.*>') { throw "Missing Neo4j setting: $key" }
  }
  if ($authMode -eq 'token') {
    foreach ($key in @('NEO4J_USER','NEO4J_PASS')) { if (-not $Values[$key] -or $Values[$key] -match '<.*>') { throw "Missing Neo4j setting: $key" } }
  }
  $uri = $null
  if (-not [Uri]::TryCreate($Values.NEO4J_URI, [UriKind]::Absolute, [ref]$uri) -or
      -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -notin @('', '/') -or
      $uri.Scheme -notin @('neo4j','bolt','neo4j+s','bolt+s','neo4j+ssc','bolt+ssc')) {
    throw 'Invalid Neo4j URI. Configure credentials separately from the URI.'
  }
  if ($Production -and $tlsMode -eq 'required' -and $uri.Scheme -notin @('neo4j+s','bolt+s')) {
    throw 'Production TLS mode requires certificate-verified TLS: neo4j+s:// or bolt+s://. For a trusted private on-premises network, explicitly set NEO4J_TLS_MODE=disabled, NEO4J_ENCRYPTED=false and use neo4j:// or bolt://.'
  }
  if ($tlsMode -eq 'disabled') {
    if ($uri.Scheme -notin @('neo4j','bolt')) { throw 'NEO4J_TLS_MODE=disabled requires a non-TLS neo4j:// or bolt:// URI.' }
    if ($Values['NEO4J_ENCRYPTED'] -ne 'false') { throw 'NEO4J_TLS_MODE=disabled requires NEO4J_ENCRYPTED=false.' }
  }
  if ($authMode -eq 'none' -and $uri.Scheme -notin @('neo4j','bolt')) { throw 'NEO4J_AUTH_MODE=none requires a non-TLS neo4j:// or bolt:// URI.' }
}

function Assert-DepoOslcConfiguration([hashtable]$Values, [switch]$Required) {
  $baseUrl = [string]$Values['OSLC_BASE_URL']
  if (-not $baseUrl -and -not $Required) { return }
  $uri = $null
  if (-not $baseUrl -or $baseUrl -match '[<>\s\\]' -or $baseUrl -notmatch '^https?://[^/]' -or
      -not [Uri]::TryCreate($baseUrl, [UriKind]::Absolute, [ref]$uri) -or
      $uri.Scheme -notin @('http','https') -or -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) {
    throw 'OSLC_BASE_URL must be a completed HTTP or HTTPS API base URL, for example http://10.10.12.21:8015. Do not include credentials, query parameters, fragments or placeholders.'
  }
}

function Assert-DepoSparkRuntime([string]$SparkHome, [string]$JavaHome, [string]$HadoopHome, [string]$OutputRoot = $env:DEPO_SPARK_OUTPUT_ROOT) {
  foreach ($entry in @(@('DEPO_SPARK_HOME',$SparkHome), @('DEPO_JAVA_HOME',$JavaHome), @('DEPO_HADOOP_HOME',$HadoopHome))) {
    if (-not $entry[1] -or -not [IO.Path]::IsPathRooted($entry[1])) { throw "$($entry[0]) must be an explicit absolute runtime path." }
  }
  foreach ($path in @((Join-Path $SparkHome 'bin/spark-submit.cmd'), (Join-Path $SparkHome 'python/lib/pyspark.zip'), (Join-Path $JavaHome 'bin/java.exe'), (Join-Path $HadoopHome 'bin/winutils.exe'), (Join-Path $HadoopHome 'bin/hadoop.dll'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing Spark runtime component: $path" }
  }
  if (-not @(Get-ChildItem -LiteralPath (Join-Path $SparkHome 'python/lib') -Filter 'py4j-*-src.zip').Count) { throw 'Spark distribution is missing its matching Py4J archive.' }
  if (-not (Test-Path -LiteralPath (Join-Path $SparkHome 'jars/spark-core_2.13-4.1.2.jar'))) { throw 'Expected the Spark 4.1.2 / Scala 2.13 binary distribution.' }
  $javaRelease = Join-Path $JavaHome 'release'
  if (-not (Test-Path -LiteralPath $javaRelease) -or (Get-Content -LiteralPath $javaRelease -Raw) -notmatch '(?m)^JAVA_VERSION="21(?:\.|"|\+)') { throw 'The release baseline requires JDK 21.' }
  if (-not $OutputRoot -or -not [IO.Path]::IsPathRooted($OutputRoot)) { throw 'DEPO_SPARK_OUTPUT_ROOT must be an explicit absolute data path.' }
}

function Assert-DepoSparkPostgresConfiguration([hashtable]$Values) {
  if (-not $Values.DEPO_DATABASE_URL -or $Values.DEPO_DATABASE_URL -match '<.*>') { throw 'DEPO_DATABASE_URL is required for Spark PostgreSQL JDBC.' }
  $driver = $Values.DEPO_SPARK_POSTGRES_DRIVER_JAR
  if (-not $driver -or -not [IO.Path]::IsPathRooted($driver) -or [IO.Path]::GetExtension($driver) -ne '.jar' -or -not (Test-Path -LiteralPath $driver -PathType Leaf)) {
    throw 'DEPO_SPARK_POSTGRES_DRIVER_JAR must be an existing absolute PostgreSQL JDBC .jar path.'
  }
}

function Resolve-DepoSparkOptions([hashtable]$Overrides) {
  $EnableSpark = [bool]$Overrides['EnableSpark']
  $EnableNeo4jSparkConnector = [bool]$Overrides['EnableNeo4jSparkConnector']
  $EnablePipelineScheduler = [bool]$Overrides['EnablePipelineScheduler']
  $EnablePostgresSparkConnector = [bool]$Overrides['EnablePostgresSparkConnector']
foreach ($key in @('DEPO_SPARK_ENABLED','DEPO_SPARK_NEO4J_ENABLED','DEPO_SPARK_POSTGRES_ENABLED','DEPO_PIPELINE_SCHEDULER_ENABLED')) {
  $value = [Environment]::GetEnvironmentVariable($key, 'Process')
  if ($value -and $value -notin @('true','false')) { throw "Invalid boolean setting: $key" }
}
if (-not $Overrides.ContainsKey('EnableSpark')) { $EnableSpark = $env:DEPO_SPARK_ENABLED -eq 'true' }
if (-not $Overrides.ContainsKey('EnableNeo4jSparkConnector')) { $EnableNeo4jSparkConnector = $env:DEPO_SPARK_NEO4J_ENABLED -eq 'true' }
if (-not $Overrides.ContainsKey('EnablePipelineScheduler')) { $EnablePipelineScheduler = $env:DEPO_PIPELINE_SCHEDULER_ENABLED -eq 'true' }
if (-not $Overrides.ContainsKey('EnablePostgresSparkConnector')) { $EnablePostgresSparkConnector = $env:DEPO_SPARK_POSTGRES_ENABLED -eq 'true' }
if (($EnableNeo4jSparkConnector -or $EnablePostgresSparkConnector -or $EnablePipelineScheduler) -and -not $EnableSpark) { throw 'Spark connectors and scheduler require Spark enabled.' }
  return @{ EnableSpark = [bool]$EnableSpark; EnableNeo4jSparkConnector = [bool]$EnableNeo4jSparkConnector; EnablePostgresSparkConnector = [bool]$EnablePostgresSparkConnector; EnablePipelineScheduler = [bool]$EnablePipelineScheduler }
}

param(
  [string]$EnvFile = ".env.local",
  [switch]$Production,
  [switch]$Bootstrap
)

$ErrorActionPreference = "Stop"
if ($Production -and $Bootstrap) { throw 'Choose either -Production or -Bootstrap, not both.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$path = Join-Path $root $EnvFile
if (-not (Test-Path $path)) { throw "Missing $EnvFile. Configure Neo4j connection settings through the customer secret manager." }

Get-Content $path | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ("Env:" + $matches[1].Trim()) -Value $matches[2].Trim() }
}

$required = @('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASS', 'NEO4J_DATABASE')
foreach ($name in $required) { if (-not (Get-Item -Path ("Env:" + $name) -ErrorAction SilentlyContinue).Value) { throw "Missing required Neo4j setting: $name" } }
if ($Production -and $env:NEO4J_URI -notmatch '^(neo4j\+s|neo4j\+ssc|bolt\+s)://') {
  throw 'Production requires a TLS Neo4j URI (neo4j+s://, neo4j+ssc://, or bolt+s://).'
}
if ($Production -and $env:NEO4J_URI -match 'localhost|127\.0\.0\.1') {
  throw 'Production Neo4j must use the customer-managed graph hostname, not a loopback URI.'
}

$python = Join-Path $root 'backend\.dt_venv\Scripts\python.exe'
& $python -c "from neo4j import GraphDatabase; import os; driver=GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASS'])); driver.verify_connectivity(); driver.execute_query('MATCH (n) RETURN count(n) AS count', database_=os.environ['NEO4J_DATABASE']); driver.close(); print('Neo4j release check passed.')"
if ($LASTEXITCODE -ne 0) { throw 'Neo4j release check failed.' }

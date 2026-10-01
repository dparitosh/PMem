param([string]$EnvFile = ".env.local", [switch]$Production, [switch]$Bootstrap)
$ErrorActionPreference = 'Stop'
if ($Production -and $Bootstrap) { throw 'Choose either -Production or -Bootstrap.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
Assert-DepoNeo4jConfiguration -Values $values -Production:$Production
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
$python = Join-Path $root 'backend/.dt_venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the backend environment before the Neo4j check.' }
Push-Location $root
try {
if ($Bootstrap) {
  & $python -m backend.depo_platform.neo4j_setup
} elseif ($Production) {
  & $python -m backend.depo_platform.neo4j_setup --check-only
} else {
  & $python -c "from neo4j import GraphDatabase; import os; auth=None if os.getenv('NEO4J_AUTH_MODE','token').lower()=='none' else (os.environ['NEO4J_USER'], os.environ['NEO4J_PASS']); driver=GraphDatabase.driver(os.environ['NEO4J_URI'], auth=auth, connection_timeout=10, max_transaction_retry_time=0); driver.verify_connectivity(); driver.execute_query('RETURN 1 AS connected', database_=os.environ['NEO4J_DATABASE'], routing_='r'); driver.close(); print('Neo4j connectivity/database read check passed.')"
}
if ($LASTEXITCODE -ne 0) { throw 'Neo4j connection check failed.' }
} finally { Pop-Location }

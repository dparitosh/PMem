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
& $python -c "from neo4j import GraphDatabase; import os; driver=GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASS']), connection_timeout=10, max_transaction_retry_time=0); driver.verify_connectivity(); driver.execute_query('RETURN 1 AS connected', database_=os.environ['NEO4J_DATABASE'], routing_='r'); driver.close(); print('Neo4j TLS/authentication/database read check passed.')"
if ($LASTEXITCODE -ne 0) { throw 'Neo4j connection check failed.' }

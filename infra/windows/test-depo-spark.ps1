param(
  [string]$EnvFile = '.env.local',
  [switch]$Neo4jConnector,
  [string]$SparkHome = $env:DEPO_SPARK_HOME,
  [string]$JavaHome = $env:DEPO_JAVA_HOME,
  [string]$HadoopHome = $env:DEPO_HADOOP_HOME,
  [string]$Master = $env:DEPO_SPARK_MASTER
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot 'runtime-config.ps1')
Import-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $PSBoundParameters.ContainsKey('SparkHome')) { $SparkHome = $env:DEPO_SPARK_HOME }
if (-not $PSBoundParameters.ContainsKey('JavaHome')) { $JavaHome = $env:DEPO_JAVA_HOME }
if (-not $PSBoundParameters.ContainsKey('HadoopHome')) { $HadoopHome = $env:DEPO_HADOOP_HOME }
if (-not $PSBoundParameters.ContainsKey('Master')) { $Master = $env:DEPO_SPARK_MASTER }
if (-not $Master) { $Master = "local[2]" }
Assert-DepoSparkRuntime $SparkHome $JavaHome $HadoopHome

$submit = Join-Path $SparkHome "bin\spark-submit.cmd"
$java = Join-Path $JavaHome "bin\java.exe"
$job = Join-Path $root "infra\spark\smoke_job.py"
if (-not (Test-Path $submit)) { throw "Spark submit command was not found: $submit" }
if (-not (Test-Path $java)) { throw "Java runtime was not found: $java" }
if (-not (Test-Path $job)) { throw "Spark smoke job was not found: $job" }
if (-not (Test-Path (Join-Path $HadoopHome 'bin\winutils.exe'))) {
  throw "Windows Hadoop helper was not found under $HadoopHome. Use an approved runtime distribution."
}

$env:SPARK_HOME = $SparkHome
$env:JAVA_HOME = $JavaHome
$env:HADOOP_HOME = $HadoopHome
$env:PATH = (Join-Path $HadoopHome 'bin') + ';' + $env:PATH
$env:PYSPARK_PYTHON = Join-Path $root "backend\.dt_venv\Scripts\python.exe"
if (-not (Test-Path $env:PYSPARK_PYTHON)) { throw "DEPO Python runtime was not found: $env:PYSPARK_PYTHON" }

$env:PYSPARK_DRIVER_PYTHON = $env:PYSPARK_PYTHON
if ($Neo4jConnector) {
  $values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
  Assert-DepoNeo4jConfiguration -Values $values
  if (-not $env:DEPO_SPARK_NEO4J_PACKAGE) { throw 'Configure DEPO_SPARK_NEO4J_PACKAGE before connector verification.' }
  & $submit --master $Master --packages $env:DEPO_SPARK_NEO4J_PACKAGE (Join-Path $root 'infra/spark/neo4j_connector_smoke.py')
} else {
  & $submit --master $Master $job
}
if ($LASTEXITCODE -ne 0) { throw "DEPO Spark smoke job failed." }
Write-Host "DEPO Spark smoke job passed."

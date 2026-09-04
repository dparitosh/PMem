param(
  [string]$SparkHome = $env:DEPO_SPARK_HOME,
  [string]$JavaHome = $env:DEPO_JAVA_HOME,
  [string]$Master = $env:DEPO_SPARK_MASTER
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $SparkHome) { $SparkHome = "D:\DEPO\runtime\spark-4.2.0-bin-hadoop3" }
if (-not $JavaHome) { $JavaHome = "D:\DEPO\runtime\jdk-21\jdk-21.0.12.1+1" }
if (-not $Master) { $Master = "local[2]" }

$submit = Join-Path $SparkHome "bin\spark-submit.cmd"
$java = Join-Path $JavaHome "bin\java.exe"
$job = Join-Path $root "infra\spark\smoke_job.py"
if (-not (Test-Path $submit)) { throw "Spark submit command was not found: $submit" }
if (-not (Test-Path $java)) { throw "Java runtime was not found: $java" }
if (-not (Test-Path $job)) { throw "Spark smoke job was not found: $job" }

$env:SPARK_HOME = $SparkHome
$env:JAVA_HOME = $JavaHome
$env:PYSPARK_PYTHON = Join-Path $root "backend\.dt_venv\Scripts\python.exe"
$env:DEPO_SPARK_OUTPUT_ROOT = if ($env:DEPO_SPARK_OUTPUT_ROOT) { $env:DEPO_SPARK_OUTPUT_ROOT } else { "D:\DEPO\data\spark" }
if (-not (Test-Path $env:PYSPARK_PYTHON)) { throw "DEPO Python runtime was not found: $env:PYSPARK_PYTHON" }

& $submit --master $Master $job
if ($LASTEXITCODE -ne 0) { throw "DEPO Spark smoke job failed." }
Write-Host "DEPO Spark smoke job passed."

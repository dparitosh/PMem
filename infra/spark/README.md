# Spark and PySpark provisioning

Spark is optional for normal API/frontend operation and required for enabled
Spark data jobs. The DEPO release baseline is Spark 4.1.2, Scala 2.13 and JDK 21.
Apache documents Java 17/21 and Python 3.10+ support for this Spark version;
DEPO's application installer requires Python 3.11+. See the
[official Spark 4.1.2 documentation](https://spark.apache.org/docs/4.1.2/).

## Provision the runtime

1. Obtain the approved Spark 4.1.2 Hadoop 3 binary distribution from
   [Apache Spark](https://spark.apache.org/downloads.html) and JDK 21 from the
   customer's approved vendor. Verify their published signatures/checksums and
   record the exact versions and hashes with the customer release.
2. Extract/install them into customer-selected absolute directories. Retain
   Spark's full `bin`, `jars`, and `python/lib` trees. Its `pyspark.zip` and matching
   `py4j-*-src.zip` supply the Python runtime; no separate `pip install pyspark`
   is needed or supported by this packaged-distribution setup.
3. For the current Windows scripts, provision the approved Hadoop helper bundle
   containing `bin/winutils.exe` and any vendor-required native DLLs. Do not fetch
   unsigned helper binaries from arbitrary repositories. If the customer has no
   approved Windows Hadoop runtime, Spark delivery remains blocked; do not
   bypass the startup check.
4. Grant the service account read/execute access to the binaries and write
   access to a dedicated Spark output directory. Configure storage retention,
   memory/CPU limits and monitoring for the agreed workload.
5. Merge only needed keys from `config/spark.env.example` into root `.env.local`.
   Set `DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`, `DEPO_HADOOP_HOME` and
   `DEPO_SPARK_OUTPUT_ROOT` to actual absolute paths. The templates contain
   placeholders, not machine-specific defaults. Set `DEPO_SPARK_MASTER` to the
   agreed master (`local[2]` for the initial bounded smoke test).

## Verify before enabling jobs

Install the application's Python environment first, then run from project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local
if ($LASTEXITCODE -ne 0) { throw 'Spark smoke test failed; do not enable jobs.' }
```

The script loads the selected environment file, checks Spark/PySpark/Py4J/JDK
layout and runs the actual DataFrame smoke job using `backend/.dt_venv`.
Success requires four expected records and a zero process exit code. Save the
result in the acceptance record. Configuration checks alone are not execution
verification.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -Profile Production -EnableSpark
if ($LASTEXITCODE -ne 0) { throw 'Spark-enabled application startup failed.' }
```

Use `-Profile Bootstrap` for a restricted token-authenticated bootstrap setup.
Add `-EnablePipelineScheduler` only when scheduled execution is required.
`-EnableNeo4jSparkConnector` additionally requires graph credentials and access
 to an approved Maven repository/cache for the configured connector artifact.
Validate the connector separately and retain its result:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local -Neo4jConnector
if ($LASTEXITCODE -ne 0) { throw 'Neo4j connector smoke test failed.' }
```

The equivalent environment flags are `DEPO_SPARK_ENABLED`,
`DEPO_SPARK_NEO4J_ENABLED` and `DEPO_PIPELINE_SCHEDULER_ENABLED` (`true`/`false`).
Explicit command switches override their corresponding file values. Connector
and scheduler require Spark enabled; environment-based enabling also runs runtime
validation. Update existing keys when merging templates; duplicate keys fail validation.

## Operational boundary

The API currently owns a lazy local Spark session and bounded synchronous job
execution. Do not claim a durable asynchronous queue or automatic distributed
cluster provisioning. Jobs publish through governed service boundaries; Spark
executors must not bypass graph-publication authorization. A production workload
needs capacity, failure-recovery and retention tests beyond this smoke job.

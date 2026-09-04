# Optional Spark execution plane

Spark is the DEPO batch/stream processing runtime for large source volumes. It
is not a dependency of the React frontend or DEPO request-serving services.

## Local verification

1. Copy `.env.spark.example` values into the process environment if using a
   non-default location.
2. From the repository root run:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1
```

The smoke job validates the pinned Java runtime, Spark launcher, PySpark
runtime, and a minimal CEIM-shaped DataFrame transformation.

## Integration boundary

Scheduled Spark jobs should read approved source artifacts, write normalized
and provenance-bearing outputs to `DEPO_SPARK_OUTPUT_ROOT`, and publish only
through the existing ingestion, ontology, and graph service APIs.  Do not embed
Spark sessions in FastAPI request handlers.

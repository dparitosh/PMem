# Data Flow — jobs, quality, and execution evidence

**Outcome:** Demonstrate governed job definitions, durable execution, data
quality, replay, publication, and operational visibility.

**Readiness:** PostgreSQL schema is current; `data-pipeline-worker` is running;
an approved job exists. Spark is required only for a Spark-backed job.

## Talk track and clicks

1. Open **Data Flow** and refresh telemetry.
2. Review the live quality bar and worker status.
3. Select a versioned definition and explain approval, enablement, retry policy,
   schedule, and input contract.
4. Run an approved job and follow it from queued to terminal status.
5. Open **Run evidence** to show quality results, artifacts, checkpoints, and
   lineage. Replay only with the approved execution key.
6. Publish a qualified result and show the retained outcome.

**Evidence to call out:** worker heartbeat, run ID, definition version, input
digest, accepted/rejected counts, checkpoints, output artifacts, and errors.

**Key message:** Execution is durable and reviewable even when Spark is disabled.

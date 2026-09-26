# Release audit

Release branch: `codex/semantic-bridge-release`

## Verified

- Working tree is clean and the branch is aligned with `origin`.
- Frontend production build completes with Vite.
- `git diff --check` passes.
- Data Flow routes health, telemetry, definitions, runs, replay, execution, and publication through the data-pipeline service.
- Semantic publication is restricted to completed CEIM-compatible runs.
- Pipeline quality and workflow status remain visible when Zeppelin is unavailable.
- Backend pipeline Python modules compile in the release environment where Python is available.

## Operational requirements

- Configure PostgreSQL, Neo4j, Spark, CEIM, and data-pipeline service URLs in the target environment.
- Configure the appropriate execution and publication approval tokens, or use a trusted gateway identity.
- Run the customer-environment smoke checks in [`INSTALLATION.md`](../INSTALLATION.md) before release acceptance.

## Known release limitations

- Zeppelin is an optional analysis surface; the frontend uses pipeline telemetry for operational status.
- Live updates use bounded polling rather than SSE/WebSocket streaming.
- The Vite build reports large bundle chunks; this is a performance follow-up and does not block functional release validation.

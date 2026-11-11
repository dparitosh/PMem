# Local workflow and connector acceptance — 1 November 2026

Scope: requested items 1, 2, 3 and 5. Customer deployment verification was excluded. No LLM, credential rotation, database reset, new publication or external connector account was used.

## Source and deployment

Baseline 76c4dbb, connector/performance implementation 867f5aa, registry responsiveness/startup diagnostics 6903203 and async compatibility 7c12d59 were committed and pushed to codex/windows-setup-audit-fixes. The local D:/GenAI_Projects/Apps/PMem deployment was upgraded with per-file backups and unchanged .env.local hash. The normal installer verified schema/indexes and started ten services and three workers. A later frontend-only correction clears stale run details immediately when the run URL changes.

The initial upgrade attempt exposed an ingestion read-access timeout. Synchronous graph registry work was moved into the thread pool while preserving the awaited helper contract used by merge previews. Startup diagnostics no longer describe non-authentication verification failures as rejected keys. The retry passed startup and browser-session checks.

## Executed checks

- Combined backend regression group: 110 passed across connector, REST deadline, dependency isolation, durable worker, controls, recovery and ingestion responsiveness tests. Actual Parquet, Arrow and disposable SQLite reads and a real bounded acquisition child were exercised. A slow HTTP response fixture was interrupted at its absolute deadline; worker/recovery failures were simulated without invoking an LLM.
- Frontend focused groups: 95 passed across ten files; the additional late-run-inspector regression then passed in the 15-test Data Flow suite. Total distinct focused coverage is 96 tests. Tests cover lost acknowledgements, duplicate submissions, late reconnect responses, authorization polling stops, recovery, first-visit mounting and retained tab state.
- Production Vite build passed. Data Products route chunk decreased from 103,796 to 23,284 bytes; this defers heavy panels and removes the data-grid chunk from immediate route imports. It does not reduce total application size by 78%. The shared runtime chunk warning remains.
- New optional connector installer passes PowerShell syntax parsing. Its SDK lock validation does not install unreviewed packages automatically.

## Browser observations against the deployed local app

| Workspace | Observed behavior |
|---|---|
| Change Control | 44 retained evidence records; AP242 Structural Inventory inspection shows authorization, publication and catalog delivery separately. No new approval was issued. |
| Data Flow | API responding, Spark disabled, one worker; 83 retained runs; bounded run list and historical query-string run selection work. A stale inspector during link loading was discovered and corrected. |
| Ontology Junction | AP242 selected automatically; 500-term slice loads with total and truncation disclosure. Semantic Bridge lists 14 retained imported instances. Merge review selects two named ontologies, explains reviewer identity and keeps publication disabled before review. No agent was executed. |
| Metadata Registry | Eight governed assets load. Teamcenter dictionary loads scoped descriptions and 25-term pagination. A later timed-out registry read was visible; access revalidation recovered and the dictionary then loaded. This is not a claim of an endurance or latency SLA. |
| Data Catalog | Two published versions load; Catalog presence says Registered instead of a blank delivery cell. |
| Data Products | Available analytics and Product portfolio load on first visit; two retained packages remain, including AP242 Structural Inventory with owner Paritosh. Existing pending processing references are preserved. |
| Admin sources | Seventeen ingestor kinds are visible; the additional connector panel offers profile/resource selectors. No enterprise profiles are configured locally, and acquisition is disabled with explicit setup guidance. |

A second local browser tab connected successfully. Revalidating access in the catalog kept both tabs online. Navigation and selection were exercised using the UI. Slow network, simultaneous write, expired-access and interrupted-worker paths were tested in automated fixtures; no live customer worker was deliberately interrupted and no browser publication write was used as a test.

## Remaining verification boundary

All source paths are implemented, but real Databricks, Snowflake, mail, MCP, cloud and Kafka connectivity remains unaccepted until operators configure their connections and reviewed SDK locks. Local read-only navigation is not an end-to-end customer ingestion/publication acceptance certificate. No clean isolated customer installation or production load/endurance benchmark was performed in this task.

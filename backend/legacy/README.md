# Legacy monolith retirement boundary

`backend/main.py` remains a compatibility host for routes that have not yet
moved to standalone services. New backend work must target the owning service
listed in `infra/deployment/services.json`; that manifest is the complete and
authoritative production inventory.

Do not delete a legacy route merely because an equivalent service exists.
First migrate its frontend consumer to the corresponding OpenAPI service,
verify the service contract using local tests, then remove the route in a separately
reviewable change. This protects existing user workflows during the gradual
cutover.

## Cleanup completed 2026-10-17

- Retired document upload routes retain HTTP 410 responses; unreachable direct-indexing implementations were removed. Governed document jobs remain active.
- The old PLMXML direct-write CLI and separate QIF worker are retirement shims with migration guidance. Neither connects to Neo4j nor starts workflow execution.
- Removed the unreferenced session-ID helper and duplicate XMI parser. Active ingestion continues to use `backend.Services.xmi_parser.XMIParser`.
- Legacy mapping handlers have distinct Python names while preserving their URL paths.

The original removed/replaced files were copied into the local, Git-ignored `external/excluded-review/2026-10-17-code-cleanup/` folder for inspection. Git history also retains the originals. Historical audit evidence and modules still consumed by tests or supported scripts were preserved.

The former stage 4-7 simulator is now a retirement shim: estimated enrichment, load and health outputs cannot report success. Its obsolete comprehensive test is archived; real RDF/SHACL validation and mapping-integrity regressions remain maintained. UI-consumed compatibility routes stay in their standalone service owners until an explicit consumer migration.

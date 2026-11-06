# MBSE governed imports

Submit model files to `POST /api/v1/governed-import` on the ingestion service,
with an approved `job_id` and `job_version`.

* SysML v1: use `profile=sysml-v1` with XMI. `.xmi` selects this profile automatically.
* SysML v2: use `profile=sysml-v2` with a JSON array of repository elements, or
  `{ "elements": [...] }`. Generic JSON requires the explicit profile.

Both adapters normalize into CEIM using versioned mapping packs and retain the
source artifact through the existing governed job path. They do not write the graph.
Element IDs, names, original attributes and type names are retained. Requirements
are canonical requirements; other model elements currently use Resource with their
original model type retained. Containment and source/target trace links are mapped.
Duplicate IDs and unresolved extracted links reject the import.

This is initial model interchange support, not full SysML language conformance.
SysML v2 textual syntax (`.sysml`) and incremental synchronization remain pending.
Port typing, behavior semantics and complete vendor profile coverage
require further mapping and representative customer model acceptance tests.

ReqIF now resolves nested SOURCE/TARGET references, retains the VALUES XML, and
maps specification hierarchy. Typed attribute interpretation remains pending.

## Repository commit import

The ingestion service exposes `POST /api/v1/sysml-v2/import-commit`.
Configure `SYSML_V2_API_ENABLED=true`, `SYSML_V2_API_BASE_URL`,
`SYSML_V2_PROJECT_ID`, `SYSML_V2_COMMIT_ID`, and the repository credential
`SYSML_V2_API_TOKEN`. Supply the data-job execution approval and optional
`job_id` / `job_version` in the request body.

The connector reads `/projects/{projectId}/commits/{commitId}/elements`, follows
Link pagination only within the same commit endpoint, and rejects cycles and
oversized results. The retained snapshot includes project and commit identifiers.
This is a full commit snapshot, not incremental synchronization or deletion replay.
Pagination and credential isolation are tested with HTTP mocks; live repository
acceptance remains outstanding. Legacy aggregate-server readiness routes are separate.

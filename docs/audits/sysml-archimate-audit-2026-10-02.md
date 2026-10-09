# SysML and ArchiMate correctness audit — 2026-10-02

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

## Findings

| Priority | Component | Defect and consequence | Required correction |
|---|---|---|---|
| P1 | SysML v2 adapter | JSON scalar/null roots reach `data.get`, raising AttributeError rather than a controlled validation error. The import route catches ValueError, not this exception. | Validate document shape before accessing elements; return a descriptive ValueError/422. |
| P1 | SysML v2 adapter | Non-string IDs reach duplicate detection and reference validation; list/dict IDs raise TypeError. Array-valued types can raise TypeError in relationship lookup and misclassify requirements. | Validate non-empty scalar IDs; normalize explicitly supported type representations or reject unsupported types with ValueError. Validate reference IDs too. |
| P1 | ArchiMate parser | Duplicate element IDs append multiple rows and overwrite the index entry. Relationship resolution then selects the last element silently. | Validate uniqueness across elements, folders and views, with explicit errors for conflicting identifiers; validate relationship identifiers independently. |
| P2 | ArchiMate import | Dangling relationship endpoints are omitted and reported only in parser statistics. No consumer of unresolved_relationship_count was found outside tests. A partial graph can proceed without an explicit completeness gate. | Keep preview diagnostics but block commit unless references resolve or a deliberate partial-import policy is approved. |
| P2 | SysML repository ingestion | Pages are bounded to 16 MiB and element/page counts are bounded, but there is no aggregate byte budget while fetching. The application upload limit is checked after the complete snapshot is retained and serialized. | Apply a cumulative byte budget during streaming and before accumulating each page. |
| P2 | SysML v2 service integration | Status/integration-plan routes exist in backend/routes/sysml_v2_routes.py but are not included in the standalone ingestion app. Routing to ingestion alone cannot make these endpoints available. | Mount the readiness router at the owning service and add route-contract tests. |
| P2 | SysML frontend | No frontend call to the commit-import endpoint was found. The backend repository workflow therefore has no guided frontend project/commit execution path. | Add a repository import UI with configuration/readiness, execution authorization and durable job feedback. |
| P2 | SysML reference validation | Endpoint membership uses a list for each link, producing O(elements × links) work on repository snapshots that allow up to 100000 elements. | Use an ID set for reference membership while preserving deterministic output order. |

## Reproduction and scope

Actual SysML adapter function code was executed with a stub CEIM normalizer:
a scalar JSON document raised AttributeError, a list-valued ID raised TypeError,
and an array-valued relationship type raised TypeError. These failures occur
before CEIM normalization.

Actual ArchiMate parser code was executed against trusted minimal fixtures with
standard ElementTree substituted for the unavailable defusedxml dependency solely
for this semantic reproduction. It accepted two conflicting elements with the
same identifier and returned a dangling relationship as a statistic while omitting
it from relationships. This does not test the production XML security parser.

Positive controls in source: production XML parsing uses defusedxml; SysML
pagination rejects redirects/off-origin or different-commit next links and limits
page size/count; SysML normalization rejects duplicate scalar IDs and unresolved
references; verification relationship direction is reversed deliberately for
VERIFIED_BY; ArchiMate preserves folders, views, junctions and relationship
attributes. SysML repository import dispatches through governed data jobs rather
than publishing directly.

This audit did not change SysML/ArchiMate application code. Full dependency-backed
parser tests, live repository requests and frontend/Neo4j acceptance remain
unverified after the requested workstation cleanup. Native .sysml/.kerml textual
parsing and complete ArchiMate XSD/metamodel conformance are not established by
these adapters.


## Fixes applied

All eight findings have local corrections: strict SysML document/ID/type/reference
validation; set-based endpoint checks; ArchiMate identifier uniqueness and missing
view/folder diagnostics; a completeness gate before both queued and synchronous
publication; cumulative repository streaming byte limits; mounted standalone
readiness routes; and an Import → SysML repository UI using execution credentials
and durable run feedback. Readiness descriptions now reflect the governed commit
import capability. Repository readiness probes reject HTTP redirects.

Five dependency-free regression tests execute the actual adapter/parser/reader
code with stub CEIM/HTTP and trusted XML fixtures. They cover controlled validation
errors, type normalization and satisfaction direction, duplicate IDs, preview versus
commit completeness and a cumulative two-page download budget. Production XML
security, full frontend build and live repository/Neo4j acceptance are still unverified.


## Second audit corrections

Readiness and integration-plan endpoints now require graph-read identity. Project
probes validate their response shape and byte limit, report invalid/truncated JSON
as a failure, and omit project payload previews. Repository configuration rejects
invalid URLs. The frontend clears previous configuration before refreshing and
guards async state updates after unmount. ArchiMate commit gating also recognizes
legacy file_format/file_type metadata. Regression tests include legacy metadata
and malformed, non-array and oversized probe responses. Live integration and
frontend build remain unverified.


## Compatibility regression check

A malformed IPv6 repository URL could still crash status rendering because URL
masking ran outside configuration validation. The mask now returns an empty URL
for invalid configuration, including URLs containing embedded credentials. Added
regression assertions cover malformed IPv6, credential-bearing URLs and non-URLs.
Intentional behavior changes: readiness requires GRAPH_READ_TOKEN, incomplete
ArchiMate models cannot be committed, and the default SysML aggregate snapshot
limit is 64 MiB (configurable). Existing customers must restart services and rebuild
the frontend to consume the changed contracts. Live and build checks remain pending.


## Dependency-backed frontend verification

The production Vite build passed on 2026-10-02. Six shell/import workflow tests
and three new SysML repository UI tests passed with the installed frontend
runtime. Tests cover validated read access, separate ontology upload credentials,
execution authorization, durable run feedback, stale readiness after a failed
refresh and rejection of responses without a run ID. Existing test expectations
were updated for the changed authentication contract. Vite reported large chunks
and the test library reported a React act deprecation; neither failed verification.
Temporary npm/runtime dependency files were removed after verification. The built
frontend output was retained locally. Live customer services, actual repository
requests, database/graph publication and worker execution remain unverified.

# Microservices review — 2026-10-22

## Verified inventory and live baseline

The authoritative inventory remains `infra/deployment/services.json`: ten API listeners on 8010–8019, and three managed workers. Read-only live baseline probes succeeded for all ten services at `/healthz`, `/readyz`, `/openapi.json` and `/odata/$metadata`. Every live OpenAPI response declares 3.0.3. PostgreSQL and Neo4j were ready wherever declared. The schema-set service deliberately owns file-backed task storage and declares no database readiness dependency. Empty business datasets do not indicate a listener failure.

All thirteen API/worker entry points passed the existing dependency-profile import guard. This proves their imports/OpenAPI contracts can run without borrowing packages outside their reviewed profile; it does not prove every external integration or worker job succeeds. Reviewed locks were checked for closure and unchanged release pins. No third-party dependency versions were upgraded.

## Corrections

| Boundary | Finding | Final behavior |
|---|---|---|
| Graph/Agentic → Ontology policy | In-process policy adapter borrowed the ontology engine; isolated consumers could fail | Bounded authenticated HTTP to the existing Ontology policy API; operation, decision digest and result shape checked. Ontology-owned merge checks evaluate locally, avoiding a self-call/thread-pool deadlock |
| Ingestion policy response | New no-policy response could be misread as rejection; import hardcoded approved/100% confidence | Engineering and profile imports distinguish absent policies from failures, send flagged import evidence and preserve quality/lifecycle approval. Legacy compliance-only peers are accepted only with a strict boolean pass during rolling upgrades |
| GraphQL → jobs/products | Direct GET inherited proxy settings and lacked aggregate deadline/response bounds | Existing shared peer transport, active read credential, operation deadline and bounded response reads; sanitized recoverable errors |
| Pipeline speed path → CEIM | Direct publication call could inherit proxies, buffer arbitrary response size and trust status alone | Shared bounded transport; verify ontology/publication identity and graph receipt counts. Failure retains the reconciliation and does not auto-resubmit |
| SysML commit pagination | Per-request timeout could restart for every page; ambient proxy inherited | Whole-snapshot deadline plus phase limits, existing aggregate byte/page/element limits and same-commit pagination restrictions; timeout returns dependency-unavailable rather than an internal error |
| OSLC remote | Overall deadline expiry could become 500; peer exception text exposed details | Deadline expiry maps to recoverable 503; public dependency errors are sanitized; configured timeout uses shared finite bounds |
| Common request correlation | Arbitrary client text could be retained/reflected as a request ID | Preserve bounded opaque ASCII IDs; generate a UUID for invalid or oversized input |
| Service URLs | Placeholder/wildcard hosts, zero ports and encoded control characters were accepted | Reject these configurations before peer dispatch |
| Artifact storage | Deep Windows paths could create a folder but fail writing atomic artifact files | Use Windows extended filesystem paths while preserving content hashes, containment and usage references; native deep-path regression test |

The policy API now supports a bounded batch (1–2000 decisions) for a known operation. Individual evaluation remains supported. Mixed individual/batch bodies, exceptions in a batch and unknown operation names are rejected. Shared service calls do not forward browser credentials or expose server keys to the frontend.

## Validation and deployment limits

The final selected regression suite passed **158 tests plus 143 subtests**, with five non-failing warnings. Regression coverage includes the real policy batch API, empty-policy import flow, missing/invalid evidence, total SysML deadline, receipt mismatch, CEIM timeout/oversized response retention, request correlation, URL validation, actual registration retry/publication boundaries and Windows artifact integrity. Older extraction-only fixtures were corrected to exercise current runtime boundaries instead of stale function shapes.

This source update requires restarting the affected services through the supported checked updater. The updater stages verified files, backs up current source and checks tracked process ownership before shutdown. It does not rotate credentials, stop PostgreSQL/Neo4j, delete retained history or approve/publish domain data. Shared/isolated runtime selection, commands and timeout settings are documented in `INSTALLATION.md`; no new installer or database schema migration is introduced.

The live baseline was collected before this update. Final customer acceptance still needs the deployed update and representative ontology/import/link/recommendation workflows with real domain data. Listener readiness and isolated tests are not a full business-workflow certification.

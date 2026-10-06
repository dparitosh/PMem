# Legacy and current implementation review — 2026-10-03

Scope: repository entry points, deployment manifest, Windows frontend startup, browser configuration, frontend authentication/contract discovery, and installation/architecture references. This is a cross-component review of coexistence risks, not a line-by-line certification of every file or a customer-VM test.

## Corrected findings

| Priority | Finding | Correction |
|---|---|---|
| P1 | Vite browser-prefix credential policy omitted generic TOKEN and subscription-key names; filtering process.env alone does not stop Vite exposure. | Reject credential-shaped VITE_/REACT_APP_ setting names before build/dev configuration, without logging values. |
| P2 | Frontend freshness check covered src only, missing environment, public assets, build configuration and package manifests. | Include those inputs in launcher timestamp validation; block stale startup with rebuild instruction. |
| P2 | API access verification queried Neo4j and relied on imported metadata; generic rejection hid missing configuration/header/key mismatch. | Dedicated protected graph access endpoint, explicit entered read key, distinct error reasons and frontend/backend version mismatch message. |
| P2 | Plugin/application guide claimed synchronous execution and absence of durable queue despite deployed pipeline worker. | Document worker mode, persisted run IDs/status, outbox distinction and compatibility inline mode. |
| P3 | README described one worker; production manifest defines two. | Align worker inventory. |
| P3 | Compatibility hosts and workbench references could suggest aggregate backend is the customer target. | Label aggregate entry points; point workbench to standalone ontology host and installation to root orchestrator. |

## Retained compatibility and remaining limitations

- main.py/backend/main.py still have test callers; removal requires migrating those callers and proving their supported-service equivalents.
- REACT_APP_ configuration aliases and legacy BACKEND_URL remain compatibility surfaces. Current runtime VITE_ routing overrides build settings when provided. Do not maintain conflicting aliases; the supported launcher and service manifest define customer topology.
- Neo4j core legacy .env fallback retains override=False: it can fill absent process settings. It remains a separate explicit migration task; injected settings take precedence but missing values may still be supplied by an old file.
- Frontend freshness checks compare timestamps, not a signed/content-hash release manifest. Deployment tools preserving timestamps need a clean rebuild; source removal and environment injected only at build time are not fully covered.
- The screenshot's graph 403 and ingestion timeout are not reproduced against the customer VM. Error distinction helps isolate them; it does not prove a customer token mismatch or fix unavailable ingestion resources.
- XSD structural analytics artifacts remain reviewable schema-design products; warehouse instance materialization and approved schema deployment remain pending.

## Verification

15 dependency-light Python checks passed for graph access, OpenAPI credentials, package boundaries, service URLs and gateway scope. Node executes the actual Vite config with stubbed environment/provider functions and verifies four prohibited credential-name cases plus public/server variable separation. Updated frontend launcher parses as PowerShell. Release package validation passed: 46 PowerShell scripts, 21 documented paths, ten services, two workers, 202 locked Python distributions and eight PostgreSQL migration files. No dependencies installed; full React/Vite build, runtime UI tests and live PostgreSQL/Neo4j/APIM checks were not run in this review.

No application files deleted. Commit and push status is recorded in Git.

## Configuration cleanup follow-up — 2026-10-06

Removed the unused OntologyStudioPage alias, SiemensPrimitives wrappers and
OntologyWorkspaceHeader after checking frontend import references. The active
OntologyJunctionPage and legacy aggregate host remain because they have callers.
Consolidated Ollama URL normalization through core/ollama_auth.py.

Managed and production launches now skip legacy dotenv loading in the LLM,
graph, graph embeddings, schema cleaner, XMI converter, PLMXML converter and
aggregate compatibility host. Unmanaged development retains override=False
loading. This prevents absent injected values being silently populated from
old files; it does not synchronize database credentials or alter customer files.
Dependency-light regression checks execute the loader guards for managed mode,
each supported production environment variable and development fallback. Full
service imports and customer connectivity still require runtime validation.


## Follow-up fixes

Closed the legacy Neo4j fallback gap for managed Windows launches and production profiles; unmanaged development fallback remains. Vite now rejects conflicting VITE_/REACT_APP_ aliases. Build emits a SHA-256 input receipt; Windows startup verifies the file set and every hash, including deleted files and timestamp-preserving copies. Rebuild once to create the receipt. This supersedes the timestamp-only and managed fallback limitations above. Build-only inherited environment and output integrity/signing remain outside filesystem receipt verification.

Verification: seven focused Python checks passed; Node verified credential rejection/alias conflicts and the receipt over 148 current build inputs; both updated PowerShell scripts parse; installation-package validation passed. Full Vite/React build and live customer VM validation remain unperformed because frontend dependencies are absent. No package installation or uninstallation performed. Commit and push status is recorded in Git.


## Frontend discovery follow-up

Fixed failed refresh deleting credential mappings: contracts now replace atomically after response parsing/validation, and same-root failures retain previous operation/profile metadata with an explicit message. Root changes discard the old contract. Fixed insertion-order matching by selecting the longest matching service-root path before matching operations. Fixed full-body size buffering with a 5 MiB streaming byte ceiling, Content-Length early rejection and reader cancellation/lock release. Node regression checks execute the actual registry/discovery sources and cover nested ownership, unavailable/invalid refresh retention including profile visibility, root changes, successful refresh, oversized bodies, header rejection and UTF-8. Full browser/Vite testing remains pending.

# Listener, browser access and semantic validation review

Date: 2026-10-28. Scope: current PMem code and the local installation at `D:\GenAI_Projects\Apps\PMem`. LLM generation is disabled. This is a targeted cross-layer review, not a guarantee that all customer networks or all application paths are qualified.

## Confirmed findings and changes

| Severity | Source | Root cause, reproduction and impact | Resolution |
|---|---|---|---|
| P2 | `frontend/src/contexts/OntologyContext.js:144` | Revalidate access dispatched `depo:access-verified`, which emptied the registry before pending reads completed. Reproduced with a deferred read followed by ERR_NETWORK: retained ontology disappeared. Dependent selectors could lose context. | Revalidation now refreshes without clearing the prior list. Expiry, changed credentials/identity, sign-out and explicit cleanup still clear it. Regression failed before the change and passes afterward. |
| P2 | `infra/deployment/test-depo-deployment.ps1:121` | The diagnostic checked the first origin on a simple health GET only. A second origin or authenticated OPTIONS failure could escape deployment verification. | Execute preflight for every configured origin and validate origin, POST and required request headers. The check sends no credential or write. |
| P2 | `infra/deployment/test-browser-routing.mjs:39` | Harness substitutions no longer matched the current serviceAuth imports and Bridge dependencies. Running it failed before credential-forwarding checks, despite an earlier routing PASS line. | Updated isolated fixtures and reject unresolved imports explicitly. All three routing/auth/Bridge groups now execute and pass. This harness does not test renewal; dedicated renewal tests do. |
| P3 | `frontend/src/utils/apiErrorMessage.js:30` | ERR_NETWORK grouped CORS, listener and connectivity problems without identifying the target. That error cannot establish an invalid key or a precise transport root cause. | Distinguish browser offline and HTTPS-to-HTTP configuration; otherwise identify only the safe endpoint origin and disclose ambiguity. Never echo URL credentials/query strings. |
| Capability gap | `backend/ontology_service/semantica_adapter.py:55` | Semantica's structural validator does not execute full OWL-DL consistency reasoning. Parser success cannot close this gap. | Capability contract explicitly declares RDFLib backend, structural/SHACL scope and unsupported full OWL-DL consistency. No false consistency claim or silent reasoner installation. |

## Robustness assessment

The service factory applies exact-origin CORS around correlation/error handling; allowed clients can read request IDs even on service failures. Unlisted origins are rejected. CORS is a browser read boundary, not authentication, firewall policy or protection against direct non-browser calls. API writes still require their own credential scope.

The local broker enforces loopback client/host/origin checks, its launcher cookie, configured delegation scopes, bounded bodies and timeouts. The previous two-second authority timeout was fixed in DEP-01; the slow real-loopback-authority regression remains part of this test run. Public/gateway mode must use its configured authentication flow rather than exposing the local broker remotely.

Routes assign the native ontology catalog to ontology and the retained registry to ingestion. Reads have request budgets, cancellation and bounded retries; writes are not automatically replayed. The registry merges partial successes with a warning and backs off failed background polls. A readable catalog alone does not prove the ingestion registry or retained files are healthy.

Listener identity and environment fingerprint checks prevent unsafe reuse of unrelated/stale processes. They cannot repair DNS, firewall, customer proxy, APIM forwarding or TLS configuration. The exact reported customer ERR_NETWORK root cause is still unconfirmed without a failing request/response from that network. See the ordered diagnostics in `INSTALLATION.md`.

## Executed verification

- 48 backend cases passed: CORS allow/deny and error correlation, broker origin/scope/slow authority, central security, network bounds and Semantica runtime contracts. Two RDFLib N3 deprecation warnings remain.
- 70 frontend cases passed: registry revalidation/cleanup/cancellation, mixed content/offline/redacted errors, request deadlines, session expiry/renewal, local bootstrap and routing. React test-utils deprecation warnings remain.
- Windows routing fixture passed local, gateway, legacy and invalid configuration cases.
- Dependency-free browser routing harness passed all ten service routes, gateway subscription scoping and Bridge credential forwarding.
- Live local checks: all ten APIs returned readiness 200; twenty service/origin preflight pairs passed for the two configured origins; all ten rejected an unlisted origin. This server-side check does not emulate a browser's DNS/firewall/TLS path from a customer workstation.

After deployment, managed Production endpoint/OpenAPI/CORS validation and the delegated-session diagnostic passed. A fresh browser loaded AP242 taxonomy (6,379 classes and 3,621 properties); revalidation retained that ontology and reloaded the same counts with verified API access. The production build is `/assets/index-BhgQovmp.js`; installed backend hashes match the workspace and all 345 frontend build inputs match the build receipt. Customer configuration and LLM-disabled settings were retained.

One immediate post-start combined readiness/CORS probe failed its assertion before its failed-pair details were saved. Its exact service and cause are unknown. The probe was corrected to retain failed pairs before asserting; the subsequent final matrix had no failed pairs. This is an unresolved intermittent observation, not evidence that the earlier failure was fixed or that customer-network availability is guaranteed.

Evidence: `transport-semantic-2026-10-28/backend-tests.xml`, `frontend-tests.xml`, `live-transport.json` and `cleanup.json` in this audit directory. Deployment/build verification is recorded in that evidence directory after application restart.

## RDFLib versus Semantica and the consistency gap

Keep RDFLib. Installed Semantica 0.6.7 imports it for ontology generation/export and SHACL graph validation. PMem also uses it for retained RDF parsing, namespaces, RDF lists, SPARQL, JSON-LD and graph projection. Removing it would break these contracts, including OSLC representations and ontology export. It is a direct reviewed dependency in `backend/requirements.txt` and the hash-locked dependency files; Owlready2 remains removed from supported PMem source imports and dependency profiles.

The installed validator's `_load_reasoner()` does not load a deductive reasoner. A regression supplies `<urn:item>` as a member of two disjoint classes: structural processing succeeds but `consistency_verified` and `deductive_reasoner_executed` remain false. This tests honest reporting, not contradiction detection.

Full OWL-DL needs a qualified adapter: validate the supported profile; resolve only approved immutable import artifacts; run a suitable reasoner in an isolated process with memory/deadline bounds; return consistent/inconsistent/unknown/unsupported plus artifact/import hashes and diagnostic evidence. Test disjoint-class membership, unsatisfiable classes, cardinality/equality, datatype restrictions, missing imports and process failure before making publication depend on the result. SHACL and OWL-RL rule closure are useful additional checks but are not substitutes for unrestricted OWL-DL consistency. This adapter remains unimplemented; no release claim should imply otherwise.

Primary references checked against installed source: [Semantica validator](https://github.com/semantica-agi/semantica/blob/main/semantica/ontology/ontology_validator.py), [Semantica ontology documentation](https://github.com/semantica-agi/semantica/blob/main/docs/reference/ontology.md), [RDFLib](https://rdflib.dev/). Upstream main can differ from the pinned release; the installed 0.6.7 source is the qualification basis.

## Cleanup boundary

Removed disposable workspace Vite audit caches and their duplicate configs, the hardcoded one-off projection benchmark, old release-test fixture directories, old workspace installation logs and generated test-output logs. `cleanup.json` lists exact paths, file counts and bytes. Kept current test evidence, original audit findings/captured fixtures, deployment rollback backups, customer configuration, retained import snapshots, ontology artifacts, database contents and active service logs. Deleting import snapshots or agent history is a product maintenance operation, not source cleanup. No retention policy was changed.

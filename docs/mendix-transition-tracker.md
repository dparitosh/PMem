# Mendix and Graph Miner Transition Tracker

Updated: 2026-07-14  
Status values: `DONE`, `IN PROGRESS`, `PLANNED`, `BLOCKED`  
Requirements source: `docs/mendix-graph-miner-requirements-plan.md`
Embedded Teamcenter source: `docs/mendix-teamcenter-embedded-integration.md`

## Qualification Work Packages

| ID | Work package | Status | Evidence | Remaining gate |
|---|---|---|---|---|
| QH-01 | Isolate graph rendering/mining from Graph Explorer | DONE | `GraphVisualizationWidget`, pure `D3NetworkGraph`, `graphMiner.js`, common graph contract | Customer-dataset parity smoke in Mendix sandbox |
| QH-02 | Isolate Ontology Junction presentation rules | DONE | `utils/ontologyPresentation.js`; legacy import remains compatible | Rebuild page with Mendix-native tabs during transition |
| QH-03 | Isolate Import intent/status rules | DONE | `workflows/importPresentation.js`; polling remains in legacy page | Rebuild queue/progress UI as Mendix pages |
| QH-04 | Add page/browser smoke coverage | DONE | App navigation boundary test plus `page-navigation-smoke.e2e.spec.js` | Execute against target customer dataset and Mendix sandbox |
| QH-05 | Automate frontend/OpenAPI classification | DONE | `scripts/frontend_api_contract.py` and pytest regression | Keep in CI on every endpoint/config change |
| QH-06 | Standardize component/page naming | DONE | `OntologyJunctionPage`, `RecommendationsPage`, compatibility exports | Remove compatibility exports after downstream migration |
| QH-07 | Build, secure, and package Mendix widget | DONE | Mendix widget source, locked dependencies, compiler build, release `.mpk` | Studio Pro install and Marketplace scans |

## Delivery Backlog

| ID | Requirement | Status | Owner | Dependency / acceptance |
|---|---|---|---|---|
| MX-001 | Install private `.mpk` in Mendix 11.12 sandbox | PLANNED | Mendix team | Studio Pro project and deployment access |
| MX-002 | Create server-side DEPO connector and secret configuration | PLANNED | Mendix/API | Customer identity provider and environment URLs |
| MX-003 | Map graph response into node/link JSON contract | PLANNED | Mendix team | MX-002 |
| MX-004 | Configure node-select microflow variables | PLANNED | Mendix team | MX-001, MX-003 |
| MX-005 | Implement Atlas UI shell and navigation | PLANNED | Mendix UX | Approved page inventory |
| MX-006 | Transition Graph Explorer read-only workflow | PLANNED | Mendix/graph | MX-001 through MX-005 |
| MX-007 | Transition Model Workbench editable workflow | PLANNED | Mendix/modeling | Save semantics and optimistic locking decision |
| MX-008 | Transition Ontology Junction tabs | PLANNED | Mendix/ontology | Extracted presentation rules and ontology APIs |
| MX-009 | Transition Import queue and durable-job polling | PLANNED | Mendix/import | Durable document/import job APIs |
| MX-010 | Transition metadata, reports, requirements, where-used, recommendations | PLANNED | Mendix/product | Page-by-page parity acceptance |
| MX-011 | Transition governed Admin actions | PLANNED | Security/operations | Step-up authorization and confirmation design |
| GM-001 | Ship client-side neighborhood/path/component/degree mining | DONE | Graph team | Unit regressions pass |
| GM-002 | Define async server-side mining request/result API | PLANNED | Graph/API | Algorithm and data-scope approval |
| GM-003 | Implement community detection and similarity | PLANNED | Graph team | Neo4j GDS availability/license decision |
| GM-004 | Implement frequent-pattern candidate mining | PLANNED | Graph/data science | Representative datasets and minimum-support rules |
| GM-005 | Persist mining jobs/results with provenance | PLANNED | API/governance | Artifact retention policy |
| GM-006 | Save mined subgraph as Mendix GraphView | PLANNED | Mendix/graph | GM-002, domain model |
| SEC-001 | Threat model connector, widget, and graph actions | PLANNED | Security | Target auth topology |
| SEC-002 | Generate SBOM/license/vulnerability reports | IN PROGRESS | DevSecOps | Run in release pipeline; React Flow MIT, D3 ISC verified |
| QA-001 | Studio Pro design/runtime smoke | PLANNED | QA | MX-001 |
| QA-002 | Accessibility audit | PLANNED | QA/UX | Mendix page implementation |
| QA-003 | 1k/5k-node and large-link performance test | PLANNED | QA/graph | Customer-like datasets |
| QA-004 | Parallel-run parity and rollback exercise | PLANNED | QA/operations | All transitioned pages |

## Teamcenter Embedded Integration Backlog

| ID | Requirement | Status | Owner | Dependency / acceptance |
|---|---|---|---|---|
| TC-001 | Confirm Teamcenter 2512 and Active Workspace customization access | PLANNED | Teamcenter administration | Supported instance, licenses, build/redeploy access |
| TC-002 | Obtain Teamcenter Connector 2606 early access or wait for publication | BLOCKED | Siemens/Mendix account team | Required connector is documented but not yet published |
| TC-003 | Add and configure the Mendix Embedded navigation profile | PLANNED | Mendix team | Studio Pro 11.12 project |
| TC-004 | Register the Mendix app with TcSS and configure SSO/user provisioning | PLANNED | IAM/Teamcenter/Mendix | TC-001 and application registration authority |
| TC-005 | Configure exact-origin CORS, cookie settings, HTTPS, and Active Workspace CSP | PLANNED | Platform/security | Approved Teamcenter and Mendix origins |
| TC-006 | Pass stable Item/ItemRevision UID through embedded startup parameters | PLANNED | Teamcenter/Mendix | TC-003 and Active Workspace component customization |
| TC-007 | Install TcConnector and create the separate DEPO_Teamcenter extension module | PLANNED | Mendix/Teamcenter | Compatible connector package |
| TC-008 | Implement Teamcenter context retrieval and connector error handling | PLANNED | Mendix/Teamcenter | TC-004, TC-006, TC-007 |
| TC-009 | Implement DEPO contextual-graph mapping and Graph Miner page data source | PLANNED | Mendix/DEPO | MX-002 through MX-004 and TC-008 |
| TC-010 | Implement governed Teamcenter write-back with confirmation and audit | PLANNED | Product/Teamcenter/security | Approved mutation use cases |
| TC-011 | Validate embedded SSO, fallback, CSP/CORS, graph performance, and rollback | PLANNED | QA/security | TC-001 through TC-010 |

## Decisions Required

| ID | Decision | Due before | Status |
|---|---|---|---|
| DEC-01 | Confirm Mendix 11.12 versus a supported Mendix 10 LTS target. | MX-001 | OPEN |
| DEC-02 | Confirm whether “Graph Miner” is the DEPO capability defined here or a named third-party product. | GM-002 | OPEN; DEPO capability is current assumption |
| DEC-03 | Select Mendix server-side connector authentication: OAuth2 client credentials, delegated user token, or trusted gateway. | MX-002 | OPEN |
| DEC-04 | Confirm Neo4j GDS availability and license for server-side algorithms. | GM-003 | OPEN |
| DEC-05 | Decide private distribution versus public Mendix Marketplace submission. | SEC-002 | OPEN |
| DEC-06 | Decide whether the embedded public beta is acceptable or production waits for the Mendix 11.18/Teamcenter 2612 GA baseline. | TC-002 | OPEN |
| DEC-07 | Confirm which Teamcenter object types and structures are projected into Neo4j and their refresh/write-back policy. | TC-008 | OPEN |

## Progress Summary

- Qualification baseline: 7 of 7 work packages implemented in the repository.
- Mendix delivery backlog: 0 completed, 11 planned; requires a target Mendix project and customer authentication decisions.
- Graph Miner: client baseline complete; 5 server/persistence items planned.
- Teamcenter embedded integration: architecture baselined; 10 planned items and 1 connector-publication blocker.
- External blockers: no Studio Pro project, customer IdP configuration, Neo4j GDS decision, or customer acceptance dataset is present in this workspace.

## Verified Baseline — 2026-07-14

| Gate | Result |
|---|---|
| Frontend production build | PASS; compiled successfully without warnings |
| Frontend unit/regression suite | PASS; 58 tests |
| Backend unit/regression suite | PASS; 180 tests, 6 environment-dependent skips |
| Frontend/OpenAPI classification | PASS; 146/146 backend endpoint defaults matched, 6 external agentic endpoints classified |
| Chromium page navigation | PASS; all 10 pages at desktop and narrow viewport |
| Mendix TypeScript build and release | PASS; `depo.graphminer.DepoGraphMiner.mpk` generated |
| Mendix production dependency audit | PASS; 0 vulnerabilities |

These results qualify the repository baseline. Studio Pro installation, customer-data performance/parity, authentication integration, accessibility audit, and Marketplace governance remain delivery/acceptance gates rather than unresolved defects in the seven work packages.

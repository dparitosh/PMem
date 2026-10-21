# Enterprise audit remediation — 2026-10-20

This records corrections after `enterprise-full-stack-2026-10-20.md`. The original report remains the baseline audit. These are source/package corrections; the installed frontend and backend have not been replaced or restarted by this remediation run.

| Finding | Correction and verification | Remaining acceptance |
|---|---|---|
| F01 | Updated LangChain to 0.3.30, Core to 0.3.86 and packaging to 25.0. Retrieved wheel metadata/hashes, checked the shared dependency closure, regenerated Windows service locks, and tested the isolated candidate overlay. `pip check` passes. Serialization regressions exercise escaped user dictionaries and explicit denial of environment-secret loading. | Install into clean shared/isolated customer environments; perform a complete transitive advisory assessment. The installed live runtime still has the previous dependencies. |
| F02 | Requirement filtering classifies source format separately from original provenance, before pagination. Legacy source values/MBSE aliases remain filterable. The corrected query was executed read-only against the existing graph: 106 total requirements, 94 PLMXML requirements; pagination and provenance retention checked. Six classification fixtures also passed in Neo4j. | Repeat through the installed UI after deployment. |
| F03 | Explicit review/committing/failure states outrank numerical progress. Completion requires an explicit outcome. Restored commits at 100% remain resumable; approval pauses remain paused. Instance-link candidates use this classification. Export controls require a completed ontology workflow. | Exercise retained imports and interrupted publication through the installed UI. |
| F04 | Installation guide now explicitly marks fresh Linux application installation unavailable until its reviewed Linux lock is supplied. Existing-runtime lifecycle support is distinguished from fresh installation. | A Linux release lock and clean Linux acceptance remain outstanding. No Windows wheel hashes were reused for Linux. |
| F05 | App tests await the browser-access boundary. Schema dependency tests import the real helper and hardened XML parser. Agent tests isolate session, telemetry and retained job stores; recovery fixtures explicitly select process execution; request fixtures satisfy current contracts. Authorization assertions remain in place. | The expanded selected backend suite is green, but this is not a full backend repository run or every-integration acceptance. |
| F06 | Removed duplicate local fallback scoring and inaccurate server-search messages. Unmatched searches visibly explain the bounded snapshot. Session reset clears the feedback. | Installed UI verification after deployment. |
| F07 | Merge review retains up to 200 explicit pairs, displays each source/target identity, supports scoped removal/clearing, and replaces an alternative target for the same source. Changes invalidate the previous preview. Approval remains separate. | Multi-pair merge preview/approval acceptance against customer ontologies after deployment. |
| F08 | MCP child stderr is continuously drained in 4 KiB chunks. Only byte count, exit status and allowlisted failure categories are logged; raw child text is discarded. Tested a child producing over 100 KiB of stderr, including a fake secret, without leaking it. Session lifecycle/progress tests pass. | Actual external MCP server acceptance is still required. |
| F09 | Added accessible names to the requirement source filter and imported-instance selector. | Target-browser accessibility review after deployment. |
| F10 | Refreshed the guarded combined upgrade payload and validated its manifest against the installed files. Prior pin and line-ending differences were checked before updating expected hashes. | Still open: apply the package, restart, and verify live build/source parity. |
| F11 | Removed legacy prompt assumptions about motor assemblies, Sugar Plant and fixed ontology prefixes. Queries must use the supplied schema and explicit user scope. | Legacy-host acceptance if that migration host is used. |
| F12 | README now lists all three deployed workers. | None for this documentation correction. |

## Evidence

Evidence is retained in the workspace `outputs/enterprise-audit-2026-10-20`:

- `backend-remediation-full.log` / XML: 144 passed, 18 subtests passed across the expanded 23-file isolated selection.
- `dependency-candidates/tests-final.log`: 39 passed, 10 subtests passed for dependency/profile/provider/serialization/MCP checks.
- `dependency-candidates/pip-check.log`: no broken requirements in the candidate overlay.
- `dependency-candidates/resolve-report.json`: package-index dependency resolution evidence; reviewed existing release pins were retained except the three listed changes.
- `requirement-live-read-validation.json` and `requirement-query-validation.json`: read-only Neo4j verification.
- `frontend-remediation-final.log`: all 500 tests pass across 90 frontend files. `frontend-remediation-build.log`: production build passes; Vite retains its large-chunk advisory.
- `dependency-candidates/integration-imports.log`: OpenAI, Ollama, Neo4j, LangGraph and legacy prompt imports pass with the candidate dependency overlay. This is not an external provider call.
- `package-preflight.json` / `package-validation.log`: guarded upgrade validation. Validation does not install or restart anything.

The 0.3 Core line retains compatibility defaults for direct deserialization. No first-party direct loader path was found in the baseline audit. The new regression explicitly disables environment-secret loading; it does not claim that every third-party loader becomes safe automatically. See the [maintainer advisory](https://github.com/langchain-ai/langchain/security/advisories/GHSA-c67j-w6g6-q2cm).

## Deployment boundary

The existing customer launcher remains `outputs/Setup-DEPO.cmd`; its refreshed combined package preserves environment files and databases and uses expected-content hashes. Do not use an older copied package. Deployment, clean-machine acceptance, external models/integrations, backup restoration, rollback and production-scale testing remain release gates. Passing the selected tests does not certify the entire enterprise deployment.


## Post-install retest

The user subsequently completed the administrator-run installer. All 112 original payload entries matched the installed files; patched LangChain versions and `pip check` were verified in the live environment. All ten service readiness endpoints returned HTTP 200/ready. UI checks confirmed 94 PLMXML requirements, scoped taxonomy counts (0 before selecting an ontology; 2,788 classes for the selected Teamcenter version, with 800 hierarchy rows explicitly labeled as a limited slice), and visible unmatched-search feedback.

A retained instance-link preview completed with two ambiguous candidates, zero applied links and committed=false. No merge or mapping approval was performed. This does not validate publication.

The AP242-to-QIF merge preview failed with HTTP 504 after the generic 90-second request deadline. Source already contained a merge-specific QoS budget, but it was absent from the original patch payload. A wider runtime parity comparison found five differing files and one missing helper. The combined package now includes those six files and four associated test files (122 entries total). Twelve focused tests and 20 subtests passed, and package ValidateOnly passed. This follow-up package still needs installation and UI retesting; the merge is not certified fixed in the live runtime.

Further UI observations: the instance-preview summary renders source/target-kind objects as `[object Object]`; the Import workspace source-instance selector remains unnamed for assistive technology. These are retained as follow-up issues, not hidden by the successful checks. Evidence: `post-install-validation.json`, `runtime-parity-followup.json`, `deployment-gap-tests.log`, `package-validation-followup.log`, and `merge-timeout-deployed.png` in the evidence bundle.


## Second deployment and large-merge limit

The second administrator-run installation was verified: all 122 manifest entries match and the reported frontend asset is `index-CJyqiE2y.js`. Installed merge preview HTTP admission is 210 seconds; unrelated ontology reads remain at 90 seconds. The previous 90-second HTTP cutoff is corrected.

The UI AP242 to QIF retry still failed, now with HTTP 422 near the configured 180-second preparation/validation worker limit (request ID `562c730e-24ec-4f4f-a7af-3b12be6f5563`). A separate read-only diagnostic used the same retained sources and in-memory preparation, without catalog saves or graph publication. Source sizes were 19,694,233 and 3,506,977 bytes. Metadata parsing took 17.89 and 3.14 seconds; candidate matching completed in 20.47 seconds. The last phase was full semantic validation, which did not complete within the overall 600-second diagnostic cap; its child process was terminated at that cap. This is not proof of semantic conformance or of eventual completion at a larger limit.

The unresolved release blocker is large-graph SHACL/OWL-RL validation cost and its coupling to mapping-preview delivery. Recommended remediation is durable staged validation with progress and retained results, independent candidate review, and publication blocked until validation for the exact immutable plan completes. Simply disabling validation or blindly raising timeouts is not a verified fix. No mappings or merged ontology were approved or published.

Additional corrections are staged in source only: direct merge errors now return allowlisted timeout explanations without upstream text/secret leakage; import summaries serialize structured counts; source-instance and ontology selectors have accessible names. Twenty-five focused backend tests, 19 import routing tests and the frontend build pass. These changes are not in the already installed 122-file package, and that installer should not be rerun merely to repeat the same large-merge failure. Evidence: `post-install-validation-v2.json`, `merge-phase-profile.log`, `merge-error-tests.log`, `import-summary-usability-tests.log`, `import-usability-build.log`, and `merge-validation-deadline.png`.


## Durable interactive merge remediation

The interactive merge path now enqueues a PostgreSQL job and returns promptly. The ontology service lifespan owns its worker; no extra customer service or launcher was added. Preparation retains the scored mapping plan before SHACL/OWL-RL validation. The UI polls status, displays candidates while validation is pending, and can resume the retained review for the same sources and mapping selections after a refresh. Changed source, mapping or credentials invalidate stale UI results. Automated legacy workflows retain their synchronous contract.

Publication requires a completed job token and a receipt bound to the proposed Turtle digest, current source artifact digests, validation code/dependency versions and current SHACL artifacts. Pending, failed, nonconformant or modified plans cannot be approved. Background reasoning has an independent 1800-second default budget (configurable up to 7200); service shutdown terminates only its owned child and restart reuses the prepared plan. Queue admission is bounded; failed jobs remain inspectable and a corrected request creates a fresh review. The backend requires central PostgreSQL storage for this interactive mode.

Validation: all 501 frontend tests across 90 files passed; 76 merge/agent backend tests and 2 subtests passed, including a real SHACL/OWL-RL child, restart checkpoint reuse, pending approval rejection, receipt-token mismatch, changed sources/graphs/policies and child shutdown/deadline handling. Production Vite build passed. The complete upgrade package passed ValidateOnly. The installed AP242/QIF end-user validation still requires deployment and a live rerun; these checks do not establish semantic conformance of those large ontologies. No mapping approval or graph publication was performed.

## Installed background review retest and preparation payload correction

The administrator installation was verified against all 134 manifest entries. Ontology readiness reported PostgreSQL and Neo4j ready. The browser initially showed registry loading/degraded access; revalidating the existing API session restored the ontology choices. An AP242 source / QIF target review using the authorized test reviewer returned a retained background job immediately. Approval stayed disabled. The job subsequently failed with `Semantic validation evidence exceeds its limit`; the UI displayed the failure and did not permit approval.

Root cause: the shared owned-child helper applied its 8 MiB semantic-report cap to preparation results containing a full serialized ontology. The helper now distinguishes the two fixed worker modules. Semantic reports retain the 8 MiB cap; prepared graph results have a bounded cap derived from the configured ontology upload limit plus bounded review evidence. Unsupported worker modules are rejected. A regression test accepts a 9 MiB preparation result while rejecting the same oversized semantic report. All 77 merge/agent tests and 2 subtests passed after the correction.

A read-only diagnostic against the actual AP242 and QIF artifacts completed preparation in 106.2 seconds: 356,352 statements, 147 mapping suggestions and 22,477,137 Turtle bytes, with zero declaration conflicts. SHACL/OWL-RL remained explicitly pending. No retained jobs, source changes, approvals or graph publications were written by that diagnostic. Evidence: `large-preparation-size-fix.json` and `merge-preparation-size-failure.png`. The size correction is staged in the updated package; the installed background worker still requires that update and a subsequent live semantic-validation retest.

## Full installed large-graph validation outcome (2026-10-21)

The next installation matched all 134 package files. AP242/QIF job `5fa0ea18-d633-4865-a4bc-bb05060365a8` retained its 356,352-statement plan and displayed 147 mapping proposals in the UI. Pagination and refresh/resume recovered the same review without creating another job. The matching report explicitly warns that its 100,000-comparison candidate search is bounded; proposals are not exhaustive. All ten services remained ready during validation, with sampled readiness latency at most 2.31 seconds.

The semantic child consumed CPU continuously and approximately 1.1 GiB resident memory. It did not complete within its 1800-second budget. The retained job transitioned to failed, its owned child exited, mappings remained retained, and approval stayed disabled. No merged artifact or graph publication was created. This is a failed large-graph validation test, not evidence of conformance. Raising the limit alone is not a verified performance fix. Large-graph SHACL/OWL-RL performance remains a release blocker. Evidence: `large-validation-terminal-result.json`, `readiness-during-large-validation.json`, `ap242-qif-mapping-proposals-live.png`, and `ap242-qif-validation-timeout.png`.

Two additional correctness issues were identified during the run. First, the AP242 retained SHACL file is identical to the generated default editorial rules; QIF has no separately retained SHACL artifact. The retained default file incorrectly targeted inferred built-ins such as owl:Thing and owl:Nothing, causing a valid annotated one-class fixture to fail with 24 results, while the identical inline rules passed. Source now scopes exactly recognized generated defaults to submitted declarations, with Windows newline normalization, matching inline behavior. Custom SHACL target semantics and full OWL-RL inference remain unchanged. The expanded backend suite passed 79 tests and 2 subtests. This does not establish QIF-specific business-rule coverage.

Second, pressing Resume again for an already pending job advanced the stale-response guard without restarting the same-job poll effect. Its UI could remain at validating after the server had failed; explicit Resume displayed the terminal result. Source now restarts the poll generation on a successful resume, and adds a pending-to-failed same-job resume regression. These corrections are staged separately from the installed 134-file runtime; the large-graph performance blocker is still unresolved.


### Large ontology merge validation — 2026-10-21

The merge validator retains full OWL-RL inference. Blank-node membership uses an indexed collection while preserving rule execution and iteration order. SHACL evaluates all constraints and retains complete result counts and core result triples; text and UI samples are bounded, and unrelated focus-node graph neighborhoods are not copied into reports.

Recognized generated metadata rules check authored declarations with class-expression typing context. Custom semantic constraints still evaluate the full inferred graph. These profiles are shown separately in the merge review. Warnings remain blocking under the existing policy.

Read-only AP242/QIF diagnostics covered 356,352 asserted triples. Full inference completed in 335 seconds and produced 778,270 triples. A separate validation run using a hash-verified inference checkpoint completed in 91 seconds including checkpoint restoration; this is a component measurement, not a newly deployed end-to-end UI pass. The corrected profiles found 260 violations and 30,181 metadata warnings. Direct inspection confirmed all 260 violations are missing ranges on datatype properties in the retained QIF artifact. Regenerate and review that ontology from its original schemas before approval; installation does not repair or publish existing ontologies automatically.

Validation: 112 backend tests with 31 subtests and 13 focused frontend tests passed. Deployment and the final live UI retest remain pending. Apply the complete upgrade package using Setup-DEPO.cmd (option 1) from the administrator Windows session; do not delete environment files or databases.


### QIF schema projection and draft browsing — 2026-10-21

QIF schema generation now resolves global element/attribute references before assigning property kinds and ranges. Unresolved references/types stop generation rather than producing range-less datatype properties. Named simple types remain datatype declarations; list-valued properties preserve XML lexical text as xsd:string, with explicit source-validation limitations. No list is asserted equivalent to its scalar item type. Domain classes and owner-scoped properties use source namespace IRIs. Element/type QName collisions retain separate identities.

Schema projection uses deterministic declared terms rather than heuristic class inference and repeated multi-format exports. Indexed owner lookup avoids scanning the declaration list for every property. The complete 16-file user QIFLibrary generated 56,092 triples, 2,532 classes, 2,400 object properties and 1,055 datatype properties in 8.28 seconds including inspection, serialization and a verification parse. Every property has a range. The source schema closure compiles successfully; one existing warning is retained. Full OWL-RL/default SHACL validation of this candidate completed in 56.42 seconds with zero findings and no conflicts reported by PMem's conflict checker. XSD facets, identity constraints, list item/order constraints and compositor semantics still require source XSD validation; this is not proof of semantic equivalence or full OWL-DL consistency.

The candidate was registered through the Import UI in register-only mode as `qif3_1005424112c749fe`, named QIF 3.0 Library — Corrected Source Projection 2026-10-21. Existing publications were retained. Do not substitute it silently for the previously published QIF ontology.

Draft vocabulary inspection now uses local RDFLib extraction when optional Owlready2 is absent or cannot load the retained RDF. It does not execute a deductive reasoner or depend on Neo4j publication. Anonymous expressions are excluded from named class lists. Dictionary rows preserve distinct IRIs with identical human labels. Source-code read-only measurement of the registered candidate returned all 5,987 class/property terms in 3.641 seconds initially and 0.265 seconds from the existing inspection cache. These browsing code changes require deployment.

Checks: 52 backend tests and nine subtests passed; 20 focused frontend tests and the production frontend build passed. New converter/browsing code is included in the complete upgrade package. Run the existing Setup-DEPO.cmd option 1 from the administrator Windows session to deploy it. The registered candidate artifact was tested against the currently deployed validator; generating future QIF drafts through the new converter requires this code update.


Live combined retest completed using the deployed validator: AP242 `domain_model_3253c746fcf2420a` with corrected QIF `qif3_1005424112c749fe`, preview `6691f507-c8d6-4e7a-aae3-56bf37cfbb8e`. The UI displayed 190 proposals over 353,026 asserted triples and completed full validation without timing out. Violations fell from 260 to zero. Remaining findings are 19,042 AP242 metadata warnings; custom semantic constraints returned zero findings. Existing policy still blocks approval on these warnings. No mappings were consolidated, approved or published. The new QIF artifact is a registered review draft; future regeneration and the draft browsing fixes require deployment of the updated code package.


Post-deployment UI verification confirmed all 147 package entries installed and both vocabularies visible: AP242 24,206 terms and corrected QIF 5,987 terms. The saved merge review resumed with 190 proposals after restart. AP242's first cold dictionary extraction exceeded the former 30-second inventory-read timeout; retry succeeded from the extraction cache. A follow-up frontend correction gives only cancellable vocabulary GET requests a bounded 90-second budget and provides a read-specific timeout message that preserves saved proposals. Its eight component tests passed. Deploy this follow-up through the same installer; the already registered draft and retained merge job do not need recreation. The AP242 metadata warnings remain unresolved.


### AP242 generated association metadata — 2026-10-21

The retained AP242 artifact's 19,042 warnings were traced to 4,760 generated association nodes and their target edges missing descriptions/provenance, one missing SKOS source link and one omitted source version. The XSD converter now supplies traceable descriptions explicitly identifying generated projection constructs and source provenance. It links the built-in SKOS class to its defining IRI. The generation service copies the XSD root version attribute into ontology version metadata; no standard release number is inferred.

The user's managed_model_based_3d_engineering_domain/DomainModel.xsd regenerated in 43.38 seconds. Its declared version is N11493;2024-12-03. Structural validation returned zero errors/warnings for 315,976 triples, 6,379 classes and 17,827 properties, with complete declared class/property provenance. Tests: 33 passed, one skipped across source registration and deep/semantic XSD conversion.

Identity comparison found one existing source QName collision normalization: the old global element IRI ending #element_d641b803eebbe98d_Uos becomes #element/Uos, still a subclass of #Uos. All other named class/property identities and named domain/range/subclass/inverse relationships remain unchanged. This is explicit review evidence, not authorization to migrate old references. Existing publications and mappings were retained.

The corrected artifact registered through the Import UI in register-only mode as domain_model_26fdb3f1b7934157 (AP242 SMRL v12 Domain Model — Metadata Review 2026-10-21). Full merge validation against corrected QIF qif3_1005424112c749fe is being tested separately. Deploy the converter fix through the existing Setup-DEPO.cmd option 1 to make future generations include it; the registered review draft already contains the correction.


The first AP242 metadata review artifact exceeded the configured combined source limit when paired with QIF. It remains an unapproved audit draft (domain_model_26fdb3f1b7934157). Generated descriptions were shortened and association provenance now records the exact source filename; no limits were relaxed. Final compact ap242-source-projection-v3.ttl is 21,205,305 bytes, with the same 315,976 triples and zero structural errors/warnings. Together with QIF it totals 25,043,335 bytes, below the configured 26,214,400-byte merge source limit. This removes 1,261,400 bytes of repeated text relative to the first LF-serialized generation. The compact draft's review description explicitly identifies the Uos normalization.


Final compact draft registration: domain_model_3a1aad097d514efa, named AP242 SMRL v12 — Corrected Source Projection 2026-10-21. Prepared merge bf414f04-4d4d-46b1-9507-761807bf65cd with corrected QIF has 372,068 statements, 198 heuristic proposals, no selected identity consolidations, and a 23,994,478-byte retained Turtle result, also below the configured source/artifact limit. The user explicitly authorized approval and Neo4j publication after successful validation.

### Service-principal version author correction — 2026-10-21

User authorization to approve and publish remains in force. The final AP242/QIF review passed custom SHACL on the inferred closure; an independent check of the exact prepared asserted graph also passed the standard metadata profile with zero findings. Publication failed before graph-job creation because Semantica requires an email-shaped author and rejected the authenticated `deployment-bootstrap` principal. The retained approval and merged artifact do not constitute a Neo4j publication receipt.

The version adapter now supplies a deterministic reserved-domain SDK alias while retaining the authenticated principal in the public author field and snapshot metadata. Credentials and approval identity are unchanged. Real-SDK tests cover service-principal creation, retained snapshot hydration, idempotent merge retry, existing email authors, and empty-author rejection. Merge/source-profile/version tests: 81 passed and 18 subtests passed. Embedded custom SHACL constraints now supplement, rather than suppress, standard metadata checks; related call-selection tests were updated. Deploying that policy change requires a new validation receipt, not renewed user authorization.

The agent cannot safely restart the installed Windows backend: CIM process inspection returns Access denied. The complete upgrade payload must be applied through the existing administrator-run installer before the installed service can use this correction. Publication is still pending; no success is inferred from artifact status.

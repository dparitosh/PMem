# Governor / Steward boundary review

**Subsequent fixes:** [L0–L4 remediation](l0-l4-remediation-2026-10-28.md) addresses GS-01/GS-02 and the graph revision handoff. This review retains its original pre-fix evidence.

Date: 2026-10-28. Scope: audit of the previously stated Governor/Steward guarantees, the installed local release, and the Semantic Bridge workflow. Production code was not changed during this review. Live LLMs, graph publication and business-data modification were not exercised.

## Outcome

The roles and authorization boundaries are implemented, but the statement that known logical conflicts hold affected writes was too broad. Two execution reproductions found a target-check false negative and loss of a previously established hold during an evidence outage. These should be treated as release blockers for claiming reliable automated semantic conflict protection. The earlier 351 passing tests did not cover these cases.

## Claim reconciliation

| Earlier statement | What the implementation actually does |
|---|---|
| Governor coordinates merge/mapping proposals and publication requests. | Confirmed as registered tools and fixed workflow steps. This does not imply that an LLM plans or reasons independently at every stage. |
| Steward evaluates the retained proposal. | Confirmed: saved preview integrity, upstream validation findings, ambiguity, heuristic confidence, configured policy and current semantic support are evaluated by server code. |
| Steward checks domain compatibility. | The bridge consumes validation produced by `SemanticWorkflowService._validate_candidate_pair` and its reasoning/validation implementation. `bridge_findings` separately holds explicit identity assertions. This is not complete ABox SHACL validation or a fresh full OWL-DL check for each candidate. |
| Known logical conflicts hold affected writes. | Only when a relevant conflict is represented by the evidence available at the check. The two confirmed failures below make an unconditional guarantee incorrect. |
| Unknown remains explicit. | The assessment reports unknown/unverified, but initial unknown does not block bridge publication under the existing policy. A previous hold can also be lost after an outage. Manual and automatic merge paths treat unverified DL differently. |
| HermiT does not grant approval. | Confirmed. Semantic assessment returns `publication_authorized=false`; API authorization, policy and publication contracts remain separate. |
| Governor publishes only through the existing authorized workflow. | Authorization is enforced, but workflow execution is not the exclusive entry point. Approved direct tool calls and manual bridge publication routes also exist and invoke the governed service checks. |
| Boundaries were being checked in the restarted app. | Managed startup completed and checked browser authentication/ontology reads. A prior broader post-restart probe did not execute because approval review could not complete. This audit subsequently verified live read endpoints, not a live publication or LLM-assisted end-to-end scenario. |

## Confirmed findings

### GS-01 — P1: bounded unsatisfiable-class list allows an unsafe target through

**Sources:** `infra/reasoner/src/main/java/org/depo/reasoner/Main.java:58-59`; `backend/depo_platform/semantic_support.py:26`, `:35-39`; `backend/agentic_service/bridge_jobs.py:99`, `:192-202`.

**Root cause:** HermiT computes the complete unsatisfiable-class count, but emits at most 200 class IRIs. The business assessment retains at most 200 IRIs. `target_conflict` treats absence from that bounded list as no target conflict, without checking whether the list is complete or whether the selected class was individually assessed.

**Execution reproduction:**

1. Build an ontology with two disjoint classes and 205 named classes subclassing both. No instances are necessary; the ontology is globally consistent but these 205 classes are unsatisfiable.
2. Run the actual local OWLAPI/HermiT worker.
3. Select one of the five unsatisfiable classes absent from the returned 200-IRI list.
4. Feed that evidence and a high-confidence otherwise eligible classification candidate into `BridgeJobs` using an in-memory registry and fake graph publisher.
5. Evaluate and publish automatically.

**Observed:** real reasoner count 205; listed classes 200; target guard false; one candidate accepted; fake publisher called once and returned `published`. No live graph write occurred.

**Impact:** automatic and manual write guards share this target check. A classification can pass for an impossible class omitted from the evidence sample. The live graph transaction checks source/target identity and type, not OWL class satisfiability, so its identity checks do not close this gap.

**Recommended fix:** make completeness explicit and perform a hash-bound selected-target satisfiability lookup when membership cannot be decided from complete evidence. Never interpret absence from a sample as proof of satisfiability. Hold that candidate pending the targeted check rather than holding every unrelated class. Add regression cases at 199, 200, 201 and 205 unsatisfiable classes for both publication paths.

### GS-02 — P1 policy/reliability gap: evidence outage can remove an established conflict hold

**Sources:** `backend/depo_platform/semantic_support.py:42` onward (`read_support` converts dependency failure to unknown); `backend/agentic_service/bridge_jobs.py:77-117`, `:124-137`, `:192-202`.

**Root cause:** evaluation reads current semantic support without preserving an established hold as a durable decision bound to the same source. `target_conflict` returns false for unverified evidence. Automatic publication reevaluates the same preview, and the write path also permits unknown under the existing initial-unknown policy. There is no distinction between “never checked” and “previously known conflicting, now unavailable.”

**Execution reproduction:**

1. Execute the real reasoner on an ontology containing an individual typed as two disjoint classes; obtain verified `inconsistent` evidence.
2. Evaluate a valid retained bridge preview with that support; observe `held`.
3. Simulate a subsequent semantic-evidence read outage, returning unknown with reason `semantic_evidence_unavailable`. Keep the source snapshot unchanged.
4. Request automatic publication of the same preview using the in-memory/fake-graph harness.

**Observed:** initial assessment held; later evidence unknown; the fake graph publisher was called once and the job became published. No live graph write occurred.

**Impact:** a dependency outage can appear to resolve a previously established model conflict. The behavior is confirmed; permitting initial unknown was deliberate compatibility policy, so the defect is specifically failure to preserve a prior hold, not absence of a blanket OWL-DL requirement.

**Recommended fix:** retain established per-model/per-target holds with source, foundation, policy and preview revisions. Loss of evidence must not clear such a hold. Require a new verified assessment resolving the conflict, or an explicitly authorized and audited exception under a defined policy. Keep unrelated legacy initial-unknown handling separate. Test outages, 401/403, timeout and restart after a held assessment, including lost-response receipt recovery.

## Confirmed limitations and unproven risks

- **Optional merge reasoning:** `backend/depo_platform/request_bodies.py:98` makes `owl_dl_check` optional; `backend/ontology_service/merge_service.py:183` executes it only when true. The UI currently requests it by default, but a workflow/API caller can omit it. Automatic union evaluation still applies structural/SHACL/OWL-RL/governance checks; it is not a mandatory HermiT gate. BPMN documentation must show this condition.
- **Manual versus automatic unknown:** `merge_service.py:251` holds automatic union approval for unverified DL evidence. `_apply` explicitly blocks conflict and checks dependency revisions, but does not universally prohibit manually authorized application of an unverified result. Do not describe all unresolved cases as a single hard gate.
- **Graph/model revision correspondence — P2 risk:** ingestion snapshots hash retained ontology content and graph lookup data together (`backend/ingestion_service/bridge_source.py:29-30`). Current semantic evidence is selected by the retained artifact digest (`backend/ontology_service/owl_dl.py:124`). The assessment explicitly reports `graph_projection_verified=false`. That is not proof that the selected graph projection was published from the reasoned artifact. A stale-projection/updated-retained-model interleaving needs a dedicated concurrency test and publication-revision binding. No live mismatched publication was reproduced in this audit.
- **Logical roles, not independent approvers:** catalog tool allowlists distinguish Governor and Steward, but fixed workflows use the existing authorization/grant mechanism. Two named roles do not establish a four-eyes approval scheme or require two independent humans/LLMs.
- **Direct governed execution exists:** `backend/agentic_service/router.py:593`, `:799`, and `backend/agentic_service/bridge_router.py:56-70` support authorized execution outside a catalog workflow. This is not evidence of an authorization bypass.

## Correct functional sequence

1. User selects exact source identities and an operation in Semantic Bridge.
2. The controller dispatches a Governor-labelled preview tool and retains the proposal.
3. A Steward-labelled evaluation tool invokes deterministic validation/policy code. An optional model review can explain evidence; it is not enforcement authority.
4. Applicable reasoning is either executed for the requested union/model or retrieved as current evidence. Missing/incomplete evidence must be distinguished from a positive result.
5. UI displays eligible/held candidates, coverage and next actions. Automated and manual policy paths remain explicit.
6. An authorized Governor-labelled publication tool or manual governed route rechecks applicable constraints, reconciles an existing receipt, then requests a graph transaction when permitted.
7. Graph changes and their receipt commit together; PostgreSQL retains the workflow outcome and evidence. Cross-store state is reconciled, not one distributed atomic database transaction.

## Evidence and coverage

- New executable harness: `outputs/governor-steward-boundary-audit.py`.
- New machine-readable reproductions: `outputs/governor-steward-boundary-audit.json`. Both scenarios use actual local HermiT results, an in-memory registry and fake graph writes; live writes are explicitly zero.
- New installed read checks: `outputs/governor-steward-live-read-audit.json`. Foundation, ontology inventory, current semantic evidence, agent catalog, Data Flow list/detail and Data Products list all returned HTTP 200. The inspected model was `not_checked/unverified`; Data Flow model evidence was unknown; the Data Products list contained zero products. A populated customer product publication is therefore not live-qualified by this check.
- Governor and Steward expose the new semantic-evidence tool in the running catalog. Installed hashes matched the reviewed `bridge_jobs.py`, `semantic_support.py`, `merge_service.py` and catalog JSON.
- Earlier combined regression evidence remains **351 passed, zero failed/skipped** (`outputs/semantic-loop-release.xml`). It is historical coverage for that run, not proof that the new boundary cases pass. Small target sets and initial-unknown cases did not expose these failures.

No production correction or release approval is claimed by this audit. Fix GS-01 and GS-02, preserve the cases as regression tests, then qualify targeted evidence completeness, outage/reconnect behavior and graph/model revision correspondence before repeating the stronger customer guarantee.

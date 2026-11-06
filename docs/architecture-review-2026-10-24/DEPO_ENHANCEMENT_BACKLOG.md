# DEPO enhancement backlog — approval proposal

Estimates are engineering ranges for one engineer familiar with the code, excluding customer policy decisions and deployment access. They are not delivery commitments. Implement incrementally after baseline/plan approval.

| Order | Gap / deliverable | Dependencies | Effort | Risk | Acceptance |
|---|---|---|---|---|---|
| P0-1 | G01 versioned context envelope and adapters in agentic owner | Approved contract | 3–5 days | Scope leakage or broken recovery | Cross-page/ontology/principal tests; old run compatibility; no new store |
| P0-2 | G02 required execution receipt versus optional enrichment status | P0-1 | 2–4 days | False success when memory fails | Graph-memory outage cannot erase mandatory run state; UI shows degraded enrichment |
| P1-1 | G03 semantic validity/supersession filtering | Approved lifecycle model, P0-1 | 4–7 days | Legacy facts silently reused | Unknown legacy state explicit; revoked/superseded facts excluded; source revision change tested |
| P1-2 | G05 representation and provenance coverage in retrieval/UI | P0-1 | 3–5 days | Confusing graph completeness | ContextGraph versus Neo4j clearly named; unavailable source and partial results visible |
| P1-3 | G07 grounded-answer evaluation fixtures | P0-1; can begin in parallel as fixtures | 3–5 days | Evaluation overfits sample | AP242–QIF, PLMXML, catalog, quality and recommendations; citation support, abstention and isolation evaluated |
| P2-1 | G04 coordinated retention/invalidation receipts | Policy approval, P1-1 | 5–8 days | Irreversible loss / retained sensitive copies | Dry-run inventory; legal hold; injected per-store failure; retry completion; backup policy documented |
| P2-2 | G06 versioned procedure promotion | P0-2, evaluation fixtures | 4–6 days | Unsafe executable learning | Human promotion; signed/authorized definition digest; compatibility and retirement tests |
| P3-1 | Uncertainty/gap explanation and budget tuning | Evaluation baseline | 2–4 days | Uncalibrated confidence | Scores labeled; insufficient evidence abstains; token/latency budget measured |

## Release gates

Unit checks are necessary but insufficient. Require an isolated PostgreSQL/Neo4j integration environment; migrations and rollback exercise; customer identity topology tests; browser acceptance across ontology, import, graph, catalog, products, quality and recommendations; provider outage/quota and stale-request checks; controlled deletion tests; retrieval relevance and citation audits. No production cleanup or publication is part of this review.

## Decisions to review before implementation

Confirm the existing-service facade approach; define individual-user versus shared-service identity requirements; approve semantic assertion lifecycle and legacy-fact policy; select retention/legal-hold requirements; agree representative domain fixtures and measured release thresholds. Do not set arbitrary accuracy or latency claims before collecting the baseline.

## Implementation status after approval

See [implementation progress](DEPO_IMPLEMENTATION_PROGRESS.md). P0-1 now has an internal versioned envelope, shared Companion scope and worker resume checks; authoritative revision validation and token budgeting remain incomplete. P0-2 has required-before-optional Companion retention with fault-injection tests. P1-2 now reports representation and bounded coverage in retrieval. The remaining backlog is not marked complete.

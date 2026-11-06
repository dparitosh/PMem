# Deliverable reconciliation — 2026-10-28

Follow-up: [installed deployment verification and browser-discovered fix](DEPLOYMENT_VERIFICATION.md). Earlier statements about no live deployment describe the audit/remediation snapshot below, before this explicitly authorized deployment.

**The twelve confirmed findings have implementation changes. The full audit is not closed.**
Recorded final verification: 262 backend tests, 67 frontend tests and a successful production build. Five standalone registry/source checks passed; its full host suite could not collect without the external IIF LlamaIndex SDK. Inference was mocked. No customer deployment or live model qualification was performed.

## Earlier deliverables

| Artifact | Meaning and reconciliation |
|---|---|
| `AUDIT.md`, `defects.json` | Historical findings and seven separate risks. Preserved as the pre-fix record; follow `REMEDIATION.md` for implemented changes. A historical confirmed defect is not a current failure claim. |
| `INVENTORY.md`, `inventory.json`, `runtime-catalog.json` | Pre-fix inventory, traces and role/policy text. `runtime-policy-current.json` supplies the reconciled current catalog/policy snapshot without inference. |
| `dependency-map.mmd` | Updated current flow: separate Companion, proposals, read goals, deterministic workflows, original schema validation, context budgets, needs-input outcomes, provider routing and optional hosts. A node does not mean production behavior is qualified. |
| `proposed-prompts.json` | Design drafts, not runtime configuration or a deployment manifest. Final code implements selected contracts with preserved business roles; do not replace the catalog with these drafts. |
| `test_prompt_audit_reproductions.py`, original XML and captures | Historical reproductions; some deliberately assert defective behavior. They are not current acceptance tests. |
| `backend/tests/test_prompt_audit_fixes.py` | Current acceptance cases: role/mode construction, redaction, schema projection, citations, memory, clarification and budget diagnostics. Broader tests cover retention, grants, scope, recommendations and MCP. |
| `REGRESSION.md` | Broader qualification plan, not a claim every scenario ran live. Final executed results are in `validation.json` and `prompt-fixes-frozen.xml`. |
| `source-preservation.json` | Historical proof the original audit did not change source. `validation.json` records post-fix hashes; `deliverable-check.json` compares those with the current tree. |

## Finding closure

PA-01 through PA-10 and PA-12 have implemented fixes with relevant passing local regression evidence. PA-11's obsolete tool/bindings are removed and registry/source checks pass; external IIF integration remains pending. See individual rows in `REMEDIATION.md`.

## Work still open

| Risk | Status and required closure evidence |
|---|---|
| PR-01: truthful conclusions | Mitigated, not semantically verified. Domain gold-set and fact/relationship grounding checks remain necessary. Citation membership and advisory labels do not prove prose follows from evidence. |
| PR-02: context fit | Guard implemented; verify/configure each customer's usable model context and test representative maximum-size requests. The default does not detect capacity. |
| PR-03: jailbreak behavior | Live provider/model adversarial and stochastic evaluation pending. Code fixtures cannot establish model resistance. |
| PR-04: optional legacy cost/latency | Not closed. Measure/bound nested model calls under a shared budget or retire that host path. Fixing its RAG message boundary does not finish this work. |
| PR-05: per-person history | Deployment identity policy pending. Use individual identities and verify cross-principal denial. Deliberately shared service credentials share a principal. |
| PR-06: ontology-review shape | Code clarification complete; existing schema and supplied-IRI checks retained. Live provider compliance remains part of PR-03 qualification. |
| PR-07: AOI transformations | Vendor/customer documentation and boundary traces pending. Approved compiled helper internals were not audited or modified. |

The map now exposes these limits. This is not evidence that all security/business-accuracy work is complete or that a customer release has been tested.

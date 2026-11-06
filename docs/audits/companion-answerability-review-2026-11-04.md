# Answerability follow-up audit

## Result

The audit initially found five groups of defects despite 37 passing tests and 5 subtests. A subsequent authorized fix addresses the reproduced cases below. This remains a bounded coverage guard, not a general proof of natural-language answerability.

Scope: the new answerability module, Companion call order and generation decision, selected-record routing, memory filtering and frontend response consumption. This was code review and executable backend probes, not browser or live-model acceptance.

## Confirmed findings

### A1 — High: descriptive prefix bypasses quantitative protection

- Location: `backend/agentic_service/answerability.py:7`.
- Reproduction: `assess('Explain this product and calculate its average mass', [])` returns `bounded_evidence`, `answerable: true`.
- Root cause: the first word exempts the entire request, including subsequent calculation clauses.
- Impact: later retrieval can permit model interpretation without executed numerical evidence. An incorrect final generated answer was not tested.
- Fix: classify requested operations per clause, retaining descriptive context without exempting explicit calculation instructions.

### A2 — High: calculation coverage depends on a short keyword list

- Location: `backend/agentic_service/answerability.py:8`.
- Reproduction: `assess('What is the sum of component weights?', [])` returns answerable.
- Root cause: the vocabulary omits sum and other aggregate forms, and the fallback assumes coverage.
- Impact: semantically equivalent quantitative questions receive different protection.
- Fix: use explicit supported operations with required evidence contracts; unsupported aggregate intents must not reach generation as answered facts. Do not treat expanding a regex as comprehensive natural-language understanding.

### A3 — High: unknown or mixed ownership evidence passes

- Location: `backend/agentic_service/answerability.py:16`.
- Reproduction: a `parts_with_pmi` row with `association_status: unknown` returns answerable. A source-reference-only PMI item combined with a product-list item also returns answerable.
- Root cause: the gate rejects only one negative value and requires every item to share the PMI intent. It does not require affirmative, recognized ownership evidence for each requested claim.
- Impact: unrelated evidence or an unknown status can remove the ownership guard and permit generation.
- Fix: validate the actual producer's ownership contract per association. Keep verified and unverified rows distinct and compute coverage per question requirement.

### A4 — Medium: vocabulary questions incorrectly blocked

- Location: `backend/agentic_service/answerability.py:8`; `backend/agentic_service/companion.py:52`.
- Reproduction: `assess('What percentage means in this ontology?', [])` returns `unsupported_calculation`.
- Root cause: isolated words trigger rejection before semantic or selected-record routing can interpret the request.
- Impact: legitimate ontology explanations are unavailable. The same early rejection can suppress retained operational evidence that already contains authoritative counts.
- Fix: distinguish definitions, reading an existing result and executing a new calculation. Preserve owning-service evidence and apply operation-specific checks before generation/execution.

### A5 — High: positive answerability is not proof of coverage

- Location: `backend/agentic_service/answerability.py:20`; `backend/agentic_service/companion.py:266` and `:309`.
- Reproduction: `assess('Is the selected requirement satisfied?', [])` returns answerable. The actual Companion separately handles completely empty evidence, but nonempty unrelated evidence can still reach this permissive default.
- Root cause: presence/absence checks do not establish that the evidence supports the requested relationship or judgment. Requirement satisfaction is not part of the gate's supported evidence contracts.
- Impact: a matching record or dependency path can enable model interpretation of an unsupported judgment. Live-model fabrication was not demonstrated.
- Fix: distinguish retrievable context from an answerable claim. Require explicit satisfaction/verification evidence for satisfaction questions, otherwise return partial/unsupported coverage with useful retained context.

## Tests and conclusions

Executed the existing answerability, prompts, boundaries, domain-evidence and accuracy suites: 37 passed and 5 subtests passed. Executed six adversarial function probes; their outputs confirmed A1–A5. Those probes demonstrate coverage gaps in passing tests, not an independently verified hallucinated model response.

The memory code excludes `answerable: false` turns from successful recall, so false-positive answerability has downstream context implications. The frontend consumes the answerable flag, but no browser test of the new failure states was performed.

Next work: implement operation-specific coverage, preserve partial evidence, add these adversarial cases as regression assertions, and verify persisted/streamed responses and follow-up context. Do not describe this narrow gate as a complete Semantica-based analytics or query-execution loop.

## Follow-up implementation

- Explicit calculation clauses now take precedence over a descriptive prefix. Aggregate vocabulary includes sums, ratios and medians. Definition questions are distinguished from execution requests.
- PMI checks operate per item and accept only the producer contract's `recorded_association` status. Unknown status, source references and mixed evidence cannot enable interpretation of ownership.
- Satisfaction, compliance and suitability questions suppress model interpretation unless the request is a vocabulary definition. The current Companion has no verification-result contract that authorizes those conclusions.
- Selected-record and semantic routing run before the generic calculation rejection. Existing context remains visible, with unsupported parts marked unanswerable. Reading an approved numeric result is not yet a dedicated execution capability.
- Regression cases now cover all six audit probes, additional aggregate wording, unknown ownership, mixed evidence and preservation of retained selected-record evidence.

No package or database migration is required. Changes remain in source and require deployment/restart. Browser streaming, database persistence and live-model acceptance were not executed in this follow-up. General multilingual intent understanding and approved calculation execution remain outside this bounded fix.

Final validation: answerability, prompts, boundary, domain-evidence and accuracy suites passed 50 tests and 5 subtests. `git diff --check` passed.

## Local deployment and acceptance

On 2026-11-04, deployed the Companion module and answerability module to `D:\GenAI_Projects\Apps\PMem`, with an original-module backup in the workspace output folder. Source/installed SHA-256 hashes match. The supported Stop/Start scripts restarted backend services and workers; database servers stayed running. Schema, indexes, credential profiles and endpoint validation passed. The existing frontend launcher restored the browser listener.

An authenticated request to the running `/api/v1/chat` rejected the mixed calculation, returned `answerable: false`, did not request model generation, and retained its evidence record in PostgreSQL. Reading that session's history confirmed the retained response.

Actual browser checks in Home verified the same mixed request, refresh restoration with the saved-evidence warning, a definition question proceeding to retrieval rather than calculation rejection, and sum-of-weights rejection. No matching definition evidence was returned, so no definition was fabricated. Screenshot evidence: `outputs/companion-answerability-deploy-20261104/browser-acceptance.png` under the workspace root.

Additional checks passed: 8 backend retention/memory tests and 21 frontend Chatbot tests. Total verification: 58 backend tests, 5 subtests and 21 frontend tests. The frontend test run emitted a React test-utils deprecation warning and expected fixture error logs.

LLM services remain disabled. Live-model output quality and execution of approved business calculations are not established by these checks. This local acceptance does not imply customer-environment acceptance.

# Prompt audit remediation — 2026-10-28

The original audit and its captures describe the pre-fix snapshot. Production changes below follow the user's authorization to fix it. The historical reproduction suite intentionally asserts old defects; use `backend/tests/test_prompt_audit_fixes.py` for current acceptance tests. Do not regenerate historical source-preservation claims against the modified tree.

## Implemented changes

| Finding | Implementation | Acceptance evidence |
|---|---|---|
| PA-01 | Credential recognition covers camelCase, acronym/case and hyphen variants, private keys, tokens and connection strings. Nested objects, known configured values and serialized credential assignments are redacted. | Alias, object, assignment and actual Companion request tests. |
| PA-02 | Model-visible tool metadata and native/structured schemas are sanitized. Credential-property annotations/defaults are omitted while property names/types remain intact. Original schemas remain authoritative for response/input validation. The final agent provider boundary re-sanitizes requests. | All 28 catalog roles × both proposal modes; schema integrity and unchanged authoritative contracts. |
| PA-03 | Goal scratchpads preserve scope, plan/decision state and observation identities. Results are budgeted newest first, with explicit omission/truncation markers. Tool contracts/policy/completion reserve precede evidence selection. | Large-memory test retains latest evidence and every observation ID within the budget. |
| PA-04 | `proposal-v4` separates suggestion-only instructions from executed read-goal instructions. Custom/domain constraints, mapping direction, immutable IDs and server approval remain authoritative. | Mode-specific policy tests, complete catalog captures and goal execution tests. |
| PA-05 | Citation checks cover numbered, Unicode and ASCII list items and separately rendered facts; tables continue to require row citations. | Cited/uncited list variants and real Companion rejection before output. |
| PA-06 | Citation identities come from projected record aliases, not recursive arbitrary nested IDs. Backend and UI recognize the same record alias fields. | Forged nested ID rejection and citation rendering tests. |
| PA-07 | Primary record IDs reserve the citation budget before aliases; unrelated nested row IDs cannot crowd out their owning record. | Primary ownership/cap regression. |
| PA-08 | A schema-bound `goal.needs_input` action and server-side incomplete-read detection stop missing-input loops without dispatch. Requests can name only missing required read fields, never credentials or already-supplied scope. The UI accepts this state and other valid terminal states without resubmitting work. | Single-decision clarification, incomplete-read fallback, no-dispatch assertions and terminal-state UI cases. |
| PA-09 | Recommendations has dedicated Similar Parts, Change Impact and Process Context sample questions; quality aliases resolve to real quality samples. | Sample routing/content test. |
| PA-10 | Both legacy vector templates put retrieved context in a separate human message and retain policy in the system message. | Actual template formatting with injected retrieved text. |
| PA-11 | Obsolete standalone Owlready2 tool, bindings and old tool tests are removed. Intake/review accurately describe asserted RDF structure; no replacement claim of full OWL-DL consistency. Upgrade documentation explicitly requires removal from an existing external IIF registry. | Five registry/source checks passed. Actual SDK/host integration remains unqualified; see below. |
| PA-12 | Prompt tests check nonempty role scope/tools and policy contracts rather than requiring a literal role ID in custom wording. Extracted router/catalog fixtures supply the current dependencies and artifact resolver. | The three original test failures pass in the broader regression run. |

Additional fixes: read-goal UI validation now accepts `blocked`, `timed_out`, `budget_exhausted` and `needs_input`. Goal summaries explicitly declare advisory interpretation and lack of independent semantic entailment verification. Ontology-review instructions describe the existing JSON shape and field bounds. Context-budget failures have a distinct safe diagnostic and useful next action rather than being described as a provider outage.

## Context configuration and installation

`AGENTIC_MODEL_CONTEXT_TOKENS` bounds requests using a conservative UTF-8 token upper bound, requested completion and 2,048 tokens of framing reserve. The default/example is 32768. This is not automatic detection: configure the verified usable context for the selected provider/model. Oversized requests fail before inference. Ollama and cloud transport paths enforce this check; read-goal evidence selection accounts for it. Narrow oversized evidence rather than raising the setting beyond supported capacity.

`INSTALLATION.md` and `config/deployment.env.example` document this setting, missing-input outcomes, advisory summaries and shared-principal history behavior. These changes do not require a new PostgreSQL schema: goal records remain JSON registry entries. Existing authorization, grants, source/revision checks, approvals and publication receipts are preserved. Retained runs tied to an older policy/controller contract may be held by existing fencing controls; inspect their retained results and start a new investigation against the new contract. No write is replayed automatically.

The optional standalone IIF pack is distinct from the PMem backend and AOI adapter. Run its integration suite in the IIF host environment providing `llama_index.core.tools.FunctionTool`. The backend manifest intentionally does not install that external orchestration SDK. No AOI vendor assets or compiled helper internals were changed.

## Final verification

- **262 backend tests passed**, including actual prompt construction for every default role in structured/native modes, adversarial acceptance, provider contracts, goal scope/control, memory, MCP boundaries, recommendations and Companion retention/context.
- **67 frontend tests passed** across investigation state/recovery, recommendations, inference, history and Markdown/citation rendering.
- **Five standalone registry/source checks passed.** Its full suite could not collect in this PMem-only environment because `llama_index` is absent; one registry import/integration check was deliberately excluded from the static run. No claim of external IIF integration success is made.
- **Production frontend build passed.** Existing large-chunk and React testing deprecation warnings remain.
- Provider inference was mocked. No LLM was enabled/called; no import, approval, publication, database migration or live deployment was performed.

JUnit results and changed-source fingerprints are retained alongside this document. Earlier intermediate results are not the final release gate; use `validation.json` and `prompt-fixes-frozen.xml`.

## Remaining qualification limits

- PR-01 is mitigated with explicit advisory labeling and preserved structured observations, not solved by claiming natural-language entailment verification. A valid evidence ID alone cannot establish the truth of arbitrary prose.
- PR-02 now has an enforced conservative budget; each customer's selected model capacity must still be verified and configured.
- PR-03 requires live provider/model adversarial and stochastic evaluation. Code-level guards do not certify jailbreak resistance.
- PR-04's optional legacy path still has its own nested-call cost profile; its RAG trust boundary is fixed, but performance requires host/provider measurement or retirement.
- PR-05 requires deployment identity policy: shared credentials share a principal. Individual histories need individual/Entra identities.
- PR-06's JSON wording is clarified; existing output schema and supplied-IRI checks remain enforced.
- PR-07's AOI internal prompt transformations need vendor/customer evidence. The approved opaque wrapper remains unchanged.

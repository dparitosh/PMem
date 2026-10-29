# Regression and adversarial test plan

## Recorded execution

- Existing focused suite: 144 tests, 141 passed, 3 failed. Retained evidence: `existing-tests.xml`.
- Audit suite: 81 passed. Retained evidence: `adversarial-tests.xml`. A reproduction passes by demonstrating the current bug; it must be inverted when implementing a fix.
- 56 real role/mode prompt captures with mocked inference; 57 real input schemas resolved; ten read-only service OpenAPI GETs succeeded.

Run the audit file using a Python environment with the application's existing test dependencies, the repository root on PYTHONPATH, and an isolated temporary directory. From the repository root:

```powershell
python -m pytest docs/audits/prompt-audit-2026-10-28/test_prompt_audit_reproductions.py -q --tb=short -p no:cacheprovider --basetemp "$env:TEMP/pmem-prompt-audit-replay" --junitxml "$env:TEMP/pmem-prompt-audit-replay.xml"
```

The copied harness derives its repository root from its location. It reads retained `live-openapi-contracts.json` and writes only synthetic captures beside the harness and temporary test files. It mocks provider posting. Do not point replay at a modified production catalog without reviewing its construction side effects. Discovery scripts retain their original workspace paths; they are provenance, not portable deployment commands.

## Fix acceptance cases

| Area | Case | Required result |
|---|---|---|
| Credentials | CamelCase/snake/hyphen aliases, nested arrays, connection strings, tool descriptions/defaults/examples, known and unknown secrets | No synthetic secret in system/user/native-tool messages, logs or retained prompt snapshots; business values preserved |
| Scope | Model selects another ontology/node/principal, write tool, foreign attachment or old revision | Server rejects before dispatch; original scope retained |
| Memory | Large early observations, latest failure/success, maximum decisions, truncation | Selected scope and latest observation ID/result remain usable; omissions explicit; no invented evidence |
| Missing data | Required ontology/node absent, ambiguous object, missing artifact | Controlled needs-input or unsupported outcome; no repeated invalid loop; no write |
| Citations | Numbered/Unicode lists, table rows, nested fake IDs, >200 identifiers | Every factual unit cites authoritative retained IDs; primary IDs survive; UI/backend agree |
| Truth | Correct ID attached to false diameter/approval/ownership claim | Fact mismatch blocked or visibly advisory; no false engineering conclusion |
| Injection | Graph/PG/document/schema text says ignore rules, leak keys, change scope, publish | Data cannot grant tool rights; model output treated as untrusted; no harmful side effect |
| Contracts | Malformed JSON, extra keys, native arguments as malformed strings, missing/unknown tool, contradictory output | Bounded structured rejection, no fabricated success, no partial write |
| Providers | Ollama/cloud/AOI; disabled/unavailable model; schema/tool unsupported | Deterministic evidence retained; clear capability gap; no silent downgrade to unauthorized execution |
| Concurrency | Duplicate goal submit, concurrent poll/reconnect, cancelled/stale work, interrupted tool result | Owner-bound idempotency, no duplicate mutation, recover retained receipt/status before replay |
| Token fit | Large question/evidence/tool schema; model with small context | Reserve completion and tool headroom before call; structured omission or rejection |
| Business answer | Part–PMI ownership absent, ontology definition only, conflicting units, partial graph slice | Business names/values and vocabulary labels; precise uncertainty; no XML/JSON presented as answer or completeness claim |

The current audit executes representative code-level cases, not every row's full deployment scenario. Model-specific multilingual/encoded jailbreak tests, stochastic runs, customer latency/concurrency and individual-user memory isolation require a later controlled integration run. They remain qualification work, not passed results.

## Existing test drift

`test_all_roles_have_task_scope_and_shared_constraints` expects the literal role ID inside every prompt; ontology-inference conveys the role without that literal. Two catalog-control tests AST-extract router functions with incomplete catalog globals/stubs after production APIs changed. Repair their fixtures and semantic assertions before using the suite as a release gate. Do not suppress failures or weaken production checks to make a test green.

# Memory demo rehearsal — 2026-11-01

## Live results

| Demonstration | Observed result | Status |
| --- | --- | --- |
| Basic conversation continuity | Home question `Show requirements for induction motor` returned recorded requirement paths after one failed initial attempt. Follow-up `And its requirements?` returned the same motor context. Model generation disabled. | Passed basic subject recall |
| Page reload | The first retained turn reappeared with `Saved answer — evidence has not been refreshed.` | Passed retention, not fresh evidence |
| Context separation | Graph Explorer Companion displayed a separate empty conversation after leaving Home. | Separation observed; selected-object switching not tested |
| Return navigation | After deployment, Home → Graph → Home restored the earlier Home answer with its historical label. Graph did not display the Home conversation. Restoration exceeded the initial UI wait window. | Eventual recovery passed; latency target not qualified |
| Execution records | Admin > Agents & workflows > Load recent runs > first completed bridge workflow > Inspect / refresh showed run-1798b434-ac0b-4964-8cbe-7c7b94a9fd77, three completed steps and expandable step results/receipts. | Historical execution inspection passed; no live autonomous investigation |
| Long-term lessons | Ontology Junction > Semantic Bridge > Learning from reviewed mappings showed no approved hints for selected AP242 revision and required a verified publication for feedback. | Not ready for successful recall demonstration in this scope |
| Optional graph memory | Admin > Check agent memory reported disabled; schema/fact storage not verified. | Disabled in running installation |

The local deployment now contains source release `8a85fb7`, including memory/event and authorization fixes. Environment hashes were preserved. No LLM invocation, customer approval/publication, credential rotation or application database reset was performed.

## Presenter sequence

1. Home: enter `Show requirements for induction motor`. Only continue if the business evidence table loads. Explain these are recorded connections, not proof of satisfaction.
2. Ask `And its requirements?`. Show the business object remains the motor without repeating its name.
3. Reload the page. Show any restored answer is explicitly historical and needs current retrieval for freshness.
4. Admin > Agents & workflows > Load recent runs. Select the completed bridge workflow and choose Inspect / refresh. Show three completed steps. Expand Step results and receipt evidence only for a technical audience; the current view exposes raw JSON.
5. Ontology Junction > Semantic Bridge > Learning from reviewed mappings. Explain the feedback-to-approved-hint flow, but do not claim successful long-term recall while the selected scope has no approved hints.

## Before a customer presentation

Qualify graph/ingestion and history-restoration latency under customer network conditions. Select an actual reviewed published mapping and explicitly prepare/approve a demo lesson; recheck its revision-scoped recall. Enable optional graph memory through the managed configuration only if it is part of the agreed demonstration. Live model planning needs an available provider; keep it separate from retrieval-only demonstrations.

Screenshots are local in outputs/memory-demo-rehearsal: short-term-followup.png, context-isolation.png, execution-memory.png, learning-readiness.png. These are rehearsal evidence, not customer acceptance certification.

## Final local acceptance checks

- A temporary read-only session received HTTP 403 for execution identity and for replay against a deliberately nonexistent acceptance run. No job was enqueued. The same session subsequently received HTTP 200 for ontology health; it was disconnected afterward.
- Seven isolated PostgreSQL/replay tests passed, covering atomic rollback, retry, worker recovery and replay idempotency. Database tests used `depo_acceptance_test` with disposable test schemas, not customer application records.
- Normal browser-session diagnostics passed across ten services and ontology health/list after deployment.
- Evidence: workspace `outputs/live-readonly-replay-acceptance.json` and `outputs/acceptance-replay-memory-final.log`. These local results do not certify customer deployment, production load or live model planning.

Short-term subject recall and eventual contextual history recovery can be demonstrated now. Successful long-term lesson recall and optional graph-memory demonstrations remain unqualified until configured and populated with reviewed evidence.

## Follow-up verification and preparation

An additional 76 tests passed: 23 governed-learning/semantic-continuity checks and 53 graph-memory, maintenance, limits, page-context and context-envelope checks. These are isolated automated tests; they do not populate the running application's learning scope.

For long-term lesson recall, use Semantic Bridge's existing reviewed-mapping flow: select the matching ontology revision and imported source, inspect a verified publication receipt, record the actual confirmed/rejected outcome, prepare its lesson, obtain authorized approval, then reload learning support in that same scope. Revoking the lesson must remove it from support. Feedback and lesson approval must not publish mappings or claim model training.

Optional graph memory is a separate adapter. Its existing configuration requires `AGENT_MEMORY_ENABLED=true` and a deployment-specific `AGENT_MEMORY_SCOPE` (or both tenant and project identifiers); its bounded query timeout defaults to five seconds. Apply configuration through normal managed restart and check Admin memory diagnostics before presenting it. No configuration was changed in this follow-up.

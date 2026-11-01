# Memory demo rehearsal — 2026-11-01

## Live results

| Demonstration | Observed result | Status |
| --- | --- | --- |
| Basic conversation continuity | Home question `Show requirements for induction motor` returned recorded requirement paths after one failed initial attempt. Follow-up `And its requirements?` returned the same motor context. Model generation disabled. | Passed basic subject recall |
| Page reload | The first retained turn reappeared with `Saved answer — evidence has not been refreshed.` | Passed retention, not fresh evidence |
| Context separation | Graph Explorer Companion displayed a separate empty conversation after leaving Home. | Separation observed; selected-object switching not tested |
| Return navigation | Returning from Graph Explorer to Home displayed an empty conversation instead of the earlier turns. | Recovery gap; cause not established |
| Execution records | Admin > Agents & workflows > Load recent runs > first completed bridge workflow > Inspect / refresh showed run-1798b434-ac0b-4964-8cbe-7c7b94a9fd77, three completed steps and expandable step results/receipts. | Historical execution inspection passed; no live autonomous investigation |
| Long-term lessons | Ontology Junction > Semantic Bridge > Learning from reviewed mappings showed no approved hints for selected AP242 revision and required a verified publication for feedback. | Not ready for successful recall demonstration in this scope |
| Optional graph memory | Admin > Check agent memory reported disabled; schema/fact storage not verified. | Disabled in running installation |

The running deployment does not yet contain the local memory/event fixes. No LLM invocation, approval, publication, credential change or database reset was performed in this rehearsal.

## Presenter sequence

1. Home: enter `Show requirements for induction motor`. Only continue if the business evidence table loads. Explain these are recorded connections, not proof of satisfaction.
2. Ask `And its requirements?`. Show the business object remains the motor without repeating its name.
3. Reload the page. Show any restored answer is explicitly historical and needs current retrieval for freshness.
4. Admin > Agents & workflows > Load recent runs. Select the completed bridge workflow and choose Inspect / refresh. Show three completed steps. Expand Step results and receipt evidence only for a technical audience; the current view exposes raw JSON.
5. Ontology Junction > Semantic Bridge > Learning from reviewed mappings. Explain the feedback-to-approved-hint flow, but do not claim successful long-term recall while the selected scope has no approved hints.

## Before a customer presentation

Resolve intermittent graph/ingestion timeouts; deploy and browser-test the local fixes; resolve return-navigation history recovery; select an actual reviewed published mapping and explicitly prepare/approve a demo lesson; recheck its revision-scoped recall. Enable optional graph memory through the managed configuration only if it is part of the agreed demonstration. Live model planning needs an available provider; keep it separate from retrieval-only demonstrations.

Screenshots are local in outputs/memory-demo-rehearsal: short-term-followup.png, context-isolation.png, execution-memory.png, learning-readiness.png. These are rehearsal evidence, not customer acceptance certification.

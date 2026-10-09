# Frontend priority audit — 2026-10-09

## Fix update

All eight items below now have code changes. QIF selection is blocked during mutations while read-only selection remains available; cancellation and history responses are fenced. XML evidence links use the shared route. Agent inspection opens Admin's agents tab using only a run-identity bookmark, and execution messages use validated states. The standalone read-tool endpoint now explicitly returns its completed state. Data Flow replays retained inputs and locks concurrent definition actions. Quality clears evidence on access changes. Focused UI regression tests cover these changes; live customer services and browser layout validation remain pending.

This review does not establish 50 P1 bugs. Findings below describe the code before the follow-up fixes above. Existing tests do not establish live API, keyboard, responsive-layout or customer-deployment correctness. The initial audit made no application changes; the subsequent fix pass did.

## Original P1 candidate — corrected with regression coverage

1. **QIF action responses can replace a different selected task.** `frontend/src/pages/QifPage.js:154` unconditionally sets the cancellation response as the displayed task. History buttons at line 268 remain enabled while `actionBusy` is true. Start cancelling A, select B while cancellation is pending, then let A's response arrive: displayed task becomes A while `selectedTask.current` remains B. Action buttons derive their target from the displayed task, while polling uses the selected-task guard. This can expose controls for the wrong task and mislead an operator during governed publication. Fix by fencing every mutation response to its captured task and request generation, and blocking task selection during incompatible actions. Priority is P1 if the interleaving reproduces in the browser; it was established by control-flow inspection, not a browser test.

## Original P2 defects and workflow gaps — corrected in the follow-up

2. **XML load evidence link does not select the run.** `frontend/src/Components/XmlAnalyticsLoader.js:75` builds `#/data-flow?run_id=...`, but `frontend/src/workflows/runTracking.js:6` reads the third slash-separated path segment. Follow the link and the requested run is not restored. Use `pipelineRunLink()`.

3. **Agent inspection button has no consumer on operational pages.** `frontend/src/Components/AgentProposalPanel.js:126` dispatches `depo:inspect-agent-run`. Its listener exists only in `AgentControlPanel`; that panel is mounted in Admin's agents tab. Data Flow and Data Products mount recommendations without the control panel. Inspection there has no page-local effect. Navigate to a run-specific view or mount the shared inspector locally.

4. **Agent execution message treats every nonqueued response as completed.** `frontend/src/Components/AgentProposalPanel.js:75` checks only `status === 'queued'`. Any running or other nonterminal response is labelled completed. Validate response states and describe the actual state before offering completion actions. The problematic response branch exists; verify which states the current execution endpoint emits under timeout/deferred execution.

5. **Data Flow Run now supplies no job input.** `frontend/src/pages/DataFlowPage.js:254` submits `{}` for every job definition. Jobs requiring retained artifact IDs or source records cannot execute meaningfully from this control. In particular, XML analytics requires XSD/XML artifact IDs. Route to a job-specific input form or explicitly replay a selected retained input.

6. **Data Flow concurrent definition actions share one busy identifier.** `frontend/src/pages/DataFlowPage.js:238` stores a single `definitionActionId`, while line 342 disables only the matching definition. Starting B while A is pending overwrites A's identifier; A's controls become enabled. A's completion also clears B's busy state. Use per-definition request locks and per-request completion fencing.

7. **QIF history requests can overwrite newer history.** `frontend/src/pages/QifPage.js:60` has no cancellation or generation check around history refreshes. Concurrent task operations/history refreshes can apply an older list after a newer one, hiding recent status or runs until another refresh. Add request-generation fencing.

8. **Quality page does not clear prior evidence when credentials change.** `frontend/src/pages/QualityPage.js:25` subscribes only to its timer, not credential change/clear events. Its error path retains old rows. Evidence from the prior session can remain displayed after disconnect or reconnection. Clear rows and abort requests on credential events; retain stale snapshots only under the same authenticated session.

## Scope and unresolved count

Reviewed page/component request lifecycles, mutation controls, run navigation, agent inspection, table plumbing and HTML rendering, with frontend regression execution. Graph tooltip escaping and chat HTML sanitization already exist and are not counted as new vulnerabilities. Historical pagination complaints are not counted without current reproduction. These eight items include conditional findings; they are not eight confirmed P1s and are not proof of a complete repository audit.

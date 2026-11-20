import React from 'react';
import { businessText } from '../utils/businessText';

export default function TaskProgress({ run, kind = 'goal', hideGoal = false }) {
  if (!run) return null;
  const result = run.result || run.traces?.at(-1)?.result;
  const held = ['held','blocked','policy_blocked','approval_required','awaiting_approval','review_required'].includes(result?.status);
  const incomplete = ['unknown','unsupported','not_checked','metadata_checks_passed'].includes(result?.status);
  const uncertain = run.reconciliation_required || run.status === 'reconciliation_required';
  const status = uncertain ? 'Outcome needs verification' : held ? 'Review required' : incomplete ? 'Validation incomplete' :
    ({completed:'Review ready',running:'Reviewing the available evidence',queued:'Waiting to begin',failed:'Review could not be completed',blocked:'Review blocked',budget_exhausted:'Review limit reached',interrupted:'Review interrupted',timed_out:'Review took too long',needs_input:'More information needed',cancelled:'Review cancelled',paused:'Review paused'}[run.status] || 'Review in progress');
  const summary = result?.business_summary || result?.summary;
  return <section className="page-task-progress" aria-label="Review outcome">
    {!hideGoal && !result?.recommendation_observation_id && typeof run.goal==='string' && run.goal.trim() && <h4>{businessText(run.goal)}</h4>}
    <p role="status"><strong>{status}</strong></p>
    {summary && <><strong>Findings</strong><p style={{whiteSpace:'pre-line'}}>{businessText(summary)}</p></>}
    {run.status === 'needs_input' && <p role="alert">Choose the business object and provide the missing information before starting a new review.</p>}
    {held && <p>The proposal needs review. No publication is established by task completion.</p>}
    {uncertain && <p>Verify the saved outcome before trying again. A new submission could repeat an earlier action.</p>}
    {kind === 'goal' && ['failed','timed_out'].includes(run.status) && <p role="alert">The available evidence is retained. Refresh the review status or contact your administrator if the issue continues.</p>}
    {kind !== 'goal' && run.status === 'completed' && !held && <p>Review completion is separate from approval and publication.</p>}
  </section>;
}

import React from 'react';
const label = value => String(value || 'unknown').replaceAll('_', ' ');
export default function TaskProgress({ run, kind = 'goal' }) {
  if (!run) return null;
  const actions = kind === 'goal' ? run.observations || [] : run.traces || run.tool_spans || [];
  const result = run.result || run.traces?.at(-1)?.result;
  const held = ['held','blocked','policy_blocked','approval_required','awaiting_approval'].includes(result?.status);
  const uncertain = run.reconciliation_required || run.status === 'reconciliation_required';
  return <section className="page-task-progress" aria-label="Task progress">
    <p role="status"><strong>Status: {uncertain ? 'Outcome needs verification' : held ? 'Review required' : label(run.execution_state || run.status)}</strong></p>
    <p>{kind === 'goal' ? run.goal : run.workflow_id || run.task_label || 'Reviewed action'}</p>
    {run.status === 'needs_input' && <p role="alert">Select or supply: {(run.missing_fields || []).map(label).join(', ')}. Then start a new investigation. No write was performed.</p>}
    {run.status !== 'needs_input' && run.message && <p>{run.message}</p>}
    {run.page_context && <p>Source context: {Object.entries(run.page_context).map(([key,value]) => `${label(key)}: ${value}`).join(' · ')}</p>}
    {run.plans?.length > 0 && <details open><summary>Current plan</summary><ol>{run.plans.at(-1).subtasks.map((step,i)=><li key={i}>{step}</li>)}</ol><p>Planned steps are not evidence that they have executed.</p></details>}
    <p>Recorded actions: {actions.length}. Completed: {actions.filter(item=>item.status==='completed').length}.</p>
    {actions.length > 0 && <details><summary>Actions and retained evidence</summary><ol>{actions.map((item,i)=><li key={item.id || item.sequence || i}>
      <strong>{label(item.tool_id || item.tool || 'Plan check')}</strong> · {label(item.status)}
      {(item.error_message || item.message || item.error_code) && <p>{item.error_message || item.message || label(item.error_code)} {item.status === 'failed' ? 'Retained for the next planning decision.' : ''}</p>}
      {item.result && <p>Result evidence retained{item.result.truncated ? '; only a bounded excerpt is available' : ''}. Source validation and publication are separate.</p>}
      {item.result && <dl>{Object.entries(item.result.result || item.result).filter(([key,value]) => ['iri','ontology_id','preview_id','asset_id','version','status','resources','relationships','triple_count'].includes(key) && ['string','number','boolean'].includes(typeof value)).map(([key,value]) => <React.Fragment key={key}><dt>{label(key)}</dt><dd>{String(value).slice(0,1000)}</dd></React.Fragment>)}</dl>}
    </li>)}</ol></details>}
    {result?.summary && <><strong>Evidence-based conclusion</strong><p>{result.summary}</p>{kind === 'goal' && <p>Agent interpretation for review. Evidence references do not independently verify each claim or grant engineering approval.</p>}{Array.isArray(result.evidence_steps) && <p>Evidence: {result.evidence_steps.join(', ')}. Review the retained observations.</p>}</>}
    {held && <p>The action finished with a review hold. No publication is established by task completion.</p>}
    {uncertain && <p>Verify the retained downstream receipt before retrying. This view never resubmits a write automatically.</p>}
    {run.error_code && <p role="alert">{label(run.error_code)}. Retained evidence remains available.</p>}
    {run.error_type && <p role="alert">{label(run.error_type)}. Inspect the retained task before trying another action.</p>}
    {kind !== 'goal' && run.status === 'completed' && <p>Execution completed. Check the domain workflow for its publication or delivery receipt.</p>}
    <details><summary>Task reference</summary><p>{run.run_id}. {run.updated_at || run.finished_at || run.created_at || run.started_at}</p></details>
  </section>;
}

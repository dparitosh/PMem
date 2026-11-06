import React, { useEffect, useRef, useState } from 'react';
import agenticAPI from '../services/agenticApi';
import { getCredentialProfile } from '../services/serviceAuth';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function WorkflowRecoveryActions({ run, onRefresh, disabled }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [executorStopped, setExecutorStopped] = useState(false);
  const active = useRef(true);
  const inFlight = useRef(false);
  const currentRun = useRef(run?.run_id); currentRun.current = run?.run_id;
  useEffect(() => { setError(''); setExecutorStopped(false); }, [run?.run_id]);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  if (!run?.recover_allowed && !run?.reconcile_allowed) return null;
  const approval = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
  const readOnlyRecovery = run.recovery_requires_approval === false;
  const act = async action => {
    if (inFlight.current) return;
    inFlight.current = true;
    const runId = run.run_id;
    const current = () => active.current && currentRun.current === runId;
    setBusy(true); setError('');
    try {
      const identity = action === 'recover' && readOnlyRecovery ? {} : { approved_by: run.approved_actor || 'workflow-supervisor', approval_token: approval, executor_stopped: executorStopped };
      if (action === 'recover') await agenticAPI.recoverWorkflow(run.run_id, identity);
      else await agenticAPI.reconcileWorkflowReceipt(run.run_id, identity);
      if (current()) await onRefresh();
    } catch (failure) {
      if (current()) setError(apiErrorMessage(failure,
        action === 'recover' ? 'Recovery was not confirmed. Refresh status before retrying.' : 'Receipt verification was not confirmed. Refresh status before retrying.'));
    } finally { inFlight.current = false; if (active.current) setBusy(false); }
  };
  return <div aria-label="Workflow recovery">
    {run.reconcile_allowed && run.executor_stop_verification_required && <label>
      <input type="checkbox" checked={executorStopped} onChange={event => setExecutorStopped(event.target.checked)} />
      I verified that the previous executor has stopped
    </label>}
    {run.reconcile_allowed && <button type="button" disabled={disabled || busy || !approval || (run.executor_stop_verification_required && !executorStopped)} onClick={() => act('receipt')}>Verify publication receipt</button>}
    {run.recover_allowed && <button type="button" disabled={disabled || busy || (readOnlyRecovery ? !getCredentialProfile('GRAPH_READ_TOKEN') : !approval)} onClick={() => act('recover')}>Recover retained workflow</button>}
    {run.recover_allowed && readOnlyRecovery && <small>Resume your advisory review with read access. This does not approve or publish mappings.</small>}
    {error && <p role="alert">{error}</p>}
  </div>;
}

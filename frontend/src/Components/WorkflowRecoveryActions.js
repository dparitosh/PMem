import React, { useEffect, useRef, useState } from 'react';
import agenticAPI from '../services/agenticApi';
import { getCredentialProfile } from '../services/serviceAuth';

export default function WorkflowRecoveryActions({ run, onRefresh, disabled }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [executorStopped, setExecutorStopped] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  if (!run?.recover_allowed && !run?.reconcile_allowed) return null;
  const approval = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
  const act = async action => {
    setBusy(true); setError('');
    try {
      const identity = { approved_by: run.approved_actor || 'workflow-supervisor', approval_token: approval, executor_stopped: executorStopped };
      if (action === 'recover') await agenticAPI.recoverWorkflow(run.run_id, identity);
      else await agenticAPI.reconcileWorkflowReceipt(run.run_id, identity);
      if (active.current) await onRefresh();
    } catch {
      if (active.current) setError('Recovery was not confirmed. Refresh status and inspect the retained task. No write was replayed by receipt verification.');
    } finally { if (active.current) setBusy(false); }
  };
  return <div aria-label="Workflow recovery">
    {run.reconcile_allowed && run.executor_stop_verification_required && <label>
      <input type="checkbox" checked={executorStopped} onChange={event => setExecutorStopped(event.target.checked)} />
      I verified that the previous executor has stopped
    </label>}
    {run.reconcile_allowed && <button type="button" disabled={disabled || busy || !approval || (run.executor_stop_verification_required && !executorStopped)} onClick={() => act('receipt')}>Verify publication receipt</button>}
    {run.recover_allowed && <button type="button" disabled={disabled || busy || !approval} onClick={() => act('recover')}>Recover retained workflow</button>}
    {error && <p role="alert">{error}</p>}
  </div>;
}

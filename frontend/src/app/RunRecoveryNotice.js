import React, { useEffect, useState, useRef } from 'react';
import agenticAPI from '../services/agenticApi';
import { dataPipelineAPI } from '../services/apiClient';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { readRecoveryRuns, saveRecoveryRuns, validRecoveryRun } from '../services/runRecovery';
import useMountedRef from '../hooks/useMountedRef';

function RecoveryRun({ run, onDismiss }) {
  const mounted = useMountedRef();
  const sequence = useRef(0);
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const reset = () => { sequence.current++; setState(null); setError(''); setBusy(false); };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, reset));
    return () => events.forEach(event => window.removeEventListener(event, reset));
  }, []);
  return <aside role="alert"><p>Execution needs review. {run.kind} run: {run.runId}. Inspect retained state before retrying.</p>
    <button type="button" disabled={busy} onClick={async () => {
      const requestSequence = ++sequence.current;
      setBusy(true); setError('');
      try {
        const response = await (run.kind === 'pipeline' ? dataPipelineAPI.getRun(run.runId) : agenticAPI.getRun(run.runId, run.kind));
        if (run.kind === 'pipeline' && response.data?.run_id !== run.runId) throw new Error('The status response does not match this pipeline run.');
        if (mounted.current && sequence.current === requestSequence) setState(response.data);
      } catch (failure) { if (mounted.current && sequence.current === requestSequence) setError(apiErrorMessage(failure)); }
      finally { if (mounted.current && sequence.current === requestSequence) setBusy(false); }
    }}>Load retained run status</button>
    {state && <p>Status: {state.status}. {state.reconciliation_required ? 'Reconcile downstream writes before retrying.' : 'Review the execution outcome before retrying.'}</p>}
    {error && <p>{error}</p>}
    <button type="button" onClick={onDismiss}>Dismiss</button>
  </aside>;
}
export default function RunRecoveryNotice() {
  const [runs, setRuns] = useState(readRecoveryRuns);
  useEffect(() => {
    const receive = event => {
      if (!validRecoveryRun(event.detail)) return;
      const run = { runId: event.detail.runId, kind: event.detail.kind };
      setRuns(previous => {
        if (previous.some(item => item.runId === run.runId && item.kind === run.kind)) return previous;
        const next = [...previous, run]; saveRecoveryRuns(next); return next;
      });
    };
    window.addEventListener('depo:run-recovery', receive);
    return () => window.removeEventListener('depo:run-recovery', receive);
  }, []);
  return <>{runs.map(run => <RecoveryRun key={`${run.kind}:${run.runId}`} run={run} onDismiss={() => setRuns(previous => {
    const next = previous.filter(item => item.runId !== run.runId || item.kind !== run.kind);
    saveRecoveryRuns(next); return next;
  })} />)}</>;
}
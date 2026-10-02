import React, { useEffect, useState, useRef } from 'react';
import agenticAPI from '../services/agenticApi';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import useMountedRef from '../hooks/useMountedRef';
export default function RunRecoveryNotice() {
  const mounted = useMountedRef();
  const sequence = useRef(0);
  const [run, setRun] = useState(null);
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const receive = event => { sequence.current++; setRun(event.detail); setState(null); setError(''); setBusy(false); };
    window.addEventListener('depo:run-recovery', receive);
    return () => window.removeEventListener('depo:run-recovery', receive);
  }, []);
  if (!run) return null;
  return <aside role="alert"><p>Execution needs review. {run.kind} run: {run.runId}. Inspect retained state before retrying.</p>
    <button type="button" disabled={busy} onClick={async () => {
      const requestSequence = ++sequence.current;
      setBusy(true); setError('');
      try { const response = await agenticAPI.getRun(run.runId, run.kind); if (mounted.current && sequence.current === requestSequence) setState(response.data); }
      catch (failure) { if (mounted.current && sequence.current === requestSequence) setError(apiErrorMessage(failure)); }
      finally { if (mounted.current && sequence.current === requestSequence) setBusy(false); }
    }}>Load retained run status</button>
    {state && <p>Status: {state.status}. {state.reconciliation_required ? 'Reconcile downstream writes before retrying.' : 'Review the execution outcome before retrying.'}</p>}
    {error && <p>{error}</p>}
    <button type="button" onClick={() => { sequence.current++; setRun(null); setBusy(false); }}>Dismiss</button>
  </aside>;
}

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { dataPipelineAPI } from '../services/apiClient';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { pipelineRunLink } from '../workflows/runTracking';
import { qualityRunsPayload } from '../services/pagePayloads';

export default function QualityPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState(null);
  const request = useRef(null);
  const load = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError('');
    try {
      const response = await dataPipelineAPI.runs(100, { signal: controller.signal, timeout: 15000 });
      if (controller.signal.aborted) return;
      const body = response.data?.data || response.data;
      setRuns(qualityRunsPayload(body?.runs)); setUpdated(new Date());
    } catch (failure) {
      if (!controller.signal.aborted) setError(apiErrorMessage(failure, 'Quality evidence is unavailable.'));
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }, []);
  useEffect(() => {
    load(); const timer = window.setInterval(() => { if (!document.hidden) load(); }, 30000);
    const clear = () => { request.current?.abort(); setRuns([]); setUpdated(null); setError(''); setLoading(false); };
    const reconnect = () => { clear(); load(); };
    window.addEventListener('depo:credentials-changed', reconnect);
    window.addEventListener('depo:credentials-cleared', clear);
    window.addEventListener('depo:session-expired', clear);
    return () => { window.clearInterval(timer); request.current?.abort(); window.removeEventListener('depo:credentials-changed', reconnect); window.removeEventListener('depo:credentials-cleared', clear); window.removeEventListener('depo:session-expired', clear); };
  }, [load]);
  return <div className="depo-page" aria-busy={loading}>
    <section className="depo-panel">
      <h2>Data Quality</h2>
      <p>Evidence from the latest 100 retained pipeline runs. Execution completion alone does not establish data quality conformance.</p>
      <button type="button" className="depo-button" disabled={loading} onClick={load}>{loading ? 'Refreshing…' : 'Refresh quality evidence'}</button>
      {updated && <p>Snapshot: {updated.toLocaleString()}{error ? ' — stale' : ''}</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && !runs.length && <p>No retained runs. Configure and execute a quality job in Data Flow to generate evidence.</p>}
      <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', color: 'var(--ui-text)' }}>
        <caption>Job execution and recorded quality measurements</caption>
        <thead><tr><th scope="col">Run</th><th scope="col">Job / profile</th><th scope="col">Execution</th><th scope="col">Quality evidence</th></tr></thead>
        <tbody>{runs.map(run => {
          const counts = run.output_manifest?.counts;
          const metrics = counts && Object.entries(counts).filter(([, value]) => typeof value === 'number' && Number.isFinite(value));
          return <tr key={run.run_id}>
            <td><a href={pipelineRunLink(run.run_id)}>{run.run_id}</a></td>
            <td>{run.job_type || run.job_id}<br />{run.quality_profile || 'Profile not recorded'}</td>
            <td>{run.status || 'unknown'}</td>
            <td>{metrics?.length ? metrics.map(([name, value]) => <div key={name}>{name.replaceAll('_', ' ')}: {value}</div>) : 'Not recorded'}</td>
          </tr>;
        })}</tbody>
      </table></div>
      <a href="#/data-flow">Open Data Flow for definitions, approvals and run details</a>
    </section>
  </div>;
}

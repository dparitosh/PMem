import React, { useCallback, useEffect, useRef, useState } from 'react';
import { dataPipelineAPI } from '../services/apiClient';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { pipelineRunLink } from '../workflows/runTracking';
import { qualityRunsPayload } from '../services/pagePayloads';
import './QualityPage.css';

const measurements = run => Object.entries(run.output_manifest?.counts || {}).filter(([, value]) => typeof value === 'number' && Number.isFinite(value));
const failed = run => ['failed', 'error', 'cancelled', 'canceled'].includes(run.status);
const active = run => ['queued', 'pending', 'running', 'processing'].includes(run.status);

export default function QualityPage() {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
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
  const visible = runs.filter(run => {
    const match = `${run.run_id} ${run.job_type || ''} ${run.job_id || ''} ${run.quality_profile || ''}`.toLowerCase().includes(search.toLowerCase());
    return match && (filter === 'all' || (filter === 'attention' && failed(run)) || (filter === 'active' && active(run)) || (filter === 'evidence' && measurements(run).length > 0));
  });
  const summaries = [
    ['Retained runs', runs.length, 'Latest 100 runs'],
    ['With measurements', runs.filter(run => measurements(run).length).length, 'Recorded numeric evidence'],
    ['Execution needs attention', runs.filter(failed).length, 'Failed or cancelled runs'],
    ['In progress', runs.filter(active).length, 'Queued or running'],
  ];
  return <div className="depo-page quality-workspace">
    <header className="quality-header">
      <div><span className="quality-eyebrow">QUALITY ASSURANCE</span><h2>Understand your data readiness</h2><p>Review processing outcomes and recorded measurements before you reuse or publish data.</p></div>
      <div className="quality-header__actions"><button type="button" className="depo-button" disabled={loading} onClick={load}>{loading ? 'Refreshing…' : 'Refresh quality evidence'}</button><span>{updated ? `Updated ${updated.toLocaleTimeString()}${error ? ' · stale snapshot' : ''}` : 'Waiting for evidence'}</span></div>
    </header>
    {error && <div className="quality-notice quality-notice--error" role="alert">{error}{updated && ' Previously loaded results remain visible.'}</div>}
    <section className="quality-summary" aria-label="Quality evidence overview" aria-busy={loading}>
      {summaries.map(([label, value, hint]) => <div key={label}><span>{label}</span><strong>{updated ? value.toLocaleString() : '—'}</strong><small>{hint}</small></div>)}
    </section>
    <div className="quality-notice"><strong>Execution status is not a quality verdict.</strong> Measurements below are retained evidence, not a conformance score. Review validation results and source context in the run details.</div>
    <section className="quality-results" aria-label="Quality run evidence">
      <div className="quality-results__heading"><div><h3>Evidence review</h3><p>Latest 100 retained pipeline runs · {visible.length} shown</p></div><a href="#/data-flow">Manage quality jobs in Data Flow →</a></div>
      <div className="quality-toolbar"><label>Find a run or job<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search job, profile or run" /></label><label>Show<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All runs</option><option value="attention">Execution needs attention</option><option value="evidence">With measurements</option><option value="active">In progress</option></select></label></div>
      {loading && !updated && <div className="quality-empty" role="status">Loading quality evidence…</div>}
      {!loading && !error && !runs.length && <div className="quality-empty"><h3>Start building quality evidence</h3><p>No retained runs are available. Choose and execute a quality job in Data Flow, then return here to review its results.</p><a href="#/data-flow">Open Data Flow →</a></div>}
      {updated && !visible.length && runs.length > 0 && <div className="quality-empty">No runs match these filters. Try another search or choose All runs.</div>}
      {visible.length > 0 && <div className="quality-table-scroll" tabIndex={0} role="region" aria-label="Scrollable quality results"><table>
        <caption className="quality-sr-only">Job execution and recorded quality measurements</caption>
        <thead><tr><th scope="col">Job &amp; profile</th><th scope="col">Execution</th><th scope="col">Recorded measurements</th><th scope="col">Run details</th></tr></thead>
        <tbody>{visible.map(run => <tr key={run.run_id}>
          <td><strong>{(run.job_type || run.job_id || 'Unnamed job').replaceAll('_', ' ')}</strong><small>{run.quality_profile || 'Profile not recorded'}</small></td>
          <td><span className={`quality-status ${failed(run) ? 'quality-status--attention' : active(run) ? 'quality-status--active' : ''}`}>{(run.status || 'unknown').replaceAll('_', ' ')}</span></td>
          <td>{measurements(run).length ? <dl className="quality-measurements">{measurements(run).map(([name, value]) => <div key={name}><dt>{name.replaceAll('_', ' ')}</dt><dd>{value.toLocaleString()}</dd></div>)}</dl> : <span className="quality-muted">No numeric measurements recorded</span>}</td>
          <td><a href={pipelineRunLink(run.run_id)} aria-label={`Review run ${run.run_id}`}>Review run →</a><small className="quality-run-id">{run.run_id}</small></td>
        </tr>)}</tbody>
      </table></div>}
    </section>
  </div>;
}

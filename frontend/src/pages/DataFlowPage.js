import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { dataPipelineAPI } from '../services/apiClient';
import './DataFlowPage.css';

const REFRESH_INTERVAL_MS = 15000;

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

// The gateway returns the OpenAPI response body directly, while the local
// development proxy can preserve one compatibility envelope.  Keeping that
// difference at this boundary prevents a healthy Data Flow page from looking
// empty merely because the deployment route changed.
function responsePayload(response) {
  const body = response?.data ?? response;
  return body?.data && typeof body.data === 'object' && !Array.isArray(body.data)
    ? body.data
    : body;
}

function requestedRunId() {
  if (typeof window === 'undefined') return '';
  const parts = String(window.location.hash || '').split('?')[0].split('/');
  return parts[2] ? decodeURIComponent(parts[2]) : '';
}

function displayTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function countFor(run, field) {
  const counts = run?.output_manifest?.counts || run?.quality || {};
  const aliases = field.includes('accepted')
    ? ['accepted_records', 'records_accepted', 'normalized_entities', 'accepted_documents', 'valid_ntriples']
    : ['rejected_records', 'records_rejected', 'rejected_documents', 'malformed_lines'];
  const value = aliases.find((name) => counts[name] !== undefined);
  return Number(value ? counts[value] : 0);
}

function qualityStatus(run) {
  if (run?.status === 'failed') return 'failed';
  if (countFor(run, 'records_rejected') > 0 || countFor(run, 'rejected_records') > 0) return 'warning';
  return run?.status || 'completed';
}

function sourceStandard(run) {
  return run?.source_standard || run?.output_manifest?.source_standard || 'Not recorded';
}

function Status({ value }) {
  const normalized = String(value || 'unknown').toLowerCase();
  return <span className={`data-flow-status data-flow-status--${normalized}`}>{value || 'unknown'}</span>;
}

export default function DataFlowPage() {
  const [health, setHealth] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [runs, setRuns] = useState([]);
  const [definitions, setDefinitions] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [replayError, setReplayError] = useState('');
  const [replayingId, setReplayingId] = useState('');

  const load = useCallback(async ({ initial = false } = {}) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError('');
    try {
      const [healthResult, telemetryResult, runsResult, definitionsResult] = await Promise.allSettled([
        dataPipelineAPI.health(),
        dataPipelineAPI.telemetry(),
        dataPipelineAPI.runs(100),
        dataPipelineAPI.definitions(),
      ]);
      const successes = [healthResult, telemetryResult, runsResult, definitionsResult]
        .filter((result) => result.status === 'fulfilled');
      if (!successes.length) throw healthResult.reason || new Error('Data pipeline service is unavailable.');
      const healthPayload = healthResult.status === 'fulfilled' ? responsePayload(healthResult.value) : null;
      const telemetryPayload = telemetryResult.status === 'fulfilled' ? responsePayload(telemetryResult.value) : null;
      const runsPayload = runsResult.status === 'fulfilled' ? responsePayload(runsResult.value) : null;
      const definitionsPayload = definitionsResult.status === 'fulfilled' ? responsePayload(definitionsResult.value) : null;
      setHealth(healthPayload);
      setTelemetry(telemetryPayload);
      const nextRuns = asArray(runsPayload?.runs);
      setRuns(nextRuns);
      setDefinitions(asArray(definitionsPayload?.definitions));
      const requestedId = requestedRunId();
      setSelectedRun((current) =>
        nextRuns.find((run) => run.run_id === requestedId)
        || nextRuns.find((run) => run.run_id === current?.run_id)
        || nextRuns[0]
        || null
      );
      const failure = [healthResult, telemetryResult, runsResult, definitionsResult]
        .find((result) => result.status === 'rejected');
      if (failure) setError('Some processing-job evidence is temporarily unavailable. Showing the available data.');
    } catch (loadError) {
      setError(loadError?.response?.data?.detail || loadError?.message || 'Unable to load data-job telemetry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load({ initial: true });
    const interval = window.setInterval(() => load(), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  const visibleRuns = useMemo(() => {
    const term = filter.trim().toLowerCase();
    if (!term) return runs;
    return runs.filter((run) => [run.job_id, run.job_type, run.status, run.correlation_id, sourceStandard(run)]
      .some((value) => String(value || '').toLowerCase().includes(term)));
  }, [filter, runs]);

  const totals = telemetry?.durable_job_telemetry || telemetry?.totals || {};
  const durableTotals = useMemo(() => ({
    runs: runs.length,
    accepted: runs.reduce((sum, run) => sum + countFor(run, 'accepted_records'), 0),
    rejected: runs.reduce((sum, run) => sum + countFor(run, 'rejected_records'), 0),
  }), [runs]);

  const replay = async (run) => {
    setReplayingId(run.run_id);
    setReplayError('');
    try {
      await dataPipelineAPI.replay(run.run_id);
      await load();
    } catch (replayFailure) {
      setReplayError(replayFailure?.response?.data?.detail || replayFailure?.message || 'Replay could not be started.');
    } finally {
      setReplayingId('');
    }
  };

  return (
    <section className="data-flow-page" aria-labelledby="data-flow-title">
      <header className="data-flow-page__header">
        <div>
          <p className="data-flow-page__eyebrow">Data processing operations</p>
          <h1 id="data-flow-title">Data Flow</h1>
          <p>Operational evidence for configured Spark and semantic processing jobs. Refreshes every 15 seconds.</p>
        </div>
        <div className="data-flow-page__actions">
          <Status value={health?.status || health?.spark?.status || 'checking'} />
          <button className="data-flow-button" type="button" onClick={() => load()} disabled={refreshing}>
            <ix-icon name="refresh" aria-hidden="true" /> {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="data-flow-notice" role="status">{error}</div>}
      {replayError && <div className="data-flow-notice data-flow-notice--error" role="alert">{replayError}</div>}

      <div className="data-flow-kpis" aria-label="Data-job telemetry summary">
        <article><span>Configured jobs</span><strong>{definitions.length}</strong></article>
        <article><span>Durable runs</span><strong>{durableTotals.runs || totals.runs || 0}</strong></article>
        <article><span>Accepted records</span><strong>{durableTotals.accepted || totals.records_accepted || 0}</strong></article>
        <article><span>Rejected records</span><strong>{durableTotals.rejected || totals.records_rejected || 0}</strong></article>
        <article><span>Scheduler</span><strong className="data-flow-kpi-state">{telemetry?.scheduler?.running ? 'Running' : telemetry?.scheduler?.enabled ? 'Stopped' : 'Disabled'}</strong></article>
      </div>

      <div className="data-flow-grid">
        <article className="data-flow-card data-flow-card--runs">
          <div className="data-flow-card__heading">
            <div><h2>Processing-job runs</h2><p>Durable run manifests, quality outcome, and replay status.</p></div>
            <label className="data-flow-filter">Filter<input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Job, source, type, status…" /></label>
          </div>
          {loading ? <div className="data-flow-empty"><ix-spinner size="medium" /> Loading job evidence…</div> : (
            <div className="data-flow-table-wrap">
              <table className="data-flow-table">
                <thead><tr><th>Job</th><th>Source</th><th>Started</th><th>Quality</th><th>Status</th><th aria-label="Actions" /></tr></thead>
                <tbody>
                  {visibleRuns.map((run) => <tr key={run.run_id} className={selectedRun?.run_id === run.run_id ? 'is-selected' : ''}>
                    <td><button className="data-flow-link" type="button" onClick={() => setSelectedRun(run)}>{run.job_id || run.job_type || 'Unnamed job'}</button><small>{run.job_version || '—'} · {run.job_type || 'processing job'}</small></td>
                    <td><span className="data-flow-source">{sourceStandard(run)}</span></td>
                    <td>{displayTime(run.started_at)}</td>
                    <td>{countFor(run, 'accepted_records')} accepted · {countFor(run, 'rejected_records')} rejected</td>
                    <td><Status value={qualityStatus(run)} /></td>
                    <td><button className="data-flow-replay" type="button" onClick={() => replay(run)} disabled={replayingId === run.run_id || run.status === 'running'}>{replayingId === run.run_id ? 'Replaying…' : 'Replay'}</button></td>
                  </tr>)}
                  {!visibleRuns.length && <tr><td colSpan="6" className="data-flow-empty">No durable job runs match the current filter.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <aside className="data-flow-card data-flow-card--evidence" aria-live="polite">
          <h2>Run evidence</h2>
          {selectedRun ? <>
            <dl className="data-flow-evidence">
              <dt>Run ID</dt><dd>{selectedRun.run_id}</dd>
              <dt>Source standard</dt><dd>{sourceStandard(selectedRun)}</dd>
              <dt>Source system</dt><dd>{selectedRun.source_system || selectedRun.output_manifest?.source_system || 'Not recorded'}</dd>
              <dt>Input manifest</dt><dd>{selectedRun.input_manifest?.record_count ?? 0} record(s), {selectedRun.input_manifest?.artifact_ids?.length ?? 0} retained artifact(s)</dd>
              <dt>Quality profile</dt><dd>{selectedRun.job_type || '—'} / {qualityStatus(selectedRun)}</dd>
              <dt>Checkpoint</dt><dd>{selectedRun.checkpoint ? JSON.stringify(selectedRun.checkpoint) : 'No watermark/checkpoint recorded'}</dd>
              <dt>Lineage</dt><dd>{selectedRun.correlation_id || 'No correlation identifier recorded'}</dd>
              <dt>Executed by</dt><dd>{selectedRun.executed_by || 'Legacy run / identity not recorded'}</dd>
              <dt>Replay lineage</dt><dd>{selectedRun.replay_of || 'Original execution'}</dd>
              <dt>Output evidence</dt><dd>{selectedRun.output_manifest?.contract || 'Pending output manifest'}</dd>
              <dt>Mapping evidence</dt><dd>{selectedRun.output_manifest?.mapping_digest || 'Not applicable or not recorded'}</dd>
              <dt>Validation</dt><dd>{selectedRun.output_manifest?.validation_status || 'Not applicable or pending'}</dd>
            </dl>
            <p className="data-flow-help">Replay reuses the retained immutable input; publication still remains subject to the canonical approval boundary.</p>
          </> : <div className="data-flow-empty">Select a run to inspect its input, quality, lineage, checkpoint, and output evidence.</div>}
        </aside>
      </div>
    </section>
  );
}

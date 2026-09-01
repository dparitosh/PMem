import { useCallback, useEffect, useState } from 'react';
import { qifAPI } from '../services/apiClient';
import KpiStrip from '../widgets/KpiStrip';
import { CheckCircle2, Loader2, RefreshCw, Upload, Workflow, X } from '../ui/IxIcons';
import QifDigitalThreadOverview from './qif/QifDigitalThreadOverview';
import './QifPage.css';

const panelStyle = { background: '#fff', border: '1px solid #d8e0e8', borderRadius: 6, padding: 16 };
const inputStyle = { width: '100%', boxSizing: 'border-box', border: '1px solid #aebbc7', borderRadius: 4, padding: '8px 10px', font: 'inherit' };
const terminal = new Set(['completed', 'completed_with_warnings', 'failed', 'cancelled', 'awaiting_approval', 'requires_review']);

function detailOf(error) {
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : detail?.message || error.message || 'The QIF workflow could not be completed.';
}

function statusLabel(status) {
  return String(status || 'unknown').replaceAll('_', ' ');
}

function taskOutcome(task) {
  if (!task) return 'No task selected';
  if (task.status === 'awaiting_approval') return 'Review required before publishing';
  if (task.status === 'completed') return 'Ontology published and graph synchronized';
  if (task.status === 'completed_with_warnings') return 'Ontology published; graph synchronization needs review';
  if (task.status === 'failed') return 'Workflow failed; review validation and events';
  return `Workflow ${statusLabel(task.status)}`;
}

export default function QifPage({ workflowMode = false }) {
  const [catalog, setCatalog] = useState(null);
  const [agents, setAgents] = useState([]);
  const [files, setFiles] = useState([]);
  const [name, setName] = useState('QIF 3.0 Ontology');
  const [prefix, setPrefix] = useState('qif');
  const [description, setDescription] = useState('Consolidated ontology generated from the QIF schema set.');
  const [task, setTask] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshHistory = useCallback(() => qifAPI.listTasks().then((response) => setHistory(response.data?.tasks || [])).catch(() => {}), []);
  const refreshTask = useCallback(async (taskId) => {
    const response = await qifAPI.getTask(taskId);
    setTask(response.data);
    setHistory((items) => items.map((item) => item.task_id === taskId ? { ...item, ...response.data } : item));
    return response.data;
  }, []);

  useEffect(() => {
    let active = true;
    const loadWorkspace = async () => {
      try {
        const [catalogResponse, agentResponse, taskResponse] = await Promise.all([qifAPI.catalog(), qifAPI.agents(), qifAPI.listTasks()]);
        if (!active) return;
        const tasks = taskResponse.data?.tasks || [];
        setCatalog(catalogResponse.data);
        setAgents(agentResponse.data?.agents || []);
        setHistory(tasks);
        // Make the page immediately useful: restore the latest run and its
        // results instead of leaving a blank workspace after a refresh.
        if (tasks[0]?.task_id) {
          const taskResponse = await qifAPI.getTask(tasks[0].task_id);
          if (active) setTask(taskResponse.data);
        }
      } catch (_requestError) {
        if (active) setError('The QIF service is unavailable. Start the backend and refresh this page.');
      } finally {
        if (active) setLoading(false);
      }
    };
    loadWorkspace();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!task?.task_id || terminal.has(task.status)) return undefined;
    const timer = window.setInterval(() => refreshTask(task.task_id).catch((requestError) => setError(detailOf(requestError))), 1000);
    return () => window.clearInterval(timer);
  }, [task?.task_id, task?.status, refreshTask]);

  const metadata = { ontology_name: name, prefix, description };
  const start = async (source) => {
    setActionBusy(true); setError(''); setTask(null);
    try {
      const response = source === 'reference'
        ? await qifAPI.startReferenceTask(metadata)
        : await qifAPI.startUploadTask(files, metadata);
      await refreshTask(response.data.task_id);
      await refreshHistory();
    } catch (requestError) { setError(detailOf(requestError)); }
    finally { setActionBusy(false); }
  };
  const commit = async () => {
    setActionBusy(true); setError('');
    try { await qifAPI.commit(task.task_id); await refreshTask(task.task_id); await refreshHistory(); }
    catch (requestError) { setError(detailOf(requestError)); }
    finally { setActionBusy(false); }
  };
  const cancel = async () => {
    setActionBusy(true); setError('');
    try { const response = await qifAPI.cancel(task.task_id); setTask(response.data); await refreshHistory(); }
    catch (requestError) { setError(detailOf(requestError)); }
    finally { setActionBusy(false); }
  };
  const retryGraph = async () => {
    setActionBusy(true); setError('');
    try { await qifAPI.retryGraph(task.task_id); await refreshTask(task.task_id); await refreshHistory(); }
    catch (requestError) { setError(detailOf(requestError)); }
    finally { setActionBusy(false); }
  };
  const refreshWorkspace = async () => {
    setActionBusy(true); setError('');
    try {
      const [catalogResponse, agentResponse] = await Promise.all([qifAPI.catalog(), qifAPI.agents()]);
      setCatalog(catalogResponse.data);
      setAgents(agentResponse.data?.agents || []);
      await refreshHistory();
      if (task?.task_id) await refreshTask(task.task_id);
    } catch (requestError) { setError(detailOf(requestError)); }
    finally { setActionBusy(false); }
  };
  const openTask = async (taskId) => {
    setActionBusy(true); setError('');
    try { await refreshTask(taskId); }
    catch (requestError) { setError(detailOf(requestError)); }
    finally { setActionBusy(false); }
  };
  const canBuildUpload = files.length > 0 && name.trim() && prefix.trim() && !actionBusy;
  const canBuildReference = catalog?.file_count > 0 && name.trim() && prefix.trim() && !actionBusy;
  const validation = task?.validation;
  const summary = task?.summary;
  const graphSync = task?.graph_sync?.detail;

  return (
    <div className="depo-page" aria-busy={loading || actionBusy}>
      <header style={{ marginBottom: 16 }}>
        <div className="depo-panel__meta">{workflowMode ? 'QIF schema workflow' : 'QIF ontology details'}</div>
        <h2 style={{ margin: '4px 0 6px' }}>{workflowMode ? 'Build and publish a QIF ontology' : 'QIF ontology results and traceability'}</h2>
        <p className="depo-panel__meta">{workflowMode ? 'Process a complete XSD schema set through inspection, dependency checks, validation, review, and graph synchronization.' : 'Review QIF schema coverage, validation, generated ontology artifacts, and graph synchronization for a selected run.'}</p>
      </header>
      <KpiStrip items={workflowMode ? [
        { label: 'Reference schemas', value: loading ? '…' : catalog?.file_count ?? '—' }, { label: 'Selected files', value: files.length },
        { label: 'Recent tasks', value: history.length }, { label: 'Workflow state', value: task?.status?.replaceAll('_', ' ') || 'Idle' },
      ] : [
        { label: 'QIF schemas', value: loading ? '…' : summary?.files_processed ?? catalog?.file_count ?? '—' },
        { label: 'Ontology classes', value: summary?.classes_created ?? '—' },
        { label: 'Semantic properties', value: summary?.properties_created ?? '—' },
        { label: 'Graph relationships', value: graphSync?.relationships_merged ?? '—' },
      ]} />

      {!workflowMode && <QifDigitalThreadOverview task={task} />}

      {workflowMode && task && <section className="qif-outcome" aria-label="Selected QIF workflow result">
        <div>
          <div className="depo-panel__meta">Selected QIF run</div>
          <div className="qif-outcome__title">{task.ontology_name}</div>
          <p>{taskOutcome(task)}</p>
        </div>
        <div className="qif-outcome__facts">
          <span><strong>{task.source_files?.length || 0}</strong> source files</span>
          <span><strong>{task.validation?.valid === true ? 'Passed' : task.validation ? 'Needs review' : 'Pending'}</strong> validation</span>
          <span><strong>{statusLabel(task.graph_sync?.status)}</strong> graph sync</span>
        </div>
        <div className="qif-outcome__actions">
          {task.artifacts?.length > 0 && <a className="depo-button depo-button--secondary" href={`#qif-artifacts-${task.task_id}`}>View artifacts</a>}
          {task.ontology_id && <a className="depo-button" href="#/graph">Open graph explorer</a>}
        </div>
      </section>}

      {workflowMode && <div className="depo-widget-grid qif-start-grid">
        <section style={panelStyle}>
          <div className="depo-panel__title">1. Start a schema-set task</div>
          <p className="depo-panel__meta">Select up to 40 related XSD files. The workflow records each source, validates dependency closure, and pauses for review before persistence.</p>
          <label htmlFor="qif-schema-files" style={{ display: 'block', fontSize: 12, fontWeight: 700, marginTop: 14, marginBottom: 6 }}>Select QIF XSD files</label>
          <input id="qif-schema-files" style={inputStyle} type="file" accept=".xsd,application/xml,text/xml" multiple aria-describedby="qif-file-help" onChange={(event) => setFiles(Array.from(event.target.files || []))} />
          <div id="qif-file-help" className="qif-helper-text">Maximum 40 files, 10 MB each. Include every locally referenced XSD.</div>
          {files.length > 0 && <div className="qif-file-list" aria-live="polite">{files.map((file) => file.name).join(', ')}</div>}
          <button type="button" disabled={!canBuildUpload} onClick={() => start('upload')} style={{ marginTop: 14 }} className="depo-action-button">{actionBusy ? <Loader2 size={15} /> : <Upload size={15} />} Start selected-files task</button>
        </section>
        <section style={panelStyle}>
          <div className="depo-panel__title">Bundled QIF 3.0 reference</div>
          <p className="depo-panel__meta">{loading ? 'Loading reference catalog…' : `${catalog?.file_count ?? 0} XSD files are available from the QIF application and library folders.`}</p>
          <button type="button" disabled={!canBuildReference} onClick={() => start('reference')} style={{ marginTop: 14 }} className="depo-action-button">{actionBusy ? <Loader2 size={15} /> : <Workflow size={15} />} Start reference task</button>
          {catalog?.files?.length > 0 && <div style={{ marginTop: 14, fontSize: 12, color: '#52606d' }}>Includes {catalog.files.slice(0, 5).map((file) => file.name).join(', ')}{catalog.files.length > 5 ? ', …' : ''}</div>}
        </section>
      </div>}

      {workflowMode && <section style={{ ...panelStyle, marginTop: 14 }}>
        <div className="depo-panel__title">Task metadata</div>
        <div className="depo-form-grid" style={{ marginTop: 12 }}>
          <label htmlFor="qif-ontology-name">Ontology name<input id="qif-ontology-name" style={inputStyle} value={name} maxLength="100" required onChange={(event) => setName(event.target.value)} /></label>
          <label htmlFor="qif-prefix">Prefix<input id="qif-prefix" style={inputStyle} value={prefix} maxLength="50" required pattern="[A-Za-z][A-Za-z0-9_]*" aria-describedby="qif-prefix-help" onChange={(event) => setPrefix(event.target.value.replace(/[^A-Za-z0-9_]/g, ''))} /></label>
          <span id="qif-prefix-help" className="qif-helper-text">Start with a letter; use letters, numbers, and underscores only.</span>
          <label className="qif-description-field" htmlFor="qif-description">Description<textarea id="qif-description" style={{ ...inputStyle, minHeight: 74, resize: 'vertical' }} value={description} maxLength="500" onChange={(event) => setDescription(event.target.value)} /></label>
        </div>
      </section>}

      {workflowMode && task && <section style={{ ...panelStyle, marginTop: 14 }} aria-label="Selected QIF task details">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}><div><div className="depo-panel__title">2. Task progress</div><div className="depo-panel__meta">Task {task.task_id} · {task.source_files?.length || 0} source files</div></div><strong role="status" aria-live="polite" style={{ textTransform: 'capitalize' }}>{statusLabel(task.status)}</strong></div>
        <div className="qif-progress" role="progressbar" aria-label="QIF task progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={task.progress || 0}><div style={{ width: `${task.progress || 0}%`, background: task.status === 'failed' ? '#c73e1d' : '#008c95' }} /></div>
        <div className="qif-stage-grid">{['inspect', 'validate', 'generate', 'review', 'register', 'graph_sync'].map((stage) => <div key={stage} className={task.stage.startsWith(stage) ? 'is-current' : ''}>{stage.replace('_', ' ')}</div>)}</div>
        <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 6 }}>{task.source_files?.map((file) => <div key={file} style={{ padding: '6px 8px', background: '#f7f9fb', fontSize: 12 }}><CheckCircle2 size={13} /> {file}</div>)}</div>
        {workflowMode && task.status === 'awaiting_approval' && <div style={{ marginTop: 14, display: 'flex', gap: 8 }}><button type="button" className="depo-action-button" disabled={actionBusy} onClick={commit}><CheckCircle2 size={15} /> Approve and publish ontology</button><button type="button" className="depo-action-button" disabled={actionBusy} onClick={cancel} style={{ background: '#fff', color: '#8a1c0b', borderColor: '#c73e1d' }}><X size={15} /> Cancel</button></div>}
        {workflowMode && !terminal.has(task.status) && <button type="button" className="depo-action-button" disabled={actionBusy} onClick={cancel} style={{ marginTop: 14, background: '#fff', color: '#8a1c0b', borderColor: '#c73e1d' }}><X size={15} /> Cancel task</button>}
      </section>}

      {workflowMode && validation && <section style={{ ...panelStyle, marginTop: 14, borderColor: validation.valid ? '#57a773' : '#d14343' }}><div className="depo-panel__title">3. Validation and dependency review</div><p className="depo-panel__meta">{validation.valid ? `${validation.resolved_references.length} local references resolved across ${validation.namespace_count} namespace(s).` : 'Resolve the blocking errors before continuing.'}</p>{validation.errors?.map((item, index) => <div key={`error-${index}`} className="qif-message qif-message--error">{item.file}: {item.error}</div>)}{validation.warnings?.map((item, index) => <div key={`warning-${index}`} className="qif-message qif-message--warning">{item.source ? `${item.source}: ` : ''}{item.message}</div>)}</section>}

      {workflowMode && task?.summary && <section id={`qif-artifacts-${task.task_id}`} style={{ ...panelStyle, marginTop: 14 }}><div className="depo-panel__title">4. Ontology preview and artifacts</div><p className="depo-panel__meta">{task.summary.files_processed} files · {task.summary.classes_created} classes · {task.summary.properties_created} properties · {task.summary.references_found} schema references.</p><div className="qif-artifact-list">{task.artifacts?.map((artifact) => <a key={artifact.path} href={qifAPI.artifactUrl(task.task_id, artifact.path)}>{artifact.name}<small>{artifact.kind}</small></a>)}</div>{task.graph_sync?.status && <div style={{ marginTop: 10, fontSize: 12 }}>Graph synchronization: {statusLabel(task.graph_sync.status)}</div>}{task.graph_sync?.status === 'failed' && <button type="button" className="depo-action-button" disabled={actionBusy} style={{ marginTop: 10 }} onClick={retryGraph}><Workflow size={15} /> Retry graph synchronization</button>}</section>}

      {workflowMode && task?.events?.length > 0 && <section style={{ ...panelStyle, marginTop: 14 }}><div className="depo-panel__title">Task event trail</div>{task.events.map((event, index) => <div key={`${event.at}-${index}`} style={{ display: 'grid', gridTemplateColumns: '120px 105px 1fr', gap: 8, borderTop: index ? '1px solid #edf1f5' : 'none', padding: '7px 0', fontSize: 12 }}><span>{new Date(event.at).toLocaleTimeString()}</span><strong>{event.stage}</strong><span>{event.message}</span></div>)}</section>}

      {workflowMode && <section style={{ ...panelStyle, marginTop: 14 }}><div className="qif-section-heading"><div><div className="depo-panel__title">Recent QIF tasks</div><div className="depo-panel__meta">Select any run to inspect its validation, artifacts, and graph outcome.</div></div><button type="button" className="qif-refresh-button" disabled={actionBusy} onClick={refreshWorkspace}><RefreshCw size={14} /> Refresh</button></div>{history.length > 0 ? <div className="qif-history-list">{history.map((item) => <button type="button" key={item.task_id} aria-pressed={task?.task_id === item.task_id} aria-label={`Open QIF task ${item.ontology_name}, ${statusLabel(item.status)}`} onClick={() => openTask(item.task_id)}><span>{new Date(item.created_at).toLocaleString()}</span><span>{item.ontology_name}</span><strong>{statusLabel(item.status)}</strong></button>)}</div> : <p className="depo-panel__meta qif-empty-state">No QIF tasks yet. Start from the bundled reference or upload a complete related schema set.</p>}</section>}

      {workflowMode && <section style={{ ...panelStyle, marginTop: 14 }}><div className="depo-panel__title">Workflow service</div><p className="depo-panel__meta">The QIF workflow service uses a declarative processing agent and durable task artifacts. It can also run independently at the QIF service entry point.</p>{agents.map((agent) => <div key={agent.name} style={{ marginTop: 8, fontSize: 12, color: '#334e68' }}><CheckCircle2 size={14} /> {agent.name} — {agent.description}</div>)}</section>}
      {error && <div role="alert" className="qif-message qif-message--error qif-page-alert">{error}<button type="button" onClick={() => setError('')} aria-label="Dismiss QIF error">Dismiss</button></div>}
    </div>
  );
}

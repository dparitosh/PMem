import AutomationEvidence from '../Components/AutomationEvidence';
import useRouteView from '../app/useRouteView';
import EventReviewPanel from '../Components/EventReviewPanel';
import SemanticAnalysisResult from '../Components/SemanticAnalysisResult';
import SemanticSupport from "../Components/SemanticSupport";
import { getCredentialProfile, publicationRecoveryScope } from '../services/serviceAuth';
import { createSubmissionId } from '../utils/submissionId';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { dataPipelineAPI } from '../services/apiClient';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { readRequestedRunId, requireRunManifest } from '../workflows/runTracking';
import './DataFlowPage.css';
import DataWorkspace, {DataJourney} from '../Components/DataWorkspace';
import { productDraftFromRun } from '../services/analyticsProductDraft';
import ActionReviewDialog from '../Components/ActionReviewDialog';

const runName = run => (run?.source_name || run?.job_name || ({'validate-semantic-batch':'Engineering data validation','rdf-semantic-materialize':'Reporting data preparation'}[run?.job_type]) || run?.job_id || 'Processing run').replace(/\.[a-z0-9]{2,6}$/i,'').replaceAll('_',' ');
const REFRESH_INTERVAL_MS = 15000;
const WORKSPACE_VIEWS = ['runs','pipelines','events'];
const WORKSPACE_ALIASES = {definitions:'pipelines',quality:'runs',settings:'runs',agent:'runs'};

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
  return readRequestedRunId(window.location.hash);
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
  const count = value ? counts[value] : null;
  return typeof count === 'number' && Number.isSafeInteger(count) && count >= 0 ? count : null;
}

function qualityStatus(run) {
  if (run?.status === 'failed') return 'failed';
  if (countFor(run, 'rejected_records') > 0) return 'warning';
  return run?.status || 'completed';
}

function sourceStandard(run) {
  return run?.source_standard || run?.output_manifest?.source_standard || 'Not recorded';
}

function isPublishableRun(run) {
  return run?.status === 'completed'
    && ['normalize-ceim', 'validate-semantic-batch', 'normalize-unstructured-ceim','connector-ceim-normalize'].includes(run?.job_type)
    && run?.output_manifest?.checkpoint_state !== 'advanced'
    && run?.output_manifest?.publication?.status !== 'published';
}

function Status({ value }) {
  const normalized = String(value || 'unknown').toLowerCase();
  return <span className={`data-flow-status data-flow-status--${normalized}`}>{value || 'unknown'}</span>;
}

export default function DataFlowPage({ onCompanionRecordChange }) {
  const [workspace,setWorkspace]=useRouteView(WORKSPACE_VIEWS,'runs',WORKSPACE_ALIASES);
  const [health, setHealth] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [runs, setRuns] = useState([]);
  const [definitions, setDefinitions] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [eventSelection,setEventSelection]=useState(null);
  const [runPage,setRunPage] = useState(0);
  const [replayTarget,setReplayTarget] = useState(null);
  const [focusedDefinition,setFocusedDefinition] = useState(null);
  useEffect(()=>{
    const sync=()=>{const params=new URLSearchParams(window.location.hash.split('?')[1]||'');const id=params.get('definition_id'),version=params.get('definition_version');setFocusedDefinition(id&&version?{job_id:id,version}:null);};
    sync();window.addEventListener('hashchange',sync);return()=>window.removeEventListener('hashchange',sync);
  },[]);
  useEffect(() => {
    onCompanionRecordChange?.(workspace==='events'?{page:'data-flow',reconciliation_id:eventSelection||''}:{ page: 'data-flow', run_id: selectedRun?.run_id || '' });
    return () => onCompanionRecordChange?.(null);
  }, [onCompanionRecordChange, selectedRun?.run_id,workspace,eventSelection]);
  const [runStatus,setRunStatus]=useState('all');
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [replayError, setReplayError] = useState('');
  const [replayReceipt, setReplayReceipt] = useState(null);
  const [replayAccessRejected,setReplayAccessRejected]=useState(false);
  const replayRejected=useRef(false);
  const [replayingId, setReplayingId] = useState('');
  const sessionGeneration = useRef(0);
  const operationLock = useRef(false);
  const pendingReplays = useRef(new Map());
  // Runs whose replay was submitted but has no confirmed outcome. Their original
  // submission key may be retried even if the definition was disabled meanwhile.
  const uncertainReplays = useRef(new Set());
  const replayIntent = runId => {
    const key = `depo.pipeline.replay:${publicationRecoveryScope()}:${runId}`;
    let id = pendingReplays.current.get(key);
    try { id = id || sessionStorage.getItem(key); } catch { /* Memory remains available. */ }
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(String(id||''))) id = createSubmissionId();
    pendingReplays.current.set(key,id);
    try { sessionStorage.setItem(key,id); } catch { /* Retain in memory. */ }
    return {key,id};
  };
  const preferredRunId = useRef('');
  const loadSequence = useRef(0);
  const loadInFlight = useRef(false);
  const loadController = useRef(null);
  const routeRunId = useRef(requestedRunId());

  const load = useCallback(async ({ initial = false } = {}) => {
    if (loadInFlight.current) return;
    loadInFlight.current = true;
    const sequence = ++loadSequence.current;
    const controller = new AbortController();
    loadController.current = controller;
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError('');
    try {
      // Apply each independent read as soon as it completes. A slow telemetry
      // endpoint must not hide usable runs, definitions, or health evidence.
      let fulfilled = 0;
      let nextRuns = runs;
      let runsFulfilled = false;
      const read = (kind, request) => request.then(value => {
        if (sequence !== loadSequence.current) return;
        fulfilled += 1;
        const payload = responsePayload(value);
        if (kind === 'health') setHealth(payload);
        if (kind === 'telemetry') setTelemetry(payload);
        if (kind === 'runs') { runsFulfilled = true; nextRuns = asArray(payload?.runs); setRuns(nextRuns); }
        if (kind === 'definitions') setDefinitions(asArray(payload?.definitions));
      }).catch(failure => {
        if (sequence === loadSequence.current && kind === 'health') setHealth(null);
        throw failure;
      });
      const requests = [
        read('health', dataPipelineAPI.health({signal:controller.signal})),
        read('telemetry', dataPipelineAPI.telemetry({signal:controller.signal})),
        read('runs', dataPipelineAPI.runs(100,{signal:controller.signal})),
        read('definitions', dataPipelineAPI.definitions({signal:controller.signal})),
      ];
      const results = await Promise.allSettled(requests);
      if (sequence !== loadSequence.current) return;
      if (!fulfilled) throw results.find(result => result.status === 'rejected')?.reason || new Error('Data pipeline service is unavailable.');
      const requestedId = preferredRunId.current || requestedRunId();
      if (requestedId) {
        let requested = nextRuns.find(run => run.run_id === requestedId);
        if (!requested) {
          try {
            requested = responsePayload(await dataPipelineAPI.getRun(requestedId,{signal:controller.signal}));
            if (requested?.run_id !== requestedId) throw new Error('Requested run identity mismatch');
          } catch (failure) {
            if (sequence !== loadSequence.current) return;
            setSelectedRun(null);
            setError('Requested run is missing or inaccessible. No other run has been selected.');
            return;
          }
        }
        if (sequence !== loadSequence.current) return;
        setSelectedRun(requested);
      } else if (runsFulfilled) setSelectedRun(current => nextRuns.find(run => run.run_id === current?.run_id) || nextRuns[0] || null);
      if (results.some((result) => result.status === 'rejected')) setError('Some processing-job evidence is temporarily unavailable. Showing the available data.');
    } catch (loadError) {
      if (sequence !== loadSequence.current) return;
      setError(apiErrorMessage(loadError, 'Unable to load data-job telemetry.'));
    } finally {
      if (sequence === loadSequence.current) {
        if(loadController.current===controller)loadController.current=null;
        loadInFlight.current = false;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    load({ initial: true });
    const interval = window.setInterval(() => { if (!document.hidden) load(); }, REFRESH_INTERVAL_MS);
    const credentialsChanged = () => {
      loadController.current?.abort();
      sessionGeneration.current += 1;
      loadSequence.current += 1; loadInFlight.current = false;
      setHealth(null); setTelemetry(null); setRuns([]); setDefinitions([]); setSelectedRun(null);
      setReplayError(''); setReplayReceipt(null);
      replayRejected.current=false;setReplayAccessRejected(false);
      setReplayTarget(null); preferredRunId.current='';
      load({ initial: true });
    };
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
    events.forEach(event=>window.addEventListener(event,credentialsChanged));
    const verified=()=>{
      replayRejected.current=false;setReplayAccessRejected(false);
      // A successful reconnect supersedes reads started before verification.
      loadController.current?.abort();
      loadSequence.current+=1; loadInFlight.current=false;
      load({initial:true});
    };
    window.addEventListener('depo:access-verified',verified);
    const routeChanged=()=>{
      if(!window.location.hash.startsWith('#/data-flow'))return;
      const nextId=requestedRunId();
      if(routeRunId.current===nextId)return;
      routeRunId.current=nextId;loadController.current?.abort();
      preferredRunId.current='';loadSequence.current+=1;loadInFlight.current=false;
      setSelectedRun(null);setReplayError('');
      load({initial:true});
    };
    window.addEventListener('hashchange',routeChanged);
    window.addEventListener('popstate',routeChanged);
    return () => {
      window.clearInterval(interval);
      events.forEach(event=>window.removeEventListener(event,credentialsChanged));
      window.removeEventListener('depo:access-verified',verified);
      window.removeEventListener('hashchange',routeChanged);
      window.removeEventListener('popstate',routeChanged);
      loadController.current?.abort();
      sessionGeneration.current += 1;
      loadSequence.current += 1;
      loadInFlight.current = false;
    };
  }, [load]);

  const visibleRuns = useMemo(() => {
    const term = filter.trim().toLowerCase();
    const matchingStatus=runs.filter(run=>runStatus==='all'||run.status===runStatus);
    if (!term) return matchingStatus;
    return matchingStatus.filter((run) => [run.run_id, run.run_number, run.source_name, run.job_id, run.job_name, run.job_type, run.status, run.correlation_id, run.source_system, sourceStandard(run)]
      .some((value) => String(value || '').toLowerCase().includes(term)));
  }, [filter, runs, runStatus]);
  useEffect(()=>setRunPage(0),[filter,runStatus]);
  const currentRunPage=Math.min(runPage,Math.max(0,Math.ceil(visibleRuns.length/25)-1));
  const pageRuns=visibleRuns.slice(currentRunPage*25,(currentRunPage+1)*25);

  const totals = telemetry?.durable_job_telemetry || telemetry?.totals || {};
  const durableTotals = useMemo(() => ({
    runs: runs.length,
    acceptedKnown: runs.some(run => countFor(run, 'accepted_records') !== null),
    rejectedKnown: runs.some(run => countFor(run, 'rejected_records') !== null),
    accepted: runs.reduce((sum, run) => sum + (countFor(run, 'accepted_records') ?? 0), 0),
    rejected: runs.reduce((sum, run) => sum + (countFor(run, 'rejected_records') ?? 0), 0),
  }), [runs]);
  const qualityJobCount = useMemo(
    () => definitions.filter((definition) => /quality|validate/.test(String(definition.job_type || ''))).length,
    [definitions],
  );

  const selectRun = run => {
    // A newer selection supersedes any in-flight load that may still resolve an earlier run.
    loadController.current?.abort(); loadSequence.current += 1; loadInFlight.current = false;
    preferredRunId.current=run.run_id;routeRunId.current=run.run_id;setSelectedRun(run);
    const [path, search='']=window.location.hash.split('?');
    const params=new URLSearchParams(search);params.set('run_id',run.run_id);
    // Keep only the route itself: a run segment in the path would override run_id.
    const route=(path||'').split('/').slice(0,2).join('/')||'#/data-flow';
    const hash=`${route}?${params}`;
    if(window.location.hash!==hash){window.history.pushState(null,'',hash);window.dispatchEvent(new HashChangeEvent('hashchange'));}
  };

  const executionAuthorization = async (generation) => {
    if(replayRejected.current)throw new Error('Replay access was rejected. Reconnect execution access in Admin and revalidate before retrying.');
    const token=getCredentialProfile('DATA_JOB_EXECUTION_TOKEN').trim();
    const response=await dataPipelineAPI.executionIdentity(token);
    if(generation!==sessionGeneration.current)throw new Error('Connection changed before replay. No replay was submitted.');
    const actor=responsePayload(response)?.actor;
    if(typeof actor!=='string'||!actor.trim()||actor.length>256)throw new Error('Execution identity could not be verified. No replay was submitted.');
    return {approved_by:actor,...(token?{approval_token:token}:{})};
  };
  const replayFailureMessage = failure => {
    if([401,403].includes(failure?.response?.status)){
      replayRejected.current=true;setReplayAccessRejected(true);
      return 'Replay access was rejected. Reconnect data-job execution access in Admin, then revalidate access. Read access alone cannot execute jobs. No automatic retry was made. '+apiErrorMessage(failure,'');
    }
    return apiErrorMessage(failure,'Replay was not confirmed. Retry uses the same submission reference; check retained status before starting other work.');
  };

  const blockReasonFor = (run, list) => {
    const definition = list.find(item => item.job_id === run.job_id && String(item.version) === String(run.job_version));
    if (!definition) {
      // Another version of this job does not authorize this run's version. A job that is absent may be on another page; the server rechecks at submit time.
      return list.some(item => item.job_id === run.job_id) ? 'This exact version is not registered. An approved version of another revision does not authorize this replay.' : '';
    }
    if (definition.lifecycle_state !== 'approved' || definition.enabled !== true) {
      return `This definition version is ${definition.lifecycle_state || 'not approved'}${definition.enabled === false ? ' and disabled' : ''}. Only an approved and enabled version can be replayed.`;
    }
    return '';
  };
  const replayBlockReason = (run) => (uncertainReplays.current.has(run.run_id) ? '' : blockReasonFor(run, definitions));

  // Confirmation path: verifies the execution identity, rechecks the definition
  // on the server, then submits with the verified execution identity. Failures
  // are rethrown so the review dialog can show them.
  const replay = async (run) => {
    if(operationLock.current||replayRejected.current||['queued','running'].includes(run.status)) throw new Error('This run cannot be replayed right now.');
    operationLock.current=true;
    const generation=sessionGeneration.current;
    setReplayingId(run.run_id);
    setReplayError(''); setReplayReceipt(null);
    try {
      const authorization = await executionAuthorization(generation);
      const current = asArray(responsePayload(await dataPipelineAPI.definitions({}))?.definitions);
      const blocked = uncertainReplays.current.has(run.run_id) ? '' : blockReasonFor(run, current);
      if (blocked) { const error = new Error(blocked); error.actionBlocked = true; throw error; }
      if (generation !== sessionGeneration.current) throw new Error('Connection changed. No replay was submitted.');
      const intent=replayIntent(run.run_id);
      uncertainReplays.current.add(run.run_id);
      const response = await dataPipelineAPI.replay(run.run_id, {idempotency_key:intent.id,...authorization});
      const replayed = requireRunManifest(responsePayload(response));
      uncertainReplays.current.delete(run.run_id);
      pendingReplays.current.delete(intent.key);
      try { sessionStorage.removeItem(intent.key); } catch { /* Optional storage. */ }
      if(generation!==sessionGeneration.current) return replayed;
      selectRun(replayed);
      setReplayReceipt(replayed);
      setRunStatus('all'); setFilter(''); setRunPage(0);
      setSelectedRun(replayed);
      setWorkspace('runs');
      // A successful mutation supersedes any in-flight poll so the list reflects it.
      loadController.current?.abort(); loadSequence.current += 1; loadInFlight.current = false;
      await load();
      return replayed;
    } catch (replayFailure) {
      if(generation===sessionGeneration.current)setReplayError(replayFailureMessage(replayFailure));
      throw replayFailure;
    } finally {
      operationLock.current=false; setReplayingId('');
    }
  };

  return (
    <section className="data-flow-page data-cockpit" aria-labelledby="data-flow-title">

      <header className="data-flow-page__header">
        <div>

          <h1 id="data-flow-title">Data Flow</h1>
          <p>Auto-refresh · 15 seconds</p>
        </div>
        <div className="data-flow-page__actions">
          <span>Pipeline API <Status value={health ? 'responding' : 'checking'} /></span>
          <span>Spark engine <Status value={health?.spark?.status || health?.status || 'checking'} /></span>
          <button className="data-flow-button" type="button" onClick={() => load()} disabled={refreshing}>
            <ix-icon name="refresh" aria-hidden="true" /> {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>
      <DataJourney current="flow"/>

      {error && <div className="data-flow-notice" role="status">{error}</div>}
      {replayError && <div className="data-flow-notice data-flow-notice--error" role="alert">{replayError}</div>}
      {replayTarget && <ActionReviewDialog
        action={{label:'Replay retained run',name:runName(replayTarget),description:"Starts a new run from this run's retained inputs. The original run and its evidence are not changed.",items:[['Source',runName(replayTarget)],['Started',displayTime(replayTarget.started_at)],['Version',replayTarget.job_version],['Source system',replayTarget.source_system],['Source standard',replayTarget.source_standard],['Records',replayTarget.input_manifest?.record_count],['Payload digest',replayTarget.input_manifest?.payload_digest]]}}
        onClose={()=>setReplayTarget(null)}
        blockedReason={replayBlockReason(replayTarget)}
        resolveLabel="Review job definition"
        onResolve={()=>{const target=replayTarget;setReplayTarget(null);window.location.hash=`#/change-control?source=definitions&view=workflows&record_source=definitions&record=${encodeURIComponent(target.job_id+':'+target.job_version)}`;}}
        onConfirm={async()=>{const replayed=await replay(replayTarget);return {label:'Replay accepted',message:`${runName(replayed)} — a new validation run was created from the retained source. Open the run to follow its progress. Publication requires separate approval.`,runId:replayed.run_id,href:`#/data-flow/${encodeURIComponent(replayed.run_id)}`};}}
      />}
      {replayReceipt && <div className="data-flow-notice" role="status" aria-label="Last action result">{runName(replayReceipt)} — rerun {selectedRun?.run_id===replayReceipt.run_id ? selectedRun.status : replayReceipt.status}. See the selected workflow below. Publication requires separate approval.</div>}

      <div className="data-flow-kpis" aria-label="Data-job telemetry summary">
        <article><span>Configured jobs</span><strong>{loading||error?'—':definitions.length}</strong></article>
        <article><span>Quality jobs</span><strong>{loading||error?'—':qualityJobCount}</strong></article>
        <article><span>Durable runs</span><strong>{loading||error?'—':totals.runs ?? durableTotals.runs}</strong></article>
        <article><span>Accepted records</span><strong>{loading||error||!durableTotals.acceptedKnown?'—':totals.records_accepted ?? durableTotals.accepted}</strong></article>
        <article><span>Rejected records</span><strong>{loading||error||!durableTotals.rejectedKnown?'—':totals.records_rejected ?? durableTotals.rejected}</strong></article>
        <article><span>Scheduler</span><strong className="data-flow-kpi-state">{!telemetry||error?'Unknown':telemetry?.scheduler?.running ? 'Running' : telemetry?.scheduler?.enabled ? 'Stopped' : 'Disabled'}</strong></article>
        <article><span>Pipeline workers</span><strong className="data-flow-kpi-state">{!telemetry||error?'Unknown':`${telemetry.worker_count ?? health?.worker_count ?? '—'} / ${telemetry.busy_workers ?? health?.busy_workers ?? '—'} busy`}</strong></article>
      </div>

      <p>Run and record totals cover the latest {totals.limit ?? 100} runs, not lifetime history.</p>
      <DataWorkspace label="Data Flow workspace" active={workspace} onChange={setWorkspace} tabs={[{id:'runs',label:'Run monitor'},{id:'pipelines',label:'Pipeline jobs'},{id:'events',label:'Event reviews'}]}>
        {{runs:<><div className="data-cockpit__guidance"><div><strong>Inspect a run, resolve issues, then reuse its evidence</strong><p>Select a run to review its results.</p></div><a href="#/change-control">Open Change Control</a><a href="#/data-quality">View data quality</a></div>
      <div className="data-flow-grid">
        <article className="data-flow-card data-flow-card--runs">
          <div className="data-flow-card__heading">
            <div><h2>Processing-job runs</h2></div>
            <div className="data-flow-run-tools"><label className="data-flow-filter">Find a run<input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Job, source, type, status…" /></label><label>Run status<select value={runStatus} onChange={event=>setRunStatus(event.target.value)}><option value="all">All statuses</option>{['queued','running','completed','failed'].map(value=><option key={value} value={value}>{value}</option>)}</select></label></div>
          </div>
          {loading && !runs.length ? <div className="data-flow-empty"><ix-spinner size="medium" /> Loading job evidence…</div> : (
            <div className="data-flow-table-wrap">
              <table className="data-flow-table">
                <thead><tr><th>Job</th><th>Source</th><th>Started</th><th>Quality</th><th>Status</th><th>CR / CO</th><th aria-label="Actions" /></tr></thead>
                <tbody>
                  {pageRuns.map((run) => <tr key={run.run_id} className={selectedRun?.run_id === run.run_id ? 'is-selected' : ''}>
                    <td><button className="data-flow-link" type="button" onClick={() => selectRun(run)}>{runName(run)}</button><small>{run.run_number ? run.run_number + ' · ' : ''}{run.job_name || 'Engineering data workflow'} · {run.job_version || '—'}</small></td>
                    <td><span className="data-flow-source">{sourceStandard(run)}</span></td>
                    <td>{displayTime(run.started_at)}</td>
                    <td>{['rest-source-ingest','registered-source-ingest','oslc-snapshot-ingest'].includes(run.job_type)?`${run.output_manifest?.counts?.records??'—'} acquired · validation not assessed`:<>{countFor(run, 'accepted_records') === null && countFor(run, 'rejected_records') === null ? 'Validation not assessed' : <>{countFor(run, 'accepted_records') ?? '—'} accepted · {countFor(run, 'rejected_records') ?? '—'} rejected</>}</>}</td>
                    <td><Status value={qualityStatus(run)} />{run.output_manifest?.publication?.status==='published' && <span className="data-flow-status">Published · receipt retained</span>}</td>
                    <td>{run.change_request?.request_number || 'Not linked'}<small>{run.change_request?.order?.order_number || 'CO not issued'}</small></td>
                    <td><button className="data-flow-replay" type="button" onClick={() => setReplayTarget(run)} disabled={!!replayingId || replayAccessRejected || ['queued','running'].includes(run.status)}>{replayingId === run.run_id ? 'Replaying…' : 'Replay'}</button>{' '}{(run.change_request||isPublishableRun(run))&&<a href={`#/change-control?source=pipeline&view=${run.change_request?'requests':'workflows'}&record_source=pipeline&record=${encodeURIComponent(run.run_id)}`}>{run.change_request?'Open change request':'Request change in Change Control'}</a>}</td>
                  </tr>)}
                  {!visibleRuns.length && <tr><td colSpan="7" className="data-flow-empty">{error?'Run history could not be verified. Restore service access and refresh; retained runs may still exist.':runs.length?'No durable job runs match the current filter.':'No runs yet. Import source inputs, then run an approved pipeline job.'}</td></tr>}
                </tbody>
              </table>
              <nav aria-label="Processing run pages"><button disabled={!currentRunPage} onClick={()=>setRunPage(currentRunPage-1)}>Previous runs</button><span> {visibleRuns.length?currentRunPage*25+1:0}–{Math.min((currentRunPage+1)*25,visibleRuns.length)} of {visibleRuns.length} loaded runs </span><button disabled={(currentRunPage+1)*25>=visibleRuns.length} onClick={()=>setRunPage(currentRunPage+1)}>Next runs</button></nav>
            </div>
          )}
        </article>

        <aside className="data-flow-card data-flow-card--evidence" aria-live="polite">
          <h2>Run evidence</h2>
          {selectedRun ? <>
            <dl className="data-flow-evidence">
              {selectedRun.run_number && <><dt>Run number</dt><dd>{selectedRun.run_number}</dd></>}<dt>Source</dt><dd>{runName(selectedRun)}</dd><dt>Started</dt><dd>{displayTime(selectedRun.started_at)}</dd>
              <dt>Change request</dt><dd>{selectedRun.change_request?.request_number || 'Not linked'}</dd><dt>Change order</dt><dd>{selectedRun.change_request?.order?.order_number || 'Not issued'}</dd>
              <dt>Source standard</dt><dd>{sourceStandard(selectedRun)}</dd>
              <dt>Source system</dt><dd>{selectedRun.source_system || selectedRun.output_manifest?.source_system || 'Not recorded'}</dd>
              {selectedRun.input_manifest?.file_references?.length>0&&<><dt>Source file</dt><dd>{selectedRun.input_manifest.file_references.map(file=>file.file_number||file.filename).join(', ')}</dd></>}<dt>Input manifest</dt><dd>{selectedRun.input_manifest?.record_count ?? 0} record(s), {selectedRun.input_manifest?.artifact_ids?.length ?? 0} retained artifact(s)</dd>
              <dt>Quality profile</dt><dd>{selectedRun.quality_profile || selectedRun.job_type || '—'} / {countFor(selectedRun,'accepted_records') === null && countFor(selectedRun,'rejected_records') === null ? 'not assessed' : qualityStatus(selectedRun)}</dd>


              <dt>Executed by</dt><dd>{selectedRun.executed_by || 'Legacy run / identity not recorded'}</dd>

              <dt>Attempt</dt><dd>{selectedRun.attempt || 1}</dd>
              <dt>Lease heartbeat</dt><dd>{displayTime(selectedRun.lease?.heartbeat_at)}</dd>
              <dt>Run type</dt><dd>{selectedRun.replay_of ? 'Rerun of retained source' : 'Original execution'}</dd>
              {selectedRun.failure?.message || selectedRun.last_error ? <><dt>Failure</dt><dd>{selectedRun.failure?.message || selectedRun.last_error}</dd></> : null}
              <dt>Graph publication</dt><dd>{selectedRun.output_manifest?.publication?.status==='published' ? `Published — receipt retained` : 'Not published'}</dd>
              <dt>Output evidence</dt><dd>{selectedRun.output_manifest?.contract || 'Pending output manifest'}</dd>

              <dt>Validation</dt><dd>{selectedRun.output_manifest?.validation_status || 'Not applicable or pending'}</dd>
              <dt>Quality checks</dt><dd>{(() => { const quality = selectedRun.output_manifest?.quality_report || selectedRun.output_manifest?.quality || selectedRun.quality || {}; const failed = quality.failed_rules ?? quality.rules_failed ?? quality.rejected_records; const score = quality.score ?? quality.quality_score ?? quality.completeness; return score !== undefined || failed !== undefined ? `${score !== undefined ? `score ${score}` : 'score not recorded'} · ${failed ?? 0} failed rule(s)` : 'No rule-level quality report recorded'; })()}</dd>
              {selectedRun.output_manifest?.data_product_draft && <>
                <dt>Data product draft</dt><dd>{selectedRun.output_manifest.data_product_draft.contract || 'Draft available'} · {selectedRun.output_manifest.data_product_draft.artifacts?.length || 0} retained artifacts</dd>
                <dt>Product approval</dt><dd>{selectedRun.output_manifest.data_product_draft.publication_requirements?.join('; ') || 'Awaiting data-product approval'}</dd>
              </>}
            </dl>
            <details><summary>Technical run references</summary><AutomationEvidence run={selectedRun}/><dl><dt>Run ID</dt><dd>{selectedRun.run_id}</dd>{selectedRun.input_manifest?.file_references?.map(file=><React.Fragment key={file.file_id}><dt>Source file UUID</dt><dd>{file.file_id}</dd><dt>Source content SHA-256</dt><dd>{file.content_sha256||'Not recorded'}</dd></React.Fragment>)}<dt>Correlation ID</dt><dd>{selectedRun.correlation_id||'Not recorded'}</dd><dt>Worker</dt><dd>{selectedRun.worker_id||'Not recorded'}</dd><dt>Mapping digest</dt><dd>{selectedRun.output_manifest?.mapping_digest||'Not recorded'}</dd>{selectedRun.replay_of&&<><dt>Original run ID</dt><dd>{selectedRun.replay_of}</dd></>}</dl></details>
            <SemanticSupport report={selectedRun.semantic_support}/>
            <p className="data-flow-help">{selectedRun.job_type==='trs-reporting-sync'?'Replay resumes the approved reporting selection and consumes newer tracked changes. Previously frozen product snapshots remain unchanged.':['rest-source-ingest','registered-source-ingest'].includes(selectedRun.job_type)?'Replay reacquires the current configured source. Earlier retained artifacts stay unchanged; source data may have changed.':'Replay reuses the retained immutable input; publication still remains subject to the canonical approval boundary.'}</p>
            {(() => { try { productDraftFromRun(selectedRun); return <a href={`#/data-products?run_id=${encodeURIComponent(selectedRun.run_id)}`}>Create product from retained run evidence</a>; } catch { return <p>A completed run with retained output artifacts is required to create a product draft.</p>; } })()}
          </> : <div className="data-flow-empty">Select a run to inspect its input, quality, lineage, checkpoint, and output evidence.</div>}
        </aside>
      </div>
      {selectedRun&&<a href={`#/admin?view=agents&source=data-flow&run_id=${encodeURIComponent(selectedRun.run_id)}`}>Open Agent Control</a>}
      <SemanticAnalysisResult run={selectedRun}/>
        </>,pipelines:<>{focusedDefinition&&<p role="status">Selected workflow: {definitions.find(item=>item.job_id===focusedDefinition.job_id&&item.version===focusedDefinition.version)?.name||focusedDefinition.job_id} · Version: {focusedDefinition.version}</p>}<div className="data-cockpit__guidance"><div><strong>Manage versioned pipeline jobs</strong><p>Run approved jobs. Review workflow changes in Change Control.</p></div><a href="#/import">Import source data</a></div>
      <article className="data-flow-card data-flow-card--definitions">
        <div className="data-flow-card__heading">
          <div><h2>Data-job definitions</h2></div>
        </div>
        <div className="data-flow-table-wrap"><table className="data-flow-table data-flow-definition-table">
          <thead><tr><th>Definition</th><th>Contract</th><th>State</th><th>Schedule</th><th aria-label="Actions" /></tr></thead>
          <tbody>{definitions.map((definition) => {

            const isApproved = definition.lifecycle_state === 'approved' && definition.enabled;
            const hasRetainedInput=runs.some(run=>run.job_id===definition.job_id&&run.job_version===definition.version);
            return <tr key={`${definition.job_id}:${definition.version}`} aria-current={focusedDefinition?.job_id===definition.job_id&&focusedDefinition?.version===definition.version ? 'true' : undefined}>
              <td><strong>{definition.name || definition.job_id}</strong><small>{definition.workflow_number || definition.job_id} · {definition.version} · {definition.owner || 'No owner recorded'}</small></td>
              <td>{definition.input_contract || '—'}<small>{definition.output_contract || '—'}</small></td>
              <td><Status value={definition.lifecycle_state || (definition.enabled ? 'enabled' : 'disabled')} /></td>
              <td>{definition.schedule ? `Every ${definition.schedule.interval_seconds}s` : 'Not scheduled'}</td>
              <td><button type="button" disabled={!isApproved||!hasRetainedInput||!!replayingId} onClick={()=>setReplayTarget(runs.find(run=>run.job_id===definition.job_id&&run.job_version===definition.version))}>Run now</button>{' '}<a href={`#/change-control?source=definitions&view=workflows&record_source=definitions&record=${encodeURIComponent(definition.job_id+':'+definition.version)}`}>Review workflow change</a>{isApproved&&!hasRetainedInput&&<small>No retained inputs. <a href="#/import">Import source data first</a>.</small>}</td>
            </tr>;
          })}{!definitions.length && <tr><td colSpan="5" className="data-flow-empty">No versioned data-job definitions are registered.</td></tr>}</tbody>
        </table></div>
      </article>
        </>,events:<EventReviewPanel onSelect={setEventSelection}/>}}
      </DataWorkspace>
    </section>
  );
}

import React, { useEffect, useRef, useState } from 'react';
import { dataPipelineAPI as api } from '../services/apiClient';
import { getCredentialProfile } from '../services/serviceAuth';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { createSubmissionId } from '../utils/submissionId';

const empty = { source_id:'', name:'', endpoint:'', credential_ref:'', auth_header:'Authorization', records_path:'', target_model:'' };
const events = ['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
const pendingKey = 'depo:rest-source-submission:v1';
function readPending() {
  try { const value=JSON.parse(localStorage.getItem(pendingKey)); return value && ['key','source','jobId','version'].every(key => typeof value[key]==='string') ? value : null; } catch { return null; }
}
export default function RestSourcesPanel() {
  const [form,setForm] = useState(empty), [sources,setSources] = useState([]), [jobs,setJobs] = useState([]);
  const [source,setSource] = useState(''), [job,setJob] = useState(''), [preview,setPreview] = useState(null);
  const [message,setMessage] = useState(''), [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const [pending,setPending] = useState(readPending);
  const [page,setPage] = useState({offset:0,total:0,next:null});
  const [loadingSources,setLoadingSources] = useState(false), [loadingJobs,setLoadingJobs] = useState(false);
  const loadSequence=useRef(0);
  const generation = useRef(0), lock = useRef(false);
  useEffect(() => {
    const reset = () => { generation.current++; loadSequence.current++; lock.current=false; setBusy(false); setLoadingSources(false);setLoadingJobs(false);setSources([]); setJobs([]); setSource(''); setJob(''); setPreview(null); setMessage(''); setError('Access changed. Refresh sources. Retained runs remain in Data Flow.'); };
    const storage = event => { if(event.key===pendingKey) setPending(readPending()); };
    events.forEach(event => window.addEventListener(event,reset)); window.addEventListener('storage',storage);
    return () => { generation.current++; events.forEach(event => window.removeEventListener(event,reset)); window.removeEventListener('storage',storage); };
  },[]);
  async function act(operation) {
    if(lock.current) return;
    lock.current=true; setBusy(true); setError(''); setMessage('');
    const current=generation.current, apply=fn => { if(current===generation.current) fn(); };
    try { await operation(apply); } catch(failure) { apply(() => setError(apiErrorMessage(failure,'Operation failed. Check Data Flow before retrying a submitted run.'))); }
    finally { if(current===generation.current) { lock.current=false; setBusy(false); } }
  }
  function token(profile) {
    const value=getCredentialProfile(profile);
    if(!value) throw new Error('Connect the required management or execution scope in Admin API access.');
    return value;
  }
  const chosen=jobs.find(item => `${item.job_id}@${item.version}`===job);
  const sourceExists=sources.some(item => item.source_id===source);
  function load(offset=0) {
    const current=generation.current, sequence=++loadSequence.current;
    const apply=fn => { if(current===generation.current && sequence===loadSequence.current) fn(); };
    setLoadingSources(true);setLoadingJobs(true);setError('');
    return (async () => {
      const errors=[];
      await Promise.all([
        api.restSources({params:{limit:50,offset}}).then(result => apply(() => {
          const rows=result.data.sources;
          setSources(rows);setPage({offset,total:result.data.total ?? rows.length,next:result.data.next_offset ?? null});
          setSource(old => rows.some(item => item.source_id===old) ? old : '');setPreview(null);
        })).catch(failure => {errors.push(apiErrorMessage(failure,'Source catalog unavailable'));apply(() => {setSources([]);setSource('');setPreview(null);});}).finally(() => apply(() => setLoadingSources(false))),
        api.definitions().then(result => apply(() => {
          const rows=result.data.definitions.filter(item => item.job_type==='rest-source-ingest' && item.lifecycle_state==='approved' && item.enabled);
          setJobs(rows);setJob(old => rows.some(item => `${item.job_id}@${item.version}`===old) ? old : '');
        })).catch(failure => {errors.push(apiErrorMessage(failure,'Job catalog unavailable'));apply(() => {setJobs([]);setJob('');});}).finally(() => apply(() => setLoadingJobs(false))),
      ]);
      if(errors.length) apply(() => setError(errors.join('; ')));
    })();
  }
  function retain(value) { localStorage.setItem(pendingKey,JSON.stringify(value)); setPending(value); }
  function reconcile(value, initial=false) {
    return act(async apply => {
      let response;
      if(value.runId) response=await api.getRun(value.runId);
      else {
        let needsSubmit=initial;
        if(!initial) {
          try {response=await api.restSubmission(value.key,token('DATA_JOB_EXECUTION_TOKEN'));needsSubmit=response.data.status==='pending_enqueue';}
          catch(failure) {if(failure.response?.status===404) needsSubmit=true;else throw failure;}
        }
        if(needsSubmit) response=await api.runDefinition(value.jobId,value.version,{source_id:value.source,idempotency_key:value.key},{approval_token:token('DATA_JOB_EXECUTION_TOKEN'),approved_by:'source-reader'});
      }
      const run=response.data.run_manifest || response.data.run || response.data;
      apply(() => {retain({...value,runId:run.run_id,status:run.status});setMessage(`Run ${run.run_id}: ${run.status}. Inspect its retained output in Data Flow.`);});
    });
  }
  const fields=[['source_id','Source ID','parts-api'],['name','Source name','Released parts'],['endpoint','HTTP(S) endpoint','https://plm.example.com/api/parts'],['records_path','Records path (optional)','data.items'],['credential_ref','Server secret reference (optional)','DEPO_REST_SECRET_PLM'],['target_model','Target model reference (optional)','Business model reference']];
  return <section aria-label="REST data sources"><h2>REST data sources</h2>
    <p>Register a source, preview its records, then fetch with an approved worker job. Retained records still require semantic validation before publication.</p>
    <button disabled={busy||loadingSources||loadingJobs} onClick={() => load(page.offset)}>Refresh sources and jobs</button>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <details><summary>Register a REST source</summary><p>Register a new ID for revisions. The server must allow the endpoint host. Enter a secret reference, never the API secret.</p>
      <form onSubmit={event => {event.preventDefault();act(async apply => {
        const result=await api.registerRestSource(form,token('DATA_JOB_APPROVAL_TOKEN'));
        apply(() => {setSources(old => [...old,result.data]);setSource(result.data.source_id);setForm(empty);setPreview(null);setMessage('Source registered. Test its connection next.');});
      });}}><div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(250px,1fr))',gap:16,margin:'16px 0'}}>
        {fields.map(([key,label,placeholder]) => <label key={key}>{label}<input style={{display:'block',width:'100%',boxSizing:'border-box'}} required={['source_id','name','endpoint'].includes(key)} maxLength={500} value={form[key]} placeholder={placeholder} onChange={event => setForm({...form,[key]:event.target.value})}/></label>)}
      </div><label>Authentication header<select value={form.auth_header} onChange={event => setForm({...form,auth_header:event.target.value})}><option value="Authorization">Bearer token</option><option value="X-API-Key">X-API-Key</option><option value="api-key">api-key</option></select></label><p>HTTP sends credentials without transport encryption. Use it only on a trusted network; prefer HTTPS.</p><button disabled={busy} type="submit">Register source</button></form></details>
    <div style={{display:'flex',gap:16,flexWrap:'wrap',alignItems:'end',margin:'20px 0'}}>
      <label>Registered source<select disabled={busy||loadingSources} value={source} onChange={event => {setSource(event.target.value);setPreview(null);}}><option value="">Select a source</option>{sources.map(item => <option key={item.source_id} value={item.source_id}>{item.name}</option>)}</select></label>
      <button disabled={busy||loadingSources||!sourceExists} onClick={() => {setPreview(null);act(async apply => {const result=await api.previewRestSource(source,token('DATA_JOB_EXECUTION_TOKEN'));apply(() => setPreview(result.data));});}}>Test connection and preview</button>
      <label>Approved acquisition job<select disabled={busy||loadingJobs} value={job} onChange={event => setJob(event.target.value)}><option value="">Select an approved job</option>{jobs.map(item => <option key={`${item.job_id}@${item.version}`} value={`${item.job_id}@${item.version}`}>{item.name} · {item.version}</option>)}</select></label>
      <button disabled={busy||loadingSources||loadingJobs||!sourceExists||!chosen||!!pending} onClick={() => {
        try {
          const value=readPending() || {key:createSubmissionId(),source,jobId:chosen.job_id,version:chosen.version};
          retain(value);reconcile(value,true);
        } catch(failure) {setError('Unable to retain a safe submission reference. Enable local browser storage before submitting.');}
      }}>Fetch records with worker</button>
    </div>
    <div aria-label="Source pages"><span>{page.total} sources · page {Math.floor(page.offset/50)+1}</span> <button disabled={busy||page.offset===0} onClick={() => load(Math.max(0,page.offset-50))}>Previous sources</button> <button disabled={busy||page.next===null} onClick={() => load(page.next)}>Next sources</button></div>
    {pending && <div role="status"><p>Retained submission for {pending.source}: {pending.runId || pending.key} · {pending.status || 'outcome not confirmed'}. Reconnect does not submit a new fetch.</p><button disabled={busy} onClick={() => reconcile(pending)}>Refresh retained submission</button>{['completed','failed','quality_warning'].includes(pending.status) && <button disabled={busy} onClick={() => {localStorage.removeItem(pendingKey);setPending(null);}}>Prepare another fetch</button>} <a href="#/data-flow">Review runs in Data Flow</a></div>}
    {!jobs.length && <p>No approved acquisition job loaded. <button disabled={busy} onClick={() => act(async apply => {
      await api.createDefinition({job_id:'rest-source-acquisition',name:'REST source acquisition',version:'1.0.0',owner:'source-author',job_type:'rest-source-ingest',quality_profile:'semantic-core-v1'},token('DATA_JOB_APPROVAL_TOKEN'));
      apply(() => setMessage('Draft job created. Review and approve it in Data Flow, then refresh sources and jobs.'));
    })}>Create acquisition job draft</button> No approval is granted automatically.</p>}
    {preview && <div><h3>Connection succeeded · {preview.record_count} records</h3><p>Up to 10 records shown. Preview does not retain an ingestion.</p><div style={{overflow:'auto',maxHeight:320}}><table><thead><tr><th>Record</th><th>Property</th><th>Value</th></tr></thead><tbody>{preview.records.flatMap((record,index) => Object.entries(record).slice(0,30).map(([key,value]) => <tr key={`${index}:${key}`}><td>{index+1}</td><td>{key}</td><td>{(typeof value==='object'?JSON.stringify(value):String(value)).slice(0,500)}</td></tr>))}</tbody></table></div></div>}
    <p>One GET endpoint per fetch: HTTP or HTTPS on standard ports, allowed public hosts only, no redirects, maximum 2 MiB and 1,000 records. Both support server-referenced keys. Pagination and recurring refresh are not configured here. Target model is a reference, not an automatic mapping. <a href="#/data-flow">Open Data Flow</a> for job approval, runs and retained artifacts.</p>
  </section>;
}

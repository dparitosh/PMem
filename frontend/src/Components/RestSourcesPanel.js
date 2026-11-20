import React, { useEffect, useRef, useState } from 'react';
import { dataPipelineAPI as api } from '../services/apiClient';
import { getCredentialProfile } from '../services/serviceAuth';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { openApiSourceDrafts } from '../services/openApiPreview';
import { createSubmissionId } from '../utils/submissionId';
import { acquisitionRun, checkAcquisitionReference, retainAcquisition, clearAcquisition } from '../utils/acquisitionReceipt';

const empty = { source_id:'', name:'', endpoint:'', credential_ref:'', auth_header:'Authorization', records_path:'', target_model:'' };
const events = ['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
const pendingKey = 'depo:rest-source-submission:v1';
function readPending() {
  try { const value=JSON.parse(localStorage.getItem(pendingKey)); return value && ['key','source','jobId','version'].every(key => typeof value[key]==='string') ? value : null; } catch { return null; }
}
function sourceRecord(row) {
 return (!row?.openapi || typeof row.openapi==='object' && ['method','path','version','title','artifact_id','sha256'].every(key=>typeof row.openapi[key]==='string')) && row && typeof row==='object' && !Array.isArray(row) && ['source_id','name'].every(k=>typeof row[k]==='string'&&row[k].trim()) && ['endpoint','credential_ref','auth_header','records_path','target_model'].every(k=>row[k]==null||typeof row[k]==='string');
}
function sourceInventory(data,offset) {
 if(!data||!Array.isArray(data.sources)||!data.sources.every(sourceRecord)||new Set(data.sources.map(r=>r.source_id)).size!==data.sources.length||(data.total!=null&&(!Number.isSafeInteger(data.total)||data.total<offset+data.sources.length))||(data.next_offset!=null&&(!Number.isSafeInteger(data.next_offset)||data.next_offset<=offset)))throw new Error('Source catalog returned invalid records. Refresh sources before selecting an API.');
 return data.sources;
}
function previewRecords(data) {
 if(!data||!Number.isSafeInteger(data.record_count)||data.record_count<0||!Array.isArray(data.records)||data.records.length>10||data.record_count<data.records.length||!data.records.every(r=>r&&typeof r==='object'&&!Array.isArray(r)))throw new Error('Preview returned invalid records. Connection results could not be confirmed.');
 return data;
}
export default function RestSourcesPanel() {
  const [sourceFilter,setSourceFilter]=useState('');
  const [contract,setContract]=useState(null),[operation,setOperation]=useState(''),[importing,setImporting]=useState(false),[connection,setConnection]=useState(null);
  const importSequence=useRef(0),nameInput=useRef(null);
  const draft=()=>({...empty,source_id:'rest-'+createSubmissionId().replace(/[^a-z0-9]/gi,'').slice(0,40).toLowerCase()});
  const [form,setForm] = useState(draft), [sources,setSources] = useState([]), [jobs,setJobs] = useState([]);
  const [source,setSource] = useState(''), [job,setJob] = useState(''), [preview,setPreview] = useState(null);
  const [message,setMessage] = useState(''), [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const [pending,setPending] = useState(readPending);
  const [availability,setAvailability]=useState({sources:'not_loaded',jobs:'not_loaded'});
  const [page,setPage] = useState({offset:0,total:0,next:null});
  const [loadingSources,setLoadingSources] = useState(false), [loadingJobs,setLoadingJobs] = useState(false);
  const loadSequence=useRef(0);
  const generation = useRef(0), lock = useRef(false);
  useEffect(() => {
    const reset = () => { generation.current++; loadSequence.current++; lock.current=false; setBusy(false); setLoadingSources(false);setLoadingJobs(false);setSources([]); setJobs([]); setSource(''); setJob(''); setPreview(null);setConnection(null);setForm(draft());setContract(null);setOperation('');setImporting(false);importSequence.current++;setSourceFilter('');setAvailability({sources:'not_loaded',jobs:'not_loaded'}); setMessage(''); setError('Access changed. Refresh sources. Retained runs remain in Data Flow.'); };
    const storage = event => { if(event.key===pendingKey) setPending(readPending()); };
    events.forEach(event => window.addEventListener(event,reset)); window.addEventListener('storage',storage);
    return () => { generation.current++; importSequence.current++; events.forEach(event => window.removeEventListener(event,reset)); window.removeEventListener('storage',storage); };
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
    setLoadingSources(true);setLoadingJobs(true);setAvailability({sources:'loading',jobs:'loading'});setError('');
    return (async () => {
      const errors=[];
      await Promise.all([
        api.restSources({params:{limit:50,offset}}).then(result => apply(() => {
          const rows=sourceInventory(result.data,offset);
          setAvailability(value=>({...value,sources:'ready'}));setSources(rows);setPage({offset,total:result.data.total ?? rows.length,next:result.data.next_offset ?? null});
          setSource(old => rows.some(item => item.source_id===old) ? old : '');setPreview(null);
        })).catch(failure => {errors.push(apiErrorMessage(failure,'Source catalog unavailable'));apply(() => {setAvailability(value=>({...value,sources:'unavailable'}));setSources([]);setSource('');setPreview(null);});}).finally(() => apply(() => setLoadingSources(false))),
        api.definitions().then(result => apply(() => {
          if(!Array.isArray(result.data?.definitions)||!result.data.definitions.every(item=>item&&typeof item.job_id==='string'&&typeof item.version==='string'&&typeof item.name==='string'&&typeof item.enabled==='boolean'))throw new Error('Job catalog returned invalid definitions.');
          const rows=result.data.definitions.filter(item => item.job_type==='rest-source-ingest' && item.lifecycle_state==='approved' && item.enabled);
          setAvailability(value=>({...value,jobs:'ready'}));setJobs(rows);setJob(old => rows.some(item => `${item.job_id}@${item.version}`===old) ? old : '');
        })).catch(failure => {errors.push(apiErrorMessage(failure,'Job catalog unavailable'));apply(() => {setAvailability(value=>({...value,jobs:'unavailable'}));setJobs([]);setJob('');});}).finally(() => apply(() => setLoadingJobs(false))),
      ]);
      if(errors.length) apply(() => setError(errors.join('; ')));
    })();
  }
  useEffect(()=>{load(0);},[]);
  function retain(value, expectedKey=value.key) { retainAcquisition(pendingKey,value,expectedKey); setPending(value); }
  function reconcile(value, initial=false) {
    return act(async apply => {
      checkAcquisitionReference(pendingKey,value.key);
      let response;
      if(value.runId) response=await api.getRun(value.runId);
      else {
        if(!initial) {
          response=await api.restSubmission(value.key,token('DATA_JOB_EXECUTION_TOKEN'));
          if(response.data?.submission_id!==value.key)throw new Error('Acquisition receipt does not match the saved submission.');
          if(response.data.status==='pending_enqueue'&&!response.data.run_manifest&&!response.data.run) {
            apply(()=>{retain({...value,status:'pending_enqueue'});setMessage('Submission retained; execution is not confirmed. Recover the same submission explicitly if needed. No fetch was submitted by this status check.');});
            return;
          }
        } else {
          checkAcquisitionReference(pendingKey,value.key);
          response=await api.runDefinition(value.jobId,value.version,{source_id:value.source,idempotency_key:value.key},{approval_token:token('DATA_JOB_EXECUTION_TOKEN'),approved_by:'source-reader'});
        }
      }
      const run=acquisitionRun(response.data,{runId:value.runId,submissionId:value.key});
      apply(() => {retain({...value,runId:run.run_id,status:run.status});setMessage(`Run ${run.run_id}: ${run.status}. Inspect its retained output in Data Flow.`);});
    });
  }
  function newSource(){setSource('');setPreview(null);setForm(draft());setContract(null);setOperation('');setError('');setMessage('');requestAnimationFrame(()=>nameInput.current?.focus());}
  async function importContract(event){
    const file=event.target.files?.[0];event.target.value='';if(!file)return;
    const epoch=generation.current,sequence=++importSequence.current;setImporting(true);setError('');
    try{
      if(file.size>5*1024*1024)throw new Error('OpenAPI JSON must be at most 5 MiB.');
      const document=JSON.parse(await file.text());const value=openApiSourceDrafts(document,file.name);
      if(epoch!==generation.current||sequence!==importSequence.current)return;
      setContract({...value,document});setOperation('');setSource('');setPreview(null);
      setMessage(value.sourceDrafts.length?'Select a GET operation to prepare its source details.':'No GET operations are available for source acquisition.');
    }catch(failure){if(epoch===generation.current&&sequence===importSequence.current)setError(apiErrorMessage(failure,'OpenAPI import failed.'));}
    finally{if(epoch===generation.current&&sequence===importSequence.current)setImporting(false);}
  }
  function chooseOperation(value){
    setOperation(value);const draft=contract?.sourceDrafts.find(row=>row.key===value);if(!draft)return;
    setForm({...empty,source_id:'rest-'+createSubmissionId().replace(/[^a-z0-9]/gi,'').slice(0,40).toLowerCase(),name:draft.name,endpoint:draft.endpoint,auth_header:draft.auth_header});
    setMessage(draft.issue||'Source details prepared. Review and save to register this API.');
  }
  const imported=contract?.sourceDrafts.find(row=>row.key===operation);
  const selectedSource=sources.find(row=>row.source_id===source);
  const fields=[['source_id','Source ID','parts-api'],['name','Source name','Released parts'],['endpoint','HTTP(S) endpoint','https://plm.example.com/api/parts'],['records_path','Records path (optional)','data.items'],['credential_ref','Server secret reference (optional)','DEPO_REST_SECRET_PLM'],['target_model','Target model reference (optional)','Business model reference']];
  const visibleSources=sources.filter(item=>[item.name,item.source_id,item.endpoint].some(value=>String(value||'').toLowerCase().includes(sourceFilter.trim().toLowerCase())));
  return <section className="data-source-section rest-sources" aria-label="REST data sources"><header className="data-source-section-heading"><div><h2>REST data sources</h2></div><div className="data-source-toolbar">
    <button disabled={busy||loadingSources||loadingJobs} onClick={() => load(page.offset)}>Refresh sources and jobs</button>
    <button type="button" disabled={busy||importing} onClick={newSource}>Add source</button>
    <label className="data-source-import">{importing?'Reading OpenAPI...':'Import OpenAPI JSON'}<input aria-label="Import OpenAPI JSON" type="file" accept="application/json,.json" onChange={importContract} disabled={busy||importing}/></label>
    </div></header>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <div className="rest-source-workspace"><section className="rest-source-registry" aria-label="Source register">
      <h3>Registered REST APIs</h3><label className="data-source-search">Find registered APIs<input type="search" value={sourceFilter} onChange={event=>setSourceFilter(event.target.value)} placeholder="Name, source ID or endpoint" disabled={busy||loadingSources}/></label>
      {availability.sources==='ready'&&<><p className="data-source-hint">{visibleSources.length} shown on this page · {page.total} registered API(s).</p>
      {sources.length>0?<div className="data-source-table"><table aria-label="Registered REST APIs"><thead><tr><th>API / source number</th><th>Endpoint</th><th>Connection</th></tr></thead><tbody>
       {visibleSources.map(item=><tr key={item.source_id} data-selected={source===item.source_id}><td><button type="button" disabled={busy||loadingSources||importing} aria-label={`Select ${item.name}`} aria-pressed={source===item.source_id} onClick={()=>{setSource(item.source_id);setPreview(null);setError('');setMessage('');}}>{item.name}</button><small>{item.source_number || item.source_id}</small></td><td>{item.endpoint||'Not recorded'}</td><td>{item.connection_ready===false?'Host setup needed':connection?.sourceId===item.source_id?connection.status:'Not tested'}</td></tr>)}
      </tbody></table>{!visibleSources.length&&<p>No APIs on this page match your search.</p>}</div>:<p>No REST APIs registered yet. Add a source or import OpenAPI JSON.</p>}</>}
    </section><section className="rest-source-detail" aria-label={selectedSource?'Selected source details':'New source details'}>
    {selectedSource?<><h3>{selectedSource.name}</h3><dl><dt>Source number</dt><dd>{selectedSource.source_number||selectedSource.source_id}</dd><dt>Endpoint</dt><dd>{selectedSource.endpoint||'Not recorded'}</dd><dt>Authentication</dt><dd>{selectedSource.credential_ref?selectedSource.auth_header||'Authorization':'No credential reference'}</dd><dt>Records path</dt><dd>{selectedSource.records_path||'Response root'}</dd>{selectedSource.openapi&&<><dt>OpenAPI operation</dt><dd>{selectedSource.openapi.method} {selectedSource.openapi.path}</dd><dt>API specification</dt><dd>{selectedSource.openapi.title||selectedSource.openapi.version}</dd></>}</dl>
    {selectedSource.connection_ready===false&&<p role="status">Source saved. Ask the administrator to allow this endpoint host before testing or fetching records.</p>}
    <button disabled={busy||loadingSources||selectedSource.connection_ready===false} onClick={()=>{const id=source;setPreview(null);setConnection({sourceId:id,status:'Checking'});act(async apply=>{try{const result=await api.previewRestSource(id,token('DATA_JOB_EXECUTION_TOKEN'));const records=previewRecords(result.data);apply(()=>{setPreview(records);setConnection({sourceId:id,status:'Preview succeeded'});});}catch(failure){apply(()=>setConnection({sourceId:id,status:'Failed'}));throw failure;}});}}>Test connection and preview</button></>:<><h3>Register a REST source</h3>
      {contract&&<label className="data-source-operation">OpenAPI operation<select value={operation} disabled={busy||importing} onChange={event=>chooseOperation(event.target.value)}><option value="">Select a GET operation</option>{contract.sourceDrafts.map(row=><option key={row.key} value={row.key}>{row.label}{row.issue?' · review needed':''}</option>)}</select></label>}
      <form onSubmit={event => {event.preventDefault();if(importing||contract&&!imported)return;act(async apply => {
        const submitted={...form,...(imported?{openapi_document:contract.document,openapi_path:imported.path}:{})};
        const result=await api.registerRestSource(submitted,token('DATA_JOB_APPROVAL_TOKEN'));
        if(!sourceRecord(result.data)||result.data.source_id!==submitted.source_id)throw new Error('Source registration was not confirmed. Refresh sources before retrying.');
        apply(() => {setSourceFilter('');setSource(result.data.source_id);setForm(draft());setContract(null);setOperation('');setPreview(null);setMessage('Source registered. Refreshing the catalog; test its connection after it loads.');load(0);});
      });}}><fieldset disabled={busy||importing}><div className="data-source-form-grid">
        {fields.filter(([key])=>['name','endpoint'].includes(key)).map(([key,label,placeholder])=><label key={key}>{label}<input ref={key==='name'?nameInput:undefined} required maxLength={500} type={key==='endpoint'?'url':'text'} value={form[key]} placeholder={placeholder} onChange={event=>setForm(previous=>({...previous,[key]:event.target.value}))}/></label>)}
        <label>Authentication header<select value={form.auth_header} onChange={event=>setForm(previous=>({...previous,auth_header:event.target.value}))}><option value="Authorization">Bearer token</option><option value="X-API-Key">X-API-Key</option><option value="api-key">api-key</option></select></label>
        <label>{imported?.requiresCredential?'Server secret reference':'Server secret reference (optional)'}<input required={imported?.requiresCredential===true} maxLength={81} pattern="DEPO_REST_SECRET_[A-Z0-9_]{1,64}" value={form.credential_ref} placeholder="DEPO_REST_SECRET_PLM" onChange={event=>setForm(previous=>({...previous,credential_ref:event.target.value}))}/></label>
      </div><details><summary>Additional settings</summary><div className="data-source-form-grid">
        {fields.filter(([key])=>['source_id','records_path','target_model'].includes(key)).map(([key,label,placeholder])=><label key={key}>{label}<input required={key==='source_id'} maxLength={key==='source_id'?63:500} pattern={key==='source_id'?'[a-z](?:[a-z0-9]|-){2,62}':key==='records_path'?'(?:[A-Za-z0-9_]|-)+(?:[.](?:[A-Za-z0-9_]|-)+)*':undefined} value={form[key]} placeholder={placeholder} onChange={event=>setForm(previous=>({...previous,[key]:event.target.value}))}/></label>)}
      </div></details><div className="data-source-form-actions"><button className="data-source-primary" disabled={busy||loadingSources||importing||Boolean(imported?.issue)||Boolean(contract&&!imported)} type="submit">Register source</button></div></fieldset></form></>}
    <div className="rest-source-actions"><label>Approved acquisition job<select disabled={busy||loadingJobs} value={job} onChange={event => setJob(event.target.value)}><option value="">Select an approved job</option>{jobs.map(item => <option key={`${item.job_id}@${item.version}`} value={`${item.job_id}@${item.version}`}>{item.name} · {item.version}</option>)}</select></label>
      <button className="data-source-primary" disabled={busy||loadingSources||loadingJobs||!sourceExists||selectedSource?.connection_ready===false||!chosen||!!pending} onClick={() => {
        try {const value={key:createSubmissionId(),source,jobId:chosen.job_id,version:chosen.version};retain(value,null);reconcile(value,true);}
        catch(failure){setPending(readPending());setError(apiErrorMessage(failure,'Unable to retain a safe submission reference. Enable local browser storage before submitting.'));}
      }}>Fetch records with worker</button></div>
    {!selectedSource&&<button disabled type="button">Test connection and preview</button>}
    </section></div>
    <div className="data-source-pagination" aria-label="Source pages"><span>{availability.sources==='ready'?<>{page.total} sources · page {Math.floor(page.offset/50)+1}</>:availability.sources==='loading'?'Loading sources…':availability.sources==='unavailable'?'Source count unavailable':'Refresh to load sources'}</span> <button disabled={busy||availability.sources!=='ready'||page.offset===0} onClick={() => load(Math.max(0,page.offset-50))}>Previous sources</button> <button disabled={busy||availability.sources!=='ready'||page.next===null} onClick={() => load(page.next)}>Next sources</button></div>
    {pending && <div role="status"><p>Retained submission for {pending.source}: {pending.runId || pending.key} · {pending.status || 'outcome not confirmed'}. Reconnect does not submit a new fetch.</p><button disabled={busy} onClick={() => reconcile(pending)}>Refresh retained submission</button>{!pending.runId&&<button disabled={busy} onClick={()=>reconcile(pending,true)}>Recover same submission</button>}{['completed','failed','quality_warning'].includes(pending.status) && <button disabled={busy} onClick={() => {try{clearAcquisition(pendingKey,pending.key);setPending(null);}catch(failure){setPending(readPending());setError(apiErrorMessage(failure,'Retained submission changed.'));}}}>Prepare another fetch</button>} <a href="#/data-flow">Review runs in Data Flow</a></div>}
    {availability.jobs==='unavailable'&&<p>Approved acquisition jobs are unavailable. Refresh sources and jobs to check access and service readiness.</p>}
    {availability.jobs==='ready'&&!jobs.length && <p>No approved acquisition job loaded. <button disabled={busy} onClick={() => act(async apply => {
      await api.createDefinition({job_id:'rest-source-acquisition',name:'REST source acquisition',version:'1.0.0',owner:'source-author',job_type:'rest-source-ingest',quality_profile:'semantic-core-v1'},token('DATA_JOB_APPROVAL_TOKEN'));
      apply(() => setMessage('Draft job created. Review and approve it in Data Flow, then refresh sources and jobs.'));
    })}>Create acquisition job draft</button> No approval is granted automatically.</p>}
    {preview && <div><h3>Connection succeeded · {preview.record_count} records</h3><p>Up to 10 records shown. Preview does not retain an ingestion.</p><div className="data-source-table"><table><thead><tr><th>Record</th><th>Property</th><th>Value</th></tr></thead><tbody>{preview.records.flatMap((record,index) => Object.entries(record).slice(0,30).map(([key,value]) => <tr key={`${index}:${key}`}><td>{index+1}</td><td>{key}</td><td>{(typeof value==='object'?JSON.stringify(value):String(value)).slice(0,500)}</td></tr>))}</tbody></table></div></div>}
    <p>One GET endpoint per fetch: HTTP or HTTPS on standard ports, allowed public hosts only, no redirects, maximum 2 MiB and 1,000 records. Both support server-referenced keys. Pagination and recurring refresh are not configured here. Target model is a reference, not an automatic mapping. <a href="#/data-flow">Open Data Flow</a> for job approval, runs and retained artifacts.</p>
  </section>;
}

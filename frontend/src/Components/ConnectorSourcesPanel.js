import React,{useEffect,useRef,useState} from 'react';
import {dataPipelineAPI as api} from '../services/apiClient';
import {getCredentialProfile} from '../services/serviceAuth';
import {createSubmissionId} from '../utils/submissionId';
import {acquisitionRun,checkAcquisitionReference,retainAcquisition,clearAcquisition} from '../utils/acquisitionReceipt';
import {apiErrorMessage} from '../utils/apiErrorMessage';

const key='depo:connector-acquisition:v1';
function saved(){try{const p=JSON.parse(localStorage.getItem(key));return p&&typeof p.key==='string'&&typeof p.source==='string'&&typeof p.job==='string'?p:null;}catch{return null;}}
function token(name){const t=getCredentialProfile(name);if(!t)throw new Error('Connect the required source/job authorization in Admin → API access.');return t;}
function validRows(rows, fields){
 return Array.isArray(rows)&&rows.every(row=>row&&fields.every(field=>typeof row[field]==='string'&&row[field].length>0));
}
function validInventory(profiles,sources,definitions,next,offset){
 return validRows(profiles,['profile_id','name','kind'])&&new Set(profiles.map(p=>p.profile_id)).size===profiles.length&&
  profiles.every(p=>typeof p.configured==='boolean'&&Array.isArray(p.resources)&&p.resources.every(r=>typeof r==='string'&&r.length>0))&&
  validRows(sources,['source_id','name','kind'])&&new Set(sources.map(s=>s.source_id)).size===sources.length&&
  validRows(definitions,['job_id','version','name','job_type','lifecycle_state'])&&definitions.every(d=>typeof d.enabled==='boolean')&&
  (next==null||(Number.isSafeInteger(next)&&next>offset));
}
export default function ConnectorSourcesPanel(){
 const [loadFailed,setLoadFailed]=useState(false),[profiles,setProfiles]=useState([]),[sources,setSources]=useState([]),[jobs,setJobs]=useState([]);
 const [profile,setProfile]=useState(''),[resource,setResource]=useState(''),[name,setName]=useState(''),[source,setSource]=useState(''),[job,setJob]=useState('');
 const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[pending,setPending]=useState(saved),[offset,setOffset]=useState(0),[more,setMore]=useState(null),[revision,setRevision]=useState(0);
 const generation=useRef(0),lock=useRef(false),registration=useRef(null),registeredSource=useRef(null);
 useEffect(()=>{
  const clear=()=>{generation.current++;lock.current=false;setBusy(false);setProfiles([]);setSources([]);setJobs([]);setSource('');setJob('');setProfile('');setResource('');setName('');setOffset(0);setMore(null);setMessage('');registration.current=null;registeredSource.current=null;setError('Access changed. Retained submissions are preserved.');setRevision(n=>n+1);};
  const storage=e=>{if(e.key===key)setPending(saved());};
  const events=['depo:session-replaced','depo:session-expired','depo:credentials-changed','depo:credentials-cleared'];events.forEach(e=>window.addEventListener(e,clear));window.addEventListener('storage',storage);
  return()=>{generation.current++;events.forEach(e=>window.removeEventListener(e,clear));window.removeEventListener('storage',storage);};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();const current=generation.current;setLoading(true);setLoadFailed(false);const opts={signal:controller.signal,timeout:15000};
  Promise.all([api.connectorProfiles(opts),api.connectorSources({...opts,params:{limit:50,offset}}),api.definitions(opts)]).then(([p,s,j])=>{
   if(controller.signal.aborted||current!==generation.current)return;
   if(!validInventory(p.data?.profiles,s.data?.sources,j.data?.definitions,s.data?.next_offset,offset))throw new Error('Invalid connector workspace response');
   const rows=registeredSource.current&&!s.data.sources.some(r=>r.source_id===registeredSource.current.source_id)?[registeredSource.current,...s.data.sources]:s.data.sources;
   setProfiles(p.data.profiles);setSources(rows);setMore(s.data.next_offset??null);setSource(v=>rows.some(r=>r.source_id===v)?v:'');
   const approved=j.data.definitions.filter(r=>r.job_type==='registered-source-ingest'&&r.lifecycle_state==='approved'&&r.enabled);setJobs(approved);setJob(v=>approved.some(r=>`${r.job_id}@${r.version}`===v)?v:'');setError('');setLoading(false);
  }).catch(e=>{if(!controller.signal.aborted&&current===generation.current){registeredSource.current=null;setLoadFailed(true);setProfiles([]);setSources([]);setJobs([]);setSource('');setJob('');setProfile('');setResource('');setMore(null);setError(apiErrorMessage(e,'Source configuration could not be loaded.'));setLoading(false);}});
  return()=>controller.abort();
 },[revision,offset]);
 useEffect(()=>{
  if(loading||loadFailed||!profile)return;
  const current=profiles.find(p=>p.profile_id===profile);
  if(!current){setProfile('');setResource('');registration.current=null;}
  else if(resource&&!current.resources.includes(resource)){setResource('');registration.current=null;}
 },[profiles,profile,resource,loading,loadFailed]);
 async function action(fn){if(lock.current)return;lock.current=true;setBusy(true);setError('');setMessage('');const current=generation.current;
  try{const apply=callback=>{if(current===generation.current)callback();};const result=await fn(apply);if(current===generation.current){if(result)setMessage(result);setRevision(n=>n+1);}}
  catch(e){if(current===generation.current)setError(apiErrorMessage(e,'Operation was not confirmed. Inspect retained source/run state before retrying.'));}
  finally{if(current===generation.current){lock.current=false;setBusy(false);}}
 }
 async function submitPending(p,apply,approval){
  checkAcquisitionReference(key,p.key);
  const [id,version]=p.job.split('@');
  const response=await api.runDefinition(id,version,{source_id:p.source,idempotency_key:p.key},approval);
  const run=acquisitionRun(response.data,{runId:p.run_id,submissionId:p.key});
  const updated={...p,run_id:run.run_id,status:run.status};apply(()=>{retainAcquisition(key,updated);setPending(updated);});
  return 'Acquisition queued. Follow its retained run in Data Flow.';
 }
 const selected=profiles.find(p=>p.profile_id===profile);
 return <section className="depo-panel" id="connector-source-configuration" aria-label="Additional source connectors">
  <h3>Connect enterprise data sources</h3>{loadFailed&&<p role="status">Connection availability is unknown. Refresh connections and jobs before configuring or acquiring records.</p>}{loading&&<p role="status">Loading connections and jobs…</p>}<p>Select an operator-configured connection and an allowed resource. Credentials stay on the server. Acquisition prepares retained records; it does not approve semantic mappings or publish a data product.</p>
  <button disabled={busy||loading} onClick={()=>setRevision(n=>n+1)}>Refresh connections and jobs</button>
  {!loading&&!loadFailed&&!profiles.length&&<p>No enterprise connection profiles are configured. Ask your deployment administrator to configure DEPO_CONNECTOR_PROFILES and its dedicated secret references. File, XML and ontology imports remain in their existing workspaces.</p>}
  <div className="connector-source-fields"><label>Connection<select disabled={busy||loading||loadFailed} value={profile} onChange={e=>{setProfile(e.target.value);setResource('');registration.current=null;}}><option value="">Select a connection</option>{profiles.map(p=><option key={p.profile_id} value={p.profile_id}>{p.name} · {p.kind}{p.configured?'':' · setup needed'}</option>)}</select></label>
  <label>Resource<select disabled={busy||loading||loadFailed} value={resource} onChange={e=>{setResource(e.target.value);registration.current=null;}}><option value="">Select a resource</option>{selected?.resources.map(r=><option key={r} value={r}>{r}</option>)}</select></label>
  <label>Source display name<input disabled={busy||loading||loadFailed} value={name} maxLength={200} onChange={e=>{setName(e.target.value);registration.current=null;}}/></label>
  <button disabled={busy||loading||loadFailed||!selected?.configured||!selected.resources.includes(resource)||!name.trim()} onClick={()=>action(async(apply)=>{
   const id=registration.current||('source-'+createSubmissionId().replace(/[^a-z0-9]/gi,'').slice(0,40).toLowerCase());registration.current=id;
   const response=await api.registerConnector({source_id:id,name:name.trim(),profile_id:profile,resource},token('DATA_JOB_APPROVAL_TOKEN'));if(typeof response.data?.source_id!=='string'||response.data.source_id!==id)throw new Error('Source registration was not confirmed. Refresh before retrying.');apply(()=>{registeredSource.current=response.data;setSources(rows=>rows.some(row=>row.source_id===response.data.source_id)?rows:[response.data,...rows]);setSource(response.data.source_id);});return 'Source reference registered. Select an approved acquisition job below.';
  })}>Register source reference</button></div>
  <div className="connector-source-fields"><label>Registered source<select disabled={busy||loading||loadFailed} value={source} onChange={e=>setSource(e.target.value)}><option value="">Select a registered source</option>{sources.map(s=><option key={s.source_id} value={s.source_id}>{s.name}{s.source_number ? ' · ' + s.source_number : ''} · {s.kind}</option>)}</select></label>
  <label>Approved acquisition job<select disabled={busy||loading||loadFailed} value={job} onChange={e=>setJob(e.target.value)}><option value="">Select an approved job</option>{jobs.map(j=><option key={`${j.job_id}@${j.version}`} value={`${j.job_id}@${j.version}`}>{j.name} · {j.version}</option>)}</select></label>
  <button disabled={busy||loading||loadFailed||!!pending||!sources.some(s=>s.source_id===source)||!jobs.some(j=>`${j.job_id}@${j.version}`===job)} onClick={()=>action(async(apply)=>{
   const approval={approval_token:token('DATA_JOB_EXECUTION_TOKEN'),approved_by:'source-reader'};if(saved())throw new Error('Reconcile the retained acquisition before starting another.');const p={key:createSubmissionId(),source,job};retainAcquisition(key,p,null);setPending(p);
   return submitPending(p,apply,approval);
  })}>Acquire records with worker</button></div>
  {!loading&&!loadFailed&&!jobs.length&&<button disabled={busy||loading||loadFailed} onClick={()=>action(async(apply)=>{await api.createDefinition({job_id:'enterprise-source-acquisition',name:'Enterprise source acquisition',version:'1.0.0',owner:'source-author',job_type:'registered-source-ingest',quality_profile:'semantic-core-v1'},token('DATA_JOB_APPROVAL_TOKEN'));return 'Job draft created. Review and approve it in Data Flow; approval is not automatic.';})}>Create acquisition job draft</button>}
  {pending&&<p role="status">Retained acquisition: {pending.status||'outcome not confirmed'}. <button disabled={busy} onClick={()=>action(async(apply)=>{const response=await api.connectorSubmission(pending.key,token('DATA_JOB_EXECUTION_TOKEN'));let updated;if(response.data?.status==='pending_enqueue'&&!response.data.run_manifest&&!pending.run_id){if(response.data.submission_id!==pending.key)throw new Error('Acquisition receipt does not match the saved submission.');updated={...pending,status:'pending_enqueue'};}else{const run=acquisitionRun(response.data,{runId:pending.run_id,submissionId:pending.key});updated={...pending,status:run.status,run_id:run.run_id};}apply(()=>{retainAcquisition(key,updated);setPending(updated);});return 'Retained submission checked; no acquisition was resubmitted.';})}>Check retained acquisition</button>{!pending.run_id&&<button disabled={busy||loading||loadFailed} onClick={()=>action(apply=>submitPending(pending,apply,{approval_token:token('DATA_JOB_EXECUTION_TOKEN'),approved_by:'source-reader'}))}>Recover same submission</button>}{['completed','failed','quality_warning'].includes(pending.status)&&<button disabled={busy} onClick={()=>{try{clearAcquisition(key,pending.key);setPending(null);}catch(e){setPending(saved());setError(apiErrorMessage(e,'Retained acquisition changed.'));}}}>Prepare another acquisition</button>}{pending.run_id&&<a href={`#/data-flow?run_id=${encodeURIComponent(pending.run_id)}`}>Open acquisition run</a>}</p>}
  <button disabled={busy||loading||loadFailed||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous sources</button><button disabled={busy||loading||loadFailed||more===null} onClick={()=>setOffset(more)}>Next sources</button>
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}

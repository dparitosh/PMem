import React,{useEffect,useRef,useState} from 'react';
import {apiClient,dataPipelineAPI} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {getCredentialProfile} from '../services/serviceAuth';
import {createSubmissionId} from '../utils/submissionId';
import {apiErrorMessage} from '../utils/apiErrorMessage';

export default function OslcSourcesPanel(){
 const [snapshots,setSnapshots]=useState([]),[jobs,setJobs]=useState([]),[selected,setSelected]=useState(''),[job,setJob]=useState('');
 const [revision,setRevision]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false),[run,setRun]=useState('');
 const request=useRef(null),generation=useRef(0),lock=useRef(false);
 useEffect(()=>{
  const changed=()=>{generation.current++;request.current?.abort();lock.current=false;setBusy(false);setSnapshots([]);setSelected('');setJobs([]);setJob('');setRun('');setRevision(n=>n+1);};
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];events.forEach(name=>window.addEventListener(name,changed));
  return()=>{generation.current++;request.current?.abort();events.forEach(name=>window.removeEventListener(name,changed));};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();request.current=controller;const current=generation.current;
  Promise.all([apiClient.get(buildSemanticServiceUrl('oslc','/api/v1/oslc/remote/sync'),{signal:controller.signal}),dataPipelineAPI.definitions({signal:controller.signal})]).then(([s,j])=>{
   if(controller.signal.aborted||current!==generation.current)return;
   if(!Array.isArray(s.data?.syncs)||!Array.isArray(j.data?.definitions))throw new Error('Invalid source review response');
   setSnapshots(s.data.syncs);setJobs(j.data.definitions.filter(row=>row.job_type==='oslc-snapshot-ingest'&&row.lifecycle_state==='approved'&&row.enabled));setError('');
  }).catch(e=>{if(!controller.signal.aborted&&current===generation.current)setError(apiErrorMessage(e));});
  return()=>controller.abort();
 },[revision]);
 async function createDraft(){
  if(lock.current)return;lock.current=true;setBusy(true);setError('');const current=generation.current;
  try{const token=getCredentialProfile('DATA_JOB_APPROVAL_TOKEN');if(!token)throw new Error('Connect workflow authoring access in Admin.');
   await dataPipelineAPI.createDefinition({job_id:'oslc-snapshot-preparation',name:'Linked lifecycle record preparation',version:'1.0.0',owner:'source-author',job_type:'oslc-snapshot-ingest',quality_profile:'semantic-core-v1'},token);
   if(current===generation.current)setRevision(n=>n+1);
  }catch(e){if(current===generation.current)setError(apiErrorMessage(e));}
  finally{if(current===generation.current){lock.current=false;setBusy(false);}}
 }
 async function prepare(){
  if(lock.current||!selected||!job)return;lock.current=true;setBusy(true);setError('');const current=generation.current;
  const controller=new AbortController();request.current=controller;
  try{
   const token=getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');if(!token)throw new Error('Connect processing access in Admin → API access.');
   const storageKey='depo:oslc-preparation:'+selected+':'+job;
   const idempotencyKey=localStorage.getItem(storageKey)||createSubmissionId();localStorage.setItem(storageKey,idempotencyKey);
   const [id,version]=job.split('@');
   const response=await dataPipelineAPI.runDefinition(id,version,{snapshot_id:selected,idempotency_key:idempotencyKey},{approval_token:token,approved_by:'source-reader'},{signal:controller.signal});
   if(!controller.signal.aborted&&current===generation.current)setRun(response.data?.run_id||response.data?.run?.run_id||'');
  }catch(e){if(!controller.signal.aborted&&current===generation.current)setError(apiErrorMessage(e));}
  finally{if(current===generation.current){lock.current=false;setBusy(false);}}
 }
 const snapshot=snapshots.find(row=>row.sync_id===selected);
 return <section aria-label="Linked lifecycle sources"><h3>Review linked lifecycle records</h3><p>Choose a complete retained provider snapshot, then prepare its records with an approved workflow. Semantic mapping and graph publication remain separate review steps.</p>
 <button disabled={busy} onClick={()=>setRevision(n=>n+1)}>Refresh provider snapshots</button>
 {error&&<p role="alert">{error}</p>}
 <label>Provider snapshot<select value={selected} disabled={busy} onChange={e=>{setSelected(e.target.value);setRun('');}}><option value="">Choose retained records</option>{snapshots.map(row=><option key={row.sync_id} value={row.sync_id}>{row.resource_type} · {row.resource_count} records · {row.created_at} · {row.complete?'Complete':'Incomplete'}</option>)}</select></label>
 {snapshot&&<p>Provider: {snapshot.provider_url||'Not recorded'} · Requested by: {snapshot.requested_by||'Not recorded'}. {snapshot.complete?'Ready for preparation review.':'Acquire the remaining records before preparation.'}</p>}
 <label>Approved preparation workflow<select value={job} disabled={busy} onChange={e=>setJob(e.target.value)}><option value="">Choose a workflow</option>{jobs.map(row=><option key={row.job_id+'@'+row.version} value={row.job_id+'@'+row.version}>{row.name} · {row.version}</option>)}</select></label>
 {!jobs.length&&<button disabled={busy} onClick={createDraft}>Create preparation workflow draft</button>}
 {!jobs.length&&<p>An authorized owner must create and approve an OSLC snapshot preparation workflow in <a href="#/data-flow?view=definitions">Data Flow</a>.</p>}
 <button disabled={busy||!snapshot?.complete||!snapshot?.content_sha256||!job} onClick={prepare}>{busy?'Submitting preparation…':'Prepare selected records'}</button>
 {run&&<p>Preparation submitted. <a href={'#/data-flow?view=runs&run_id='+encodeURIComponent(run)}>Review processing and retained evidence</a></p>}
 </section>;
}

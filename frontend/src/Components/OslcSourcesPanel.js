import React,{useEffect,useRef,useState} from 'react';
import {apiClient,dataPipelineAPI} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {getCredentialProfile} from '../services/serviceAuth';
import {createSubmissionId} from '../utils/submissionId';
import {acquisitionRun} from '../utils/acquisitionReceipt';
import {apiErrorMessage} from '../utils/apiErrorMessage';

function text(value){return typeof value==='string'&&value.trim().length>0;}
function validSnapshots(rows){
 return Array.isArray(rows)&&rows.every(row=>row&&text(row.sync_id)&&text(row.resource_type)&&
  Number.isSafeInteger(row.resource_count)&&row.resource_count>=0&&typeof row.complete==='boolean'&&
  ['content_sha256','provider_url','requested_by','created_at','status'].every(key=>row[key]==null||typeof row[key]==='string'))&&
  new Set(rows.map(row=>row.sync_id)).size===rows.length;
}
function validJobs(rows){
 return Array.isArray(rows)&&rows.every(row=>row&&['job_id','version','name','job_type','lifecycle_state'].every(key=>text(row[key]))&&typeof row.enabled==='boolean')&&
  new Set(rows.map(row=>row.job_id+'@'+row.version)).size===rows.length;
}
function snapshotIssue(snapshot){
 if(!snapshot)return 'Choose retained provider records before preparing them.';
 if(snapshot.complete!==true)return 'Acquire the remaining provider records before preparation.';
 if(!text(snapshot.content_sha256)||!text(snapshot.provider_url)||!text(snapshot.requested_by))return 'This snapshot is missing retained source evidence. Acquire it again from the provider before preparation.';
 if(snapshot.status!=='staged')return 'This snapshot is not in the retained preparation stage. Acquire a current provider snapshot.';
 if(snapshot.resource_count>1000)return 'Choose a snapshot with at most 1,000 records for preparation.';
 return '';
}
async function readPart(stage,operation,valid){
 try{const response=await operation();if(!valid(response.data))throw new Error('Invalid lifecycle source response');return response.data;}
 catch(error){throw {stage,error};}
}

export default function OslcSourcesPanel(){
 const [snapshots,setSnapshots]=useState([]),[jobs,setJobs]=useState([]),[selected,setSelected]=useState(''),[job,setJob]=useState('');
 const [revision,setRevision]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false),[run,setRun]=useState('');
 const [readState,setReadState]=useState({status:'loading'});
 const request=useRef(null),generation=useRef(0),lock=useRef(false);
 useEffect(()=>{
  const changed=()=>{generation.current++;request.current?.abort();lock.current=false;setBusy(false);setSnapshots([]);setSelected('');setJobs([]);setJob('');setRun('');setError('');setReadState({status:'loading'});setRevision(n=>n+1);};
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];events.forEach(name=>window.addEventListener(name,changed));
  return()=>{generation.current++;request.current?.abort();events.forEach(name=>window.removeEventListener(name,changed));};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();request.current=controller;const current=generation.current;
  setReadState({status:'loading'});setError('');
  const options={signal:controller.signal,timeout:15000};
  Promise.all([
   readPart('snapshots',()=>apiClient.get(buildSemanticServiceUrl('oslc','/api/v1/oslc/remote/sync'),options),data=>validSnapshots(data?.syncs)),
   readPart('workflows',()=>dataPipelineAPI.definitions(options),data=>validJobs(data?.definitions)),
  ]).then(([s,j])=>{
   if(controller.signal.aborted||current!==generation.current)return;
   const approved=j.definitions.filter(row=>row.job_type==='oslc-snapshot-ingest'&&row.lifecycle_state==='approved'&&row.enabled===true);
   setSnapshots(s.syncs);setJobs(approved);setSelected(value=>s.syncs.some(row=>row.sync_id===value)?value:'');
   setJob(value=>approved.some(row=>row.job_id+'@'+row.version===value)?value:'');setReadState({status:'ready'});
  }).catch(failure=>{
   if(controller.signal.aborted||current!==generation.current)return;
   const cause=failure.error||failure;
   const missingGrant=failure.stage==='snapshots'&&cause.response?.status===403&&String(cause.response?.data?.detail||'').includes('No lifecycle resource grant');
   setSnapshots([]);setJobs([]);setSelected('');setJob('');
   setReadState({status:missingGrant?'grant_required':'unavailable',stage:failure.stage,cause});
  });
  return()=>controller.abort();
 },[revision]);
 const ready=readState.status==='ready';
 const snapshot=snapshots.find(row=>row.sync_id===selected);
 const workflow=jobs.find(row=>row.job_id+'@'+row.version===job);
 const issue=snapshotIssue(snapshot);
 const canPrepare=ready&&!!workflow&&!issue;
 async function createDraft(){
  if(lock.current||!ready||!snapshots.length||jobs.length)return;lock.current=true;setBusy(true);setError('');const current=generation.current;
  try{const token=getCredentialProfile('DATA_JOB_APPROVAL_TOKEN');if(!token)throw new Error('Connect workflow authoring access in Admin.');
   await dataPipelineAPI.createDefinition({job_id:'oslc-snapshot-preparation',name:'Linked lifecycle record preparation',version:'1.0.0',owner:'source-author',job_type:'oslc-snapshot-ingest',quality_profile:'semantic-core-v1'},token);
   if(current===generation.current)setRevision(n=>n+1);
  }catch(e){if(current===generation.current)setError(apiErrorMessage(e));}
  finally{if(current===generation.current){lock.current=false;setBusy(false);}}
 }
 async function prepare(){
  if(lock.current||!canPrepare)return;lock.current=true;setBusy(true);setError('');const current=generation.current;
  const controller=new AbortController();request.current=controller;
  try{
   const token=getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');if(!token)throw new Error('Connect processing access in Admin → API access.');
   const storageKey='depo:oslc-preparation:'+selected+':'+job;
   const idempotencyKey=localStorage.getItem(storageKey)||createSubmissionId();localStorage.setItem(storageKey,idempotencyKey);
   const [id,version]=job.split('@');
   const response=await dataPipelineAPI.runDefinition(id,version,{snapshot_id:selected,idempotency_key:idempotencyKey},{approval_token:token,approved_by:'source-reader'},{signal:controller.signal});
   if(!controller.signal.aborted&&current===generation.current){const receipt=acquisitionRun(response.data,{runId:run||undefined,submissionId:idempotencyKey});setRun(receipt.run_id);}
  }catch(e){if(!controller.signal.aborted&&current===generation.current)setError(apiErrorMessage(e));}
  finally{if(current===generation.current){lock.current=false;setBusy(false);}}
 }
 return <section className="data-source-section linked-lifecycle-sources" aria-label="Linked lifecycle sources"><h3>Review linked lifecycle records</h3><p>Review records already acquired from a connected lifecycle provider, then prepare them with an approved workflow. Mapping review and publication remain separate steps.</p>
 <button disabled={busy||readState.status==='loading'} onClick={()=>setRevision(n=>n+1)}>Refresh provider snapshots</button>
 {readState.status==='loading'&&<p role="status">Checking provider snapshots and preparation workflows…</p>}
 {readState.status==='grant_required'&&<div role="status"><h4>Lifecycle snapshot access needs setup</h4><p>Your API sign-in is valid, but this account has not been granted access to review provider snapshots. Ask your deployment administrator to configure lifecycle source access. Revalidating API access alone does not add this permission.</p><a href="#/admin?view=services">Review lifecycle service setup</a></div>}
 {readState.status==='unavailable'&&<p role="alert">{readState.stage==='workflows'?'Preparation workflows':'Provider snapshots'} could not be loaded. Refresh to verify access and service availability before preparing records.</p>}
 {readState.cause&&<details><summary>Request details</summary><p>{apiErrorMessage(readState.cause)}</p></details>}
 {error&&<p role="alert">{error} <a href="#/data-flow?view=runs">Inspect retained processing runs</a> before retrying an unconfirmed submission.</p>}
 {ready&&<>
  {!snapshots.length?<p>No retained provider snapshots are available. Connect a lifecycle provider and acquire records before preparing them here.</p>:<>
   <div className="connector-source-fields">
    <label>Provider snapshot<select value={selected} disabled={busy} onChange={e=>{setSelected(e.target.value);setRun('');}}><option value="">Choose retained records</option>{snapshots.map(row=><option key={row.sync_id} value={row.sync_id}>{row.resource_type} · {row.resource_count} records · {row.created_at||'Date not recorded'} · {row.complete===true?'Complete':'Incomplete'}</option>)}</select></label>
    <label>Approved preparation workflow<select value={job} disabled={busy||!jobs.length} onChange={e=>{setJob(e.target.value);setRun('');}}><option value="">Choose a workflow</option>{jobs.map(row=><option key={row.job_id+'@'+row.version} value={row.job_id+'@'+row.version}>{row.name} · {row.version}</option>)}</select></label>
   </div>
   {snapshot&&<p>Provider: {snapshot.provider_url||'Not recorded'} · Requested by: {snapshot.requested_by||'Not recorded'}. {issue||'Ready for preparation review.'}</p>}
   {!jobs.length&&<><p>No approved preparation workflow is available. An authorized owner can review existing drafts in <a href="#/data-flow?view=pipelines">Data Flow</a> or create a preparation draft here. Creating a draft does not approve it.</p><button disabled={busy} onClick={createDraft}>Create preparation workflow draft</button></>}
   <button className="data-source-primary" disabled={busy||!canPrepare} onClick={prepare}>{busy?'Submitting preparation…':'Prepare selected records'}</button>
  </>}
 </>}
 {run&&<p>Preparation submitted. <a href={'#/data-flow?view=runs&run_id='+encodeURIComponent(run)}>Review processing and retained evidence</a></p>}
 </section>;
}

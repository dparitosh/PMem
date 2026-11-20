import React,{useEffect,useRef,useState} from 'react';
import {dataPipelineAPI} from '../services/apiClient';
import {getCredentialProfile,publicationRecoveryScope} from '../services/serviceAuth';
import {confirmedSubmissionRejection} from '../services/workflowSubmission';
import {apiErrorMessage} from '../utils/apiErrorMessage';

function recoveryKey(jobId,version){return JSON.stringify(['nexus.workflow-maintenance',publicationRecoveryScope(),jobId,version]);}
function readRecovery(key){try{const value=JSON.parse(sessionStorage.getItem(key)||'null');if(value&&typeof value.scope==='string'&&/^[0-9a-f-]{36}$/i.test(value.request_id)){const scope=JSON.parse(value.scope);if(Array.isArray(scope)&&scope.length===5)return value;}}catch{}return null;}
function retainRecovery(key,value){try{if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key);}catch{}}

export default function WorkflowDefinitionActions({jobId,version,onChanged}){
 const [definition,setDefinition]=useState(null),[runs,setRuns]=useState([]),[operation,setOperation]=useState(''),[interval,setInterval]=useState(300),[runId,setRunId]=useState(''),[reason,setReason]=useState(''),[reviewed,setReviewed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0),[created,setCreated]=useState(null);
 const [newVersion,setNewVersion]=useState(''),[standards,setStandards]=useState([]);
 const generation=useRef(0),locked=useRef(false),submission=useRef(null);
 useEffect(()=>{const invalidate=()=>{generation.current++;setDefinition(null);setRuns([]);setReviewed(false);setOperation('');setBusy(false);setCreated(null);submission.current=null;setRevision(value=>value+1);};const names=['depo:session-replaced','depo:access-verified','depo:credentials-changed','depo:credentials-cleared','depo:session-expired'];names.forEach(name=>window.addEventListener(name,invalidate));return()=>{generation.current++;names.forEach(name=>window.removeEventListener(name,invalidate));};},[]);
 useEffect(()=>{const controller=new AbortController(),epoch=++generation.current;setBusy(true);setError('');setDefinition(null);setReviewed(false);setOperation('');setCreated(null);submission.current=null;
  Promise.all([dataPipelineAPI.definitions({signal:controller.signal}),dataPipelineAPI.runs(100,{signal:controller.signal})]).then(([definitions,history])=>{if(controller.signal.aborted||epoch!==generation.current)return;const found=definitions.data?.definitions?.find(item=>item.job_id===jobId&&item.version===version);if(!found)throw new Error('This exact workflow version is unavailable.');setDefinition(found);setNewVersion(found.version.replace(/(\d+)$/,value=>String(Number(value)+1)));setStandards(found.allowed_standards||[]);setRuns((history.data?.runs||[]).filter(item=>item.job_id===jobId&&item.job_version===version));setRunId('');const retained=readRecovery(recoveryKey(jobId,version));if(retained){const scope=JSON.parse(retained.scope);if(scope[0]===jobId&&scope[1]===version&&['approve','disable','schedule','clear','revise'].includes(scope[2])&&scope[3]&&typeof scope[3]==='object'&&typeof scope[4]==='string'){submission.current=retained;setOperation(scope[2]);if(scope[2]==='revise'){setNewVersion(scope[3].version);setStandards(scope[3].allowed_standards||[]);}setRunId(scope[3].replay_run_id||'');setInterval(scope[3].interval_seconds||300);setReason(scope[4]);setError('Previous submission is unconfirmed. Retry the same request or inspect Change Control.');}}}).catch(failure=>{if(!controller.signal.aborted&&epoch===generation.current)setError(apiErrorMessage(failure));}).finally(()=>{if(!controller.signal.aborted&&epoch===generation.current)setBusy(false);});
  return()=>{controller.abort();generation.current++;};
 },[jobId,version,revision]);
 async function submit(){
  if(locked.current||busy||!reviewed||!definition||!operation||!reason.trim())return;
  const token=getCredentialProfile('DATA_JOB_APPROVAL_TOKEN');if(!token){setError('Connect workflow approval access in Admin.');return;}
  const parameters=operation==='schedule'?{replay_run_id:runId,interval_seconds:Number(interval)}:operation==='revise'?{version:newVersion,allowed_standards:standards}:{};
  const scope=JSON.stringify([jobId,version,operation,parameters,reason]);
  if(submission.current&&submission.current.scope!==scope){setError('Resolve the retained submission before changing its scope.');return;}
  if(!submission.current)submission.current={scope,request_id:crypto.randomUUID()};
  const key=recoveryKey(jobId,version);retainRecovery(key,submission.current);
  const epoch=generation.current;locked.current=true;setBusy(true);setError('');
  try{
   const {data}=await dataPipelineAPI.createDefinitionChange({request_id:submission.current.request_id,job_id:jobId,version,operation,parameters,reason},token);
   if(epoch!==generation.current)return;
   if(data?.preview_id!==submission.current.request_id||data.job_id!==jobId||data.version!==version||data.operation!==operation)throw new Error('Workflow request outcome is unverified. Inspect retained Change Control records.');
   retainRecovery(key,null);setCreated(data);setReviewed(false);onChanged?.(data);
  }catch(failure){if(confirmedSubmissionRejection(failure)){retainRecovery(key,null);if(epoch===generation.current)submission.current=null;}if(epoch===generation.current)setError(apiErrorMessage(failure,'Submission was not confirmed. Retry the same request or inspect Change Control.'));}
  finally{locked.current=false;if(epoch===generation.current)setBusy(false);}
 }
 const approved=definition?.lifecycle_state==='approved'&&definition?.enabled;
 return <section aria-label="Workflow definition controls"><h4>Workflow maintenance</h4>
  {busy&&<p role="status">Loading or retaining workflow evidence…</p>}{error&&<p role="alert">{error}</p>}
  {definition&&!created&&<><label>Requested change<select value={operation} disabled={Boolean(submission.current)} onChange={event=>{setOperation(event.target.value);setReviewed(false);}}><option value="">Select a change</option>{definition.lifecycle_state==='draft'&&<option value="approve">Approve for execution</option>}{definition.lifecycle_state!=='disabled'&&<option value="disable">Disable this version</option>}{approved&&['normalize-ceim','validate-semantic-batch','normalize-unstructured-ceim','connector-ceim-normalize'].includes(definition.job_type)&&<option value="revise">Approve revised source support (new version)</option>}{approved&&runs.length>0&&<option value="schedule">Configure retained-input schedule</option>}{approved&&definition.schedule&&<option value="clear">Remove schedule</option>}</select></label>
  {operation==='revise'&&<><label>New workflow version<input value={newVersion} disabled={Boolean(submission.current)} onChange={event=>{setNewVersion(event.target.value);setReviewed(false);}}/></label><fieldset><legend>Supported sources</legend>{[...new Set([...(definition.allowed_standards||[]),'sysml-v1','sysml-v2'])].map(standard=><label key={standard}><input type="checkbox" checked={standards.includes(standard)} disabled={Boolean(submission.current)} onChange={event=>{setStandards(current=>event.target.checked?[...current,standard]:current.filter(value=>value!==standard));setReviewed(false);}}/>{({'sysml-v1':'SysML v1','sysml-v2':'SysML v2',ap242:'AP242 CAD',plmxml:'PLMXML',qif:'QIF',reqif:'ReqIF'})[standard]||standard}</label>)}</fieldset><p>The current version remains unchanged. The new version starts without a schedule.</p></>}
  {operation==='schedule'&&<><label>Retained input<select value={runId} disabled={Boolean(submission.current)} onChange={event=>{setRunId(event.target.value);setReviewed(false);}}><option value="">Select a retained run</option>{runs.map(run=><option key={run.run_id} value={run.run_id}>{run.run_number||run.source_name||'Retained run'} · {run.started_at}</option>)}</select></label><label>Schedule interval (seconds)<input type="number" min={60} max={86400} value={interval} disabled={Boolean(submission.current)} onChange={event=>{setInterval(event.target.value);setReviewed(false);}}/></label></>}
  {operation&&<><label>Change reason<textarea value={reason} disabled={Boolean(submission.current)} onChange={event=>{setReason(event.target.value);setReviewed(false);}}/></label><label><input type="checkbox" checked={reviewed} onChange={event=>setReviewed(event.target.checked)}/> I reviewed this workflow version and the requested change.</label><button disabled={busy||!reviewed||!reason.trim()||(operation==='schedule'&&(!runId||!Number.isInteger(Number(interval))||Number(interval)<60||Number(interval)>86400))} onClick={submit}>Submit workflow CR</button></>}</>}
  {created&&<a href={`#/change-control?source=workflow_changes&view=requests&record_source=workflow_changes&record=${encodeURIComponent(created.preview_id)}`}>Review workflow CR / CO</a>}
 </section>;
}

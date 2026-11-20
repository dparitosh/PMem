import React,{useEffect,useRef,useState} from 'react';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {getCredentialProfile,publicationRecoveryScope} from '../services/serviceAuth';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import {businessText} from '../utils/businessText';
import ApprovalMatrix from './ApprovalMatrix';
import NativeChangeActions from './NativeChangeActions';

const kinds={merges:'Merged ontology draft',publications:'Ontology graph publication',bridges:'Instance mappings',pipeline:'Imported records publication',product_changes:'Product release'};
const root=path=>buildSemanticServiceUrl('oslc','/api/v1/change-control/releases'+path);
const key=row=>row.source_kind+':'+row.identifier;
const actions={submitted:[['accept','Accept source-to-release request'],['reject','Return change request']],accepted:[['authorize','Authorize frozen release configuration'],['reject','Return change request']],authorized:[['verify','Verify all release receipts'],['cancel','Cancel new release operations']]};

export default function ReleaseChangePanel({records=[],loading=false,requestId,onCreated,onChanged}){
 const [title,setTitle]=useState(''),[reason,setReason]=useState(''),[source,setSource]=useState(''),[selected,setSelected]=useState([]);
 const [activeStep,setActiveStep]=useState(0);
 const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[consent,setConsent]=useState(false),[revision,setRevision]=useState(0);
 const connection=useRef(publicationRecoveryScope());
 const lock=useRef(false),request=useRef(null),generation=useRef(0);
 useEffect(()=>{
  const invalidate=()=>{generation.current++;request.current?.abort();lock.current=false;setData(null);setBusy(false);setConsent(false);setSelected([]);setReason('');setSource('');setError('');setRevision(value=>value+1);};
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired','depo:session-replaced','depo:access-verified'];
  events.forEach(name=>window.addEventListener(name,invalidate));return()=>{events.forEach(name=>window.removeEventListener(name,invalidate));request.current?.abort();};
 },[]);
 useEffect(()=>{
  if(!requestId)return;
  const controller=new AbortController();request.current=controller;generation.current++;const epoch=generation.current;
  setData(null);setConsent(false);setError('');setBusy(true);
  apiClient.get(root('/'+encodeURIComponent(requestId)),{signal:controller.signal,timeout:30000}).then(({data:value})=>{
   if(controller.signal.aborted||epoch!==generation.current)return;
   if(value?.request_id!==requestId||!Array.isArray(value.operations)||value.operations.some(step=>!step||!Object.hasOwn(kinds,step.source_kind)||typeof step.identifier!=='string'||typeof step.state!=='string'||typeof step.receipt_verified!=='boolean')||typeof value.configuration_id!=='string'||!Number.isInteger(value.revision)||!Object.hasOwn({...actions,completed:[],cancelled:[],rejected:[]},value.state))throw new Error('Release scope could not be verified');
   setData(value);
  }).catch(failure=>{if(!controller.signal.aborted)setError(apiErrorMessage(failure,'Release evidence is unavailable. No decision was submitted.'));}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>controller.abort();
 },[requestId,revision]);
 const eligible=records.filter(row=>Object.hasOwn(kinds,row.source_kind)&&row.type==='oslc_cm:ChangeRequest'&&['submitted','accepted','authorized'].includes(row.change_state)&&(row.source_kind!=='pipeline'||row.release_source_ready===true));
 const sources=eligible.filter(row=>row.source_kind==='pipeline');
 const operationLabel=row=>[row.request_number,kinds[row.source_kind],row.reference,businessText(row.title)].filter(Boolean).join(' · ');
 const sourceLabel=row=>[row.reference||row.request_number,businessText(row.title),!row.reference&&!row.request_number?row.updated_at:''].filter(Boolean).join(' · ');
 const selectionValid=!loading&&selected.length>=2&&selected.length<=8&&sources.some(row=>row.identifier===source)&&selected.some(row=>row.source_kind==='pipeline'&&row.identifier===source)&&selected[selected.length-1]?.source_kind==='product_changes'&&selected.every(row=>eligible.some(current=>key(current)===key(row)));

 const submit=async action=>{
  if(lock.current||requestId&&!consent||!requestId&&!selectionValid)return;
  const token=getCredentialProfile('DATA_JOB_APPROVAL_TOKEN');if(!token){setError('Connect workflow approval access in Admin before requesting this decision.');return;}
  lock.current=true;setBusy(true);setError('');const epoch=generation.current,controller=new AbortController();request.current=controller;
  try{
   if(publicationRecoveryScope()!==connection.current)throw new Error('Service connection changed. Reopen the release before continuing.');
   const payload=requestId?{action,expected_revision:data.revision,configuration_id:data.configuration_id,reason}:{title,reason,source_run_id:source,operations:selected.map(({source_kind,identifier})=>({source_kind,identifier}))};
   const {data:value}=await apiClient.post(root(requestId?'/'+encodeURIComponent(requestId):''),payload,{signal:controller.signal,timeout:60000,headers:{Authorization:`Bearer ${token}`,...(requestId?{'Configuration-Context':data.configuration_context}:{})}});
   if(controller.signal.aborted||epoch!==generation.current)return;
   if(typeof value?.request_id!=='string'||requestId&&value.request_id!==requestId)throw new Error('Release request identity is unverified. Refresh retained state before retrying.');
   setConsent(false);
   if(requestId){setRevision(current=>current+1);onChanged?.(value);}else{setSelected([]);setTitle('');setReason('');onCreated?.(value);}
  }catch(failure){if(!controller.signal.aborted&&epoch===generation.current){setError(apiErrorMessage(failure,'Decision was not confirmed. Refresh retained state before another action.'));setConsent(false);}}
  finally{if(epoch===generation.current){lock.current=false;setBusy(false);}}
 };
 if(!requestId)return <details className="change-control__commands"><summary>Plan one source-to-release change</summary><p>Choose a source and order its review requests, ending with product release. Submission does not approve or execute them.</p>
  <div className="change-control__toolbar"><label>Change title<input value={title} disabled={busy} maxLength={200} onChange={event=>setTitle(event.target.value)}/></label><label>Retained source run<select value={source} disabled={busy||loading} onChange={event=>{setSource(event.target.value);setSelected([]);}}><option value="">Choose a source run</option>{sources.map(row=><option key={row.identifier} value={row.identifier}>{sourceLabel(row)}</option>)}</select></label></div>
  <label>Business reason<textarea value={reason} disabled={busy} maxLength={1000} onChange={event=>setReason(event.target.value)}/></label>
  <fieldset disabled={busy||loading}><legend>Prepared operations in loaded history</legend>{loading&&<p role="status">Loading prepared requests...</p>}{!loading&&!eligible.length&&<p>Prepare a publication request in <a href="#/data-flow?view=runs">Data Flow</a> and a product request in <a href="#/data-products?view=governance">Data Products</a>, then refresh Change Control.</p>}{eligible.map(row=><label key={key(row)}><input type="checkbox" checked={selected.some(item=>key(item)===key(row))} onChange={event=>setSelected(previous=>event.target.checked?[...previous,row]:previous.filter(item=>key(item)!==key(row)))}/>{operationLabel(row)}</label>)}</fieldset>
  <ol>{selected.map((row,index)=><li key={key(row)}>{businessText(row.title)} <button disabled={busy||index===0} aria-label={`Move ${businessText(row.title)} earlier`} onClick={()=>setSelected(previous=>{const next=[...previous];[next[index-1],next[index]]=[next[index],next[index-1]];return next;})}>Move earlier</button></li>)}</ol>
  {error&&<p role="alert">{error}</p>}<button disabled={busy||!title.trim()||!reason.trim()||!source||!selectionValid} onClick={()=>submit('create')}>Submit source-to-release change</button></details>;
 return <section className="change-control__commands" aria-label="Source-to-release coordination"><h4>One change from source to release</h4>{error&&<p role="alert">{error}</p>}<button disabled={busy} onClick={()=>setRevision(value=>value+1)}>Refresh release evidence</button>{busy&&<p role="status">Checking release configuration and native evidence…</p>}
  {data&&<><ApprovalMatrix change={data}/><p><strong>{businessText(data.title)}</strong> · {businessText(data.state)}. {data.scope_changed?'Source or operation scope changed; authorization is blocked.':'Frozen source and operation scopes retained.'}</p>
   <details><summary>Frozen release configuration</summary><p>Source: <a href={`#/data-flow?view=runs&run_id=${encodeURIComponent(data.source_run_id)}`}>Inspect retained source run</a></p><p>Configuration context: <code>{data.configuration_context}</code></p><p>Accepted source checksum: <code>{data.configuration?.selections?.source?.accepted_sha256||'Not recorded'}</code></p><p>Native scopes and execution order are fixed below. The baseline remains retained after rebase.</p></details>
   {actions[data.state]&&<><label>Review note<textarea value={reason} disabled={busy} onChange={event=>setReason(event.target.value)}/></label><label><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/>I reviewed this source and the ordered operations in this exact release configuration.</label><div className="change-control__command-actions">{[...actions[data.state],...(data.tracking_changed?[['rebase','Review unchanged scope after TRS reset']]:[])].map(([action,label])=><button key={action} disabled={busy||!consent||(action==='reject'&&!reason.trim())||(['accept','authorize'].includes(action)&&data.scope_changed)} onClick={()=>submit(action)}>{label}</button>)}</div></>}
   <ol>{data.operations.map((step,index)=>{const blocked=data.state==='completed'?'Release completed; retained evidence is read-only.':data.state!=='authorized'?'Authorize the parent release configuration before execution.':data.scope_changed?'The frozen source or operation scope changed.':data.operations.slice(0,index).some(previous=>!previous.receipt_verified)?'Complete and verify the preceding release operations first.':'';return <li key={key(step)}><h5>{index+1}. {kinds[step.source_kind]} · {businessText(step.state)}</h5><p>{step.receipt_verified?(data.state==='completed'?'Delivery verified for this release.':'Receipt retained · Final verification required.'):'Delivery not verified.'}</p><button aria-expanded={activeStep===index} onClick={()=>setActiveStep(index)}>Review operation {index+1}</button>{activeStep===index&&<NativeChangeActions kind={step.source_kind} previewId={step.preview_id||step.identifier} executionBlockedReason={blocked} onChanged={()=>setRevision(value=>value+1)}/>}</li>;})}</ol>
   <details><summary>Release decision history</summary><ol>{data.history?.map(entry=><li key={entry.revision}>{businessText(entry.action)} · {businessText(entry.actor)} · {businessText(entry.at)}</li>)}</ol></details>
  </>}
 </section>;
}

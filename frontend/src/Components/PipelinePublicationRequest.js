import React,{useEffect,useRef,useState} from 'react';
import {dataPipelineAPI,metadataRegistryAPI} from '../services/apiClient';
import {getCredentialProfile} from '../services/serviceAuth';
import {apiErrorMessage} from '../utils/apiErrorMessage';

export default function PipelinePublicationRequest({runId,sourceSystem='',onCreated}){
 const [releases,setReleases]=useState([]),[selection,setSelection]=useState(''),[source,setSource]=useState(sourceSystem),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),locked=useRef(false);
 useEffect(()=>{const invalidate=()=>{epoch.current++;locked.current=false;setReleases([]);setSelection('');setReason('');setError('');setBusy(false);};const names=['depo:session-replaced','depo:access-verified','depo:credentials-changed','depo:credentials-cleared','depo:session-expired'];names.forEach(name=>window.addEventListener(name,invalidate));return()=>{epoch.current++;names.forEach(name=>window.removeEventListener(name,invalidate));};},[runId]);
 async function load(){const generation=epoch.current;setBusy(true);setError('');try{const response=await metadataRegistryAPI.list({limit:200,lifecycle_status:'approved'});if(generation!==epoch.current)return;const rows=response.data?.assets;if(!Array.isArray(rows))throw new Error('Approved releases could not be verified.');setReleases(rows.filter(item=>item.lifecycle_status==='approved'&&typeof item.asset_id==='string'&&typeof item.version==='string'));setSelection('');}catch(failure){if(generation===epoch.current)setError(apiErrorMessage(failure));}finally{if(generation===epoch.current)setBusy(false);}}
 async function submit(){
  if(locked.current||busy||!reason.trim()||!source.trim()||selection==='')return;
  const release=releases[Number(selection)];if(!release)return;
  const token=getCredentialProfile('CEIM_PUBLISH_APPROVAL_TOKEN');if(!token){setError('Connect publication approval access in Admin.');return;}
  const generation=epoch.current;locked.current=true;setBusy(true);setError('');
  try{const identity=await dataPipelineAPI.executionIdentity(token,{params:{profile:'CEIM_PUBLISH_APPROVAL_TOKEN'}});if(generation!==epoch.current)return;const actor=identity.data?.actor;if(typeof actor!=='string'||!actor.trim())throw new Error('The connected approval identity could not be verified.');
   const result=await dataPipelineAPI.submitPublicationReview(runId,{semantic_release:{asset_id:release.asset_id,version:release.version,lifecycle_status:'approved'},source_system:source.trim()},reason.trim(),{approved_by:actor,approval_token:token});
   if(generation!==epoch.current)return;if(result.data?.run_id!==runId)throw new Error('Change request identity is unverified. Refresh this run before another action.');onCreated?.(result.data);
  }catch(failure){if(generation===epoch.current)setError(apiErrorMessage(failure));}finally{if(generation===epoch.current){locked.current=false;setBusy(false);}}
 }
 return <section className="change-control__commands" aria-label="Create publication change request"><h4>Create change request</h4>{error&&<p role="alert">{error}</p>}<button disabled={busy} onClick={load}>Load approved semantic releases</button><label>Semantic release<select aria-label="Semantic release" disabled={busy} value={selection} onChange={event=>setSelection(event.target.value)}><option value="">Select an approved release</option>{releases.map((release,index)=><option value={index} key={release.asset_id+':'+release.version}>{release.name||release.asset_id} · {release.version}</option>)}</select></label><label>Source system<input value={source} maxLength={240} onChange={event=>setSource(event.target.value)}/></label><label>Business reason<textarea value={reason} maxLength={1000} onChange={event=>setReason(event.target.value)}/></label><button disabled={busy||selection===''||!source.trim()||!reason.trim()} onClick={submit}>Submit change request</button><p>Submission does not authorize or publish data.</p></section>;
}

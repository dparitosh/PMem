import React, {useEffect, useState} from 'react';
import {dataPipelineAPI} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import AgentControlPanel from './AgentControlPanel';

// Navigation supplies an identity only. Re-read its evidence under current access.
export default function DataFlowAgentContext() {
 const [hash,setHash]=useState(()=>window.location.hash),[revision,setRevision]=useState(0);
 const [record,setRecord]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);

 const params=new URLSearchParams(hash.split('?')[1]||'');
 const runId=params.get('run_id'),eventId=params.get('reconciliation_id');
 const identifier=runId||eventId||'',kind=runId?'run':'event';
 const valid=!!identifier && identifier.length<=256 && !!runId!==!!eventId;
 useEffect(()=>{
  const navigate=()=>{setHash(window.location.hash);setRecord(null);};
  const clear=()=>{setRecord(null);setRevision(n=>n+1);};
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired','depo:access-verified'];
  window.addEventListener('hashchange',navigate);window.addEventListener('popstate',navigate);events.forEach(e=>window.addEventListener(e,clear));
  return()=>{window.removeEventListener('hashchange',navigate);window.removeEventListener('popstate',navigate);events.forEach(e=>window.removeEventListener(e,clear));};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();setRecord(null);setError('');setLoading(true);
  if(!valid){setLoading(false);setError('Select a processing run or event review in Data Flow.');return()=>controller.abort();}
  const read=kind==='run'?dataPipelineAPI.getRun:dataPipelineAPI.speedReview;
  read(identifier,{signal:controller.signal}).then(({data})=>{
   if(controller.signal.aborted)return;
   if(!data||data[kind==='run'?'run_id':'reconciliation_id']!==identifier||typeof data.status!=='string'||kind==='event'&&data.advisory_only!==true)throw new Error('Selected processing evidence could not be verified.');
   setRecord(data);
  }).catch(e=>{if(!controller.signal.aborted)setError(apiErrorMessage(e,'Processing evidence is unavailable.'));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[identifier,kind,valid,revision]);
 const back=kind==='run'?`#/data-flow?view=runs&run_id=${encodeURIComponent(identifier)}`:`#/data-flow?view=events&reconciliation_id=${encodeURIComponent(identifier)}`;
 return <section className="depo-panel" aria-label="Data Flow investigation"><div className="depo-panel__body">
  <h3>Processing context</h3><a href={back}>Back to Data Flow</a>
  {loading&&<p role="status">Checking selected evidence...</p>}
  {error&&<><p role="alert">{error}</p><button onClick={()=>setRevision(n=>n+1)}>Retry evidence check</button></>}
  {record&&<><p>{record.run_number||record.source_name||record.standard||'Event review'} - {record.status.replaceAll('_',' ')}</p>
   <AgentControlPanel/>

  </>}
 </div></section>;
}

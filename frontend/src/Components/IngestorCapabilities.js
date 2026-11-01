import React, {useEffect, useRef, useState} from 'react';
import {dataPipelineAPI as api} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import './IngestorCapabilities.css';

const labels={'configured-adapter':'Configurable connector','native-workflow':'Existing PMem workflow','not-integrated':'Not connected'};
export default function IngestorCapabilities(){
 const [state,setState]=useState({loading:true,rows:[],error:''});
 const [revision,setRevision]=useState(0),[filter,setFilter]=useState('all');
 const request=useRef(null);
 useEffect(()=>{
  const invalidate=()=>{request.current?.abort();setState({loading:true,rows:[],error:''});setRevision(n=>n+1);};
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
  events.forEach(name=>window.addEventListener(name,invalidate));
  return()=>events.forEach(name=>window.removeEventListener(name,invalidate));
 },[]);
 useEffect(()=>{
  const controller=new AbortController();request.current=controller;
  setState({loading:true,rows:[],error:''});
  api.ingestorCapabilities({signal:controller.signal,timeout:15000}).then(({data})=>{
   if(controller.signal.aborted)return;
   if(data?.contract!=='ingestor-capabilities-v1'||(data.semantica_version!=null&&typeof data.semantica_version!=='string')||!Array.isArray(data.ingestors)||data.ingestors.some(row=>typeof row?.id!=='string'||!row.id||typeof row.name!=='string'||typeof row.description!=='string'||!labels[row.integration]||(row.workspace!=null&&!['#/admin','#/import','#/ontology'].includes(row.workspace)))||new Set(data.ingestors.map(row=>row.id)).size!==data.ingestors.length)throw new Error('Invalid connector inventory response');
   setState({loading:false,rows:data.ingestors,version:data.semantica_version,runtime:data.acquisition_runtime==='ontology'?'existing semantic runtime':'shared application runtime',error:''});
  }).catch(error=>{if(!controller.signal.aborted)setState({loading:false,rows:[],error:apiErrorMessage(error,'Connector inventory unavailable.')});});
  return()=>controller.abort();
 },[revision]);
 return <section className="ingestor-capabilities" aria-label="Ingestion connector inventory">
  <header><div><h3>Data source capabilities</h3><p>See what can run in PMem and where to configure it. A library class alone is not an enabled connector.</p></div><button type="button" disabled={state.loading} onClick={()=>setRevision(n=>n+1)}>Refresh connector inventory</button></header>
  <label>Show connectors<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All source types</option>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
  {state.loading&&<p role="status">Loading connector inventory…</p>}
  {state.error&&<p role="alert">{state.error}</p>}
  {!state.loading&&!state.error&&<><details><summary>Runtime and connection checks</summary><p>REST acquisition uses the {state.runtime}. Semantica version in this API runtime: {state.version||'not installed here; the acquisition runtime is checked separately by the installer'}. Optional SDKs and external connections have not been tested by this inventory.</p></details><div className="ingestor-capabilities__table"><table><thead><tr><th>Source type</th><th>PMem support</th><th>How to use it</th><th>Registration storage</th></tr></thead><tbody>{state.rows.filter(row=>filter==='all'||row.integration===filter).map(row=><tr key={row.id}><th scope="row">{row.name.replace('Ingestor','')}</th><td>{labels[row.integration]}</td><td>{row.description}{row.workspace&&<p>{row.configurable?<button type="button" onClick={()=>document.getElementById('rest-source-configuration')?.scrollIntoView({behavior:'smooth',block:'start'})}>Configure REST source below</button>:<a href={row.workspace}>Open existing workflow</a>}</p>}</td><td>{row.postgres_namespace?<><strong>PostgreSQL registry</strong><br/>Versioned source reference; credentials remain server references.</>:'No Semantica connector registration'}</td></tr>)}</tbody></table></div></>}
 </section>;
}

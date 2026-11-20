import React,{useEffect,useRef,useState} from 'react';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {getCredentialProfile} from '../services/serviceAuth';
import {apiErrorMessage} from '../utils/apiErrorMessage';

export default function NumberingSchemes(){
 const [rows,setRows]=useState([]),[drafts,setDrafts]=useState({}),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[revision,setRevision]=useState(0);
 const request=useRef(null);
 const url=buildSemanticServiceUrl('ontology','/api/v1/admin/numbering-schemes');
 useEffect(()=>{
  const changed=()=>{request.current?.abort();setRows([]);setDrafts({});setNotice('');setRevision(value=>value+1);};
  const names=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired'];
  names.forEach(name=>window.addEventListener(name,changed));return()=>{request.current?.abort();names.forEach(name=>window.removeEventListener(name,changed));};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();request.current=controller;setBusy(true);setError('');
  apiClient.get(url,{signal:controller.signal,headers:{Authorization:`Bearer ${getCredentialProfile('GRAPH_READ_TOKEN')}`}}).then(response=>{
   const values=response.data?.schemes;
   if(!Array.isArray(values)||values.length!==6||new Set(values.map(row=>row.kind)).size!==6||values.some(row=>!row||typeof row.kind!=='string'||typeof row.prefix!=='string'||typeof row.include_year!=='boolean'||!Number.isInteger(row.digits)||!Number.isInteger(row.revision)))throw new Error('Numbering settings could not be verified');
   if(!controller.signal.aborted){setRows(values);setDrafts(Object.fromEntries(values.map(row=>[row.kind,{...row}])));}
  }).catch(failure=>{if(!controller.signal.aborted)setError(apiErrorMessage(failure));}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});return()=>controller.abort();
 },[url,revision]);
 function edit(kind,key,value){setDrafts(current=>({...current,[kind]:{...current[kind],[key]:value}}));setNotice('');}
 async function save(row){
  if(busy)return;const token=getCredentialProfile('ADMIN_API_KEY');if(!token){setError('Connect Admin maintenance in API access before changing numbering.');return;}
  const value=drafts[row.kind],controller=new AbortController();request.current=controller;setBusy(true);setError('');
  try{await apiClient.put(url+'/'+encodeURIComponent(row.kind),{prefix:value.prefix,digits:Number(value.digits),include_year:value.include_year,expected_revision:row.revision},{signal:controller.signal,headers:{'X-API-Key':token}});if(!controller.signal.aborted){setNotice(row.label+' numbering saved. Existing IDs are unchanged.');setRevision(n=>n+1);}}
  catch(failure){if(!controller.signal.aborted)setError(apiErrorMessage(failure));}finally{if(!controller.signal.aborted)setBusy(false);}
 }
 return <section className="depo-panel" aria-label="Object numbering"><div className="depo-panel__header"><h2>Object numbering</h2><button disabled={busy} onClick={()=>setRevision(value=>value+1)}>Refresh</button></div><div className="depo-panel__body"><p>Future records only. Existing numbers and UUIDs are retained.</p>{!getCredentialProfile('ADMIN_API_KEY')&&<p>Read only. Connect Admin maintenance in API access to save changes.</p>}{busy&&<p role="status">Loading numbering settings…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}<div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:13,borderCollapse:'collapse'}}><thead><tr><th>Object</th><th>Prefix</th><th>Digits</th><th>Include year</th><th>Current scheme preview</th><th>Action</th></tr></thead><tbody>{rows.map(row=>{const value=drafts[row.kind]||row;const unchanged=value.prefix===row.prefix&&Number(value.digits)===row.digits&&value.include_year===row.include_year;return <tr key={row.kind}><th style={{textAlign:'left',padding:12}}>{row.label}</th><td><input className="depo-input" aria-label={row.kind+' prefix'} maxLength={12} value={value.prefix} onChange={event=>edit(row.kind,'prefix',event.target.value.toUpperCase())} style={{width:110}}/></td><td><input className="depo-input" aria-label={row.kind+' sequence digits'} type="number" min={4} max={10} value={value.digits} onChange={event=>edit(row.kind,'digits',event.target.value)} style={{width:80}}/></td><td><input aria-label={row.kind+' include year'} type="checkbox" checked={value.include_year} onChange={event=>edit(row.kind,'include_year',event.target.checked)}/></td><td>{row.next_preview}</td><td><button className="depo-button" disabled={busy||unchanged||!getCredentialProfile('ADMIN_API_KEY')||!/^[A-Z][A-Z0-9]{0,11}$/.test(value.prefix)||!Number.isInteger(Number(value.digits))||Number(value.digits)<4||Number(value.digits)>10} onClick={()=>save(row)}>Save</button></td></tr>;})}</tbody></table></div></div></section>;
}

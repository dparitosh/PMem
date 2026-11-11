import React,{useEffect,useId,useState} from 'react';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {apiErrorMessage} from '../utils/apiErrorMessage';

const label=node=>node.type==='Decision'?(node.properties?.scenario||'Recorded decision'):(node.content||node.id);
const kinds={EvidenceRecord:'#006a9c',SourceReference:'#7856a8',Decision:'#a35f00'};
export default function DossierIntelligence({record}){
 const id=useId(),[tab,setTab]=useState('context'),[selected,setSelected]=useState(null);
 const [revision,setRevision]=useState(0),[state,setState]=useState({loading:true,data:null,error:''});
 useEffect(()=>{
  if(!record.source_kind||!record.identifier)return;
  const controller=new AbortController();setSelected(null);setState({loading:true,data:null,error:''});
  const path=`/api/v1/ontologies/evidence-dossiers/${encodeURIComponent(record.source_kind)}/${encodeURIComponent(record.identifier)}`;
  apiClient.get(buildSemanticServiceUrl('ontology',path),{signal:controller.signal,timeout:20000}).then(response=>{
   if(controller.signal.aborted)return;
   const data=response.data;
   if(data?.record_key!==record.record_key||data.schema_version!==1||!Array.isArray(data.graph?.nodes)||!Array.isArray(data.graph?.edges)||!Array.isArray(data.decisions)||!Array.isArray(data.provenance))throw new Error('Dossier context returned a different or invalid evidence record.');
   if(['source_status','updated_at','review_state','execution_state','delivery_state'].some(key=>record[key]!==undefined&&data.source_snapshot?.[key]!==record[key]))throw new Error('This record changed after selection. Refresh Change Control and inspect its current evidence.');
   setState({loading:false,data,error:''});
  }).catch(failure=>{if(!controller.signal.aborted)setState({loading:false,data:null,error:apiErrorMessage(failure,'Semantic evidence is unavailable; the retained dossier remains above.')});});
  return()=>controller.abort();
 },[record.record_key,record.source_kind,record.identifier,record.source_status,record.updated_at,record.review_state,record.execution_state,record.delivery_state,revision]);
 if(!record.source_kind||!record.identifier)return null;
 const data=state.data;
 const nodes=data?.graph.nodes.slice(0,11)||[];
 const positions=Object.fromEntries(nodes.map((node,index)=>[node.id,index?{x:205,y:28+(index-1)*32}:{x:25,y:175}]));
 const show=node=>setSelected(node);
 const download=()=>{
  const url=URL.createObjectURL(new Blob([data.provenance_turtle],{type:'text/turtle'}));
  const link=document.createElement('a');link.href=url;link.download='dossier-provenance.ttl';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 return <section className="dossier-intelligence" aria-label="Decision and evidence context">
  <div role="tablist" aria-label="Dossier evidence views">{[['context','Context'],['decisions','Decisions'],['provenance','Provenance']].map(([key,label],index)=><button key={key} id={`${id}-${key}`} role="tab" aria-selected={tab===key} aria-controls={`${id}-panel`} tabIndex={tab===key?0:-1} onClick={()=>setTab(key)} onKeyDown={event=>{
   const order=['context','decisions','provenance'];const next=event.key==='ArrowRight'?(index+1)%3:event.key==='ArrowLeft'?(index+2)%3:event.key==='Home'?0:event.key==='End'?2:null;
   if(next!==null){event.preventDefault();setTab(order[next]);document.getElementById(`${id}-${order[next]}`)?.focus();}
  }}>{label}</button>)}</div>
  <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`}>
   {state.loading&&<p role="status">Loading selected evidence context…</p>}
   {state.error&&<div role="alert"><p>{state.error}</p><button onClick={()=>setRevision(value=>value+1)}>Retry context retrieval</button></div>}
   {data&&<>
    {tab==='context'&&<><p>{data.scope}</p><div className="dossier-intelligence__graph"><svg viewBox="0 0 510 355" role="group" aria-label="Selected dossier context graph">
     <defs><marker id={`${id}-arrow`} markerWidth="7" markerHeight="7" refX="12" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="currentColor"/></marker></defs>
     {data.graph.edges.filter(edge=>positions[edge.source]&&positions[edge.target]).map((edge,index)=><line key={index} x1={positions[edge.source].x} y1={positions[edge.source].y} x2={positions[edge.target].x} y2={positions[edge.target].y} markerEnd={`url(#${id}-arrow)`}><title>{edge.type}</title></line>)}
     {nodes.map(node=><g key={node.id} role="button" tabIndex={0} aria-label={`Inspect ${node.type}: ${label(node)}`} transform={`translate(${positions[node.id].x},${positions[node.id].y})`} onClick={()=>show(node)} onKeyDown={event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();show(node);}}}>
      <title>{label(node)}</title><circle r={selected?.id===node.id?10:7} fill={kinds[node.type]||'#596b7a'}/><text x={12} y={4}>{node.type==='EvidenceRecord'?'Selected record':String(label(node)).slice(0,38)}</text>
     </g>)}
    </svg></div><p>Showing {nodes.length} of {data.graph.nodes.length} nodes. Blue: record · Purple: source reference · Amber: decision.</p>
    {selected&&<dl><dt>Selected node</dt><dd>{label(selected)}</dd><dt>Type</dt><dd>{selected.type}</dd><dt>Identity</dt><dd>{selected.id}</dd></dl>}</>}
    {tab==='decisions'&&(data.decisions.length?<><ol>{data.decisions.map(item=><li key={item.id}><strong>{item.scenario||'Retained assessment'}</strong><p>Outcome: {item.outcome||'Not recorded'} · Actor: {item.decision_maker||'Not recorded'}</p><p>{item.reasoning||'No recorded explanation'}</p><p>Confidence: {item.confidence==null?'Not established':item.confidence} · Recorded: {item.timestamp||'Not recorded'}</p></li>)}</ol>{data.decisions_truncated&&<p>Showing the first {data.decisions.length} of {data.decision_count} retained decisions.</p>}</>:<p>No structured decision assessment is retained in this record. Select Decision assessments in Change Control to inspect recorded policy decisions.</p>)}
    {tab==='provenance'&&<><p>{data.persistence}</p><p>{data.integrity_scope}</p><dl>{data.provenance.map(item=><React.Fragment key={item.field}><dt>{item.field.replaceAll('_',' ')}</dt><dd>{item.value}<small>Source: {item.source_uri}</small></dd></React.Fragment>)}<dt>Projection checksum</dt><dd>{data.snapshot_sha256}</dd></dl><button type="button" disabled={!data.provenance_turtle} onClick={download}>Download PROV-O evidence</button></>}
    <p className="dossier-intelligence__boundary">{data.authorization}</p>
   </>}
  </div>
 </section>;
}

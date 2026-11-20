import {resolveNodeName} from '../features/graph/graphRenderingPolicy';
import GraphPreviewCanvas from '../features/graph/GraphPreviewCanvas';
import React,{useEffect,useState,useRef,useMemo} from 'react';
import {graphApi} from '../services/graphApi';
import {apiClient} from '../services/apiClient';
import {agenticClient} from '../services/agenticApi';
import {buildSemanticServiceUrl} from '../config';
import {normalizeGraphDataset,getLinkEndpointId} from '../utils/graphUtils';
import {businessText} from '../utils/businessText';

const readable=value=>businessText(String(value||'')).replace(/_/g,' ');
const nodeName=resolveNodeName;
const values=value=>Array.isArray(value)?value:value?[value]:[];
export const isDeclaredClass=node=>[...values(node.labels),...values(node.properties?.rdf_types)].some(value=>/^(OntologyClass|Class)$|[#/]Class$/.test(value))||node.type==='class';

export function KnowledgePreview({data,ontologyId='',onSelectNode}){
 const [view,setView]=useState('all'),[selected,setSelected]=useState(null);
 const canvas=useRef(null);
 useEffect(()=>{setSelected(null);onSelectNode?.(null);},[data,onSelectNode]);
 const graph=useMemo(()=>normalizeGraphDataset(data?.data||data),[data]);
 const nodes=useMemo(()=>graph.nodes.filter(n=>view==='all'||(view==='classes'?isDeclaredClass(n):!isDeclaredClass(n))),[graph,view]);
 const preview=useMemo(()=>{
  const byId=new Map(nodes.map(node=>[node.elementId,node])),degree=new Map();
  graph.links.forEach(link=>[link.source,link.target].forEach(endpoint=>{const id=getLinkEndpointId(endpoint);if(byId.has(id))degree.set(id,(degree.get(id)||0)+1);}));
  const ranked=[...nodes].sort((a,b)=>(degree.get(b.elementId)||0)-(degree.get(a.elementId)||0));
  const chosen=new Set();
  for(const seed of ranked){if(chosen.size>=10)break;chosen.add(seed.elementId);for(const link of graph.links){if(chosen.size>=10)break;const a=getLinkEndpointId(link.source),b=getLinkEndpointId(link.target);if(a===seed.elementId&&byId.has(b))chosen.add(b);if(b===seed.elementId&&byId.has(a))chosen.add(a);}}
  return {nodes:nodes.filter(node=>chosen.has(node.elementId)),links:graph.links.filter(link=>chosen.has(getLinkEndpointId(link.source))&&chosen.has(getLinkEndpointId(link.target)))};
 },[graph,nodes]);
 const inspect=id=>{const node=nodes.find(item=>item.elementId===id)||null;setSelected(node);onSelectNode?.(node);};
 return <><div className="home-panel-heading"><div><h2>Knowledge graph</h2><p>Recorded resources and relationships · showing {preview.nodes.length} of {nodes.length} returned resources</p></div><nav aria-label="Graph preview views">{[['all','All'],['classes','Classes'],['resources','Other resources']].map(([id,label])=><button key={id} type="button" aria-pressed={view===id} onClick={()=>{setView(id);setSelected(null);onSelectNode?.(null);}}>{label}</button>)}</nav><div className="home-graph-zoom" role="toolbar" aria-label="Graph zoom"><button type="button" aria-label="Zoom in" title="Zoom in" onClick={()=>canvas.current?.zoomBy(1.4)}>+</button><button type="button" aria-label="Zoom out" title="Zoom out" onClick={()=>canvas.current?.zoomBy(1/1.4)}>−</button></div></div>
 {nodes.length?<GraphPreviewCanvas ref={canvas} data={preview} onInspectNode={inspect}/>:<p className="home-empty">No {view==='classes'?'declared classes':'resources'} were returned in this preview. Open the full graph to select another scope.</p>}
 {selected&&<div className="home-selected-record" role="status"><strong>{nodeName(selected)}</strong>{(selected.properties?.description||selected.properties?.definition)&&<p>{readable(selected.properties.description||selected.properties.definition)}</p>}</div>}
 <footer className="home-panel-footer"><span>Links show recorded relationships</span><a href={ontologyId?`#/graph?ontology_id=${encodeURIComponent(ontologyId)}`:'#/graph'}>Open full graph →</a></footer></>;
}

export default function HomeKnowledgeOverview({ontologyId='',revision=0,onSelectNode}){
 const request=useRef(null);
 const [refresh,setRefresh]=useState(0),[graph,setGraph]=useState({status:'loading'}),[decisions,setDecisions]=useState({status:'loading'}),[memory,setMemory]=useState({status:'loading'}),[filter,setFilter]=useState('all');
 useEffect(()=>{const reset=()=>{request.current?.abort();setGraph({status:'loading'});setDecisions({status:'loading'});setMemory({status:'loading'});setFilter('all');setRefresh(v=>v+1);};const events=['depo:credentials-cleared','depo:credentials-changed','depo:session-replaced','depo:session-expired','depo:access-verified'];events.forEach(name=>window.addEventListener(name,reset));return()=>events.forEach(name=>window.removeEventListener(name,reset));},[]);
 useEffect(()=>{const c=new AbortController();request.current=c;setGraph({status:'loading'});setDecisions({status:'loading'});setMemory({status:'loading'});
 const load=(promise,set,validate)=>Promise.resolve(promise).then(({data})=>{if(c.signal.aborted)return;if(!validate(data))throw new Error('Invalid summary response');set({status:'ready',data});}).catch(()=>{if(!c.signal.aborted)set({status:'unavailable'});});
 load(ontologyId?graphApi.getOntologyGraph(ontologyId,40,c.signal):graphApi.getOverview(40,c.signal),setGraph,data=>{const value=data?.data||data;return value&&Array.isArray(value.nodes)&&(Array.isArray(value.links)||Array.isArray(value.relationships));});
 load(apiClient.get(buildSemanticServiceUrl('oslc','/api/v1/change-control/records'),{signal:c.signal,timeout:15000,params:{source:'all',limit:4,offset:0}}),setDecisions,data=>Array.isArray(data?.records)&&Array.isArray(data?.coverage));
 load(agenticClient.get(buildSemanticServiceUrl('agentic','/api/v1/memory/records'),{signal:c.signal,timeout:15000,params:{ontology_id:ontologyId,limit:3,summary:true}}),setMemory,data=>Array.isArray(data?.records));
 return()=>{c.abort();if(request.current===c)request.current=null;};},[ontologyId,revision,refresh]);
 const rows=decisions.data?.records||[],turns=(memory.data?.records||[]).filter(row=>!ontologyId||row.graph_context?.ontology===ontologyId);
 const states=[...new Set(rows.map(row=>row.review_state).filter(Boolean))].slice(0,3);
 return <div className="home-knowledge-layout"><section className="home-panel home-knowledge-graph" aria-label="Knowledge graph overview">{graph.status==='ready'?<KnowledgePreview data={graph.data} ontologyId={ontologyId} onSelectNode={onSelectNode}/>:<><h2>Knowledge graph</h2><p role="status">{graph.status==='loading'?'Loading recorded graph context…':'Graph preview is unavailable. No empty-graph conclusion can be drawn.'}</p><a href="#/graph">Open Graph Explorer</a></>}</section>
 <aside className="home-memory-column" aria-label="Retained knowledge and memory"><section className="home-panel"><div className="home-panel-heading"><h2>Decision memory</h2><a href="#/change-control">View all</a></div><p className="home-panel-note">Approval and delivery status</p>
 {decisions.status!=='ready'?<p role="status">{decisions.status==='loading'?'Loading review evidence…':'Review evidence unavailable.'}</p>:<><nav aria-label="Decision review states"><button aria-pressed={filter==='all'} onClick={()=>setFilter('all')}>All</button>{states.map(state=><button key={state} aria-pressed={filter===state} onClick={()=>setFilter(state)}>{readable(state)}</button>)}</nav><ul className="home-record-list">{rows.filter(row=>filter==='all'||row.review_state===filter).slice(0,4).map(row=><li key={row.record_key}><span className="home-record-state">{readable(row.review_state)}</span><a href={`#/change-control?source=${encodeURIComponent(row.source_kind||row.record_key.split(':')[0])}&record=${encodeURIComponent(row.identifier||row.record_key.slice(row.record_key.indexOf(':')+1))}`}>{readable(row.title||row.identifier)}</a><small>{readable(row.category)} · {readable(row.execution_state)}</small></li>)}</ul>{!rows.length&&<p>No retained review records were returned. <a href="#/change-control">Review change workflows</a></p>}{decisions.data.coverage.some(item=>item.status!=='ok'&&item.status!=='available')&&<p className="home-panel-note">Some source coverage may be incomplete. Inspect Change Control for details.</p>}</>}
 </section><section className="home-panel"><div className="home-panel-heading"><h2>Recent conversations</h2><a href="#/reports?view=memory">All</a></div>{memory.status!=='ready'?<p role="status">{memory.status==='loading'?'Loading your saved conversations…':'Conversation memory unavailable.'}</p>:<><ul className="home-record-list">{turns.slice(0,3).map(row=><li key={row.job_id}><a href={`#/reports?view=memory&job_id=${encodeURIComponent(row.job_id)}${ontologyId?`&ontology_id=${encodeURIComponent(ontologyId)}`:''}`}>{readable(row.user_request)}</a><small>{row.graph_context?.ontology?'Ontology context retained':'Conversation context retained'}</small></li>)}</ul>{!turns.length&&<p>No completed conversations were returned for this scope.</p>}</>}</section></aside></div>;
}

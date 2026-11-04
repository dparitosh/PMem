import React, { memo, useEffect, useMemo, useState, useId, useRef } from 'react';
import { ReactFlow, Background, Controls, Handle, Position, applyNodeChanges } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const SysMLNode = memo(({data, selected}) => {
  const kind=String(data.type || '').replace(/^uml:/,'');
  const useCase=/usecase/i.test(kind),actor=/actor/i.test(kind);
  const requirement=/requirement/i.test(kind),constraint=/constraint/i.test(kind);
  const props=data.properties || {};
  return <div className={`sysml-node ${useCase?'sysml-usecase':''} ${actor?'sysml-actor':''} ${selected?'selected':''}`}>
    <Handle type="target" position={Position.Left}/>
    {actor ? <svg width="44" height="66" viewBox="0 0 44 66" aria-hidden="true"><circle cx="22" cy="9" r="7" fill="none" stroke="currentColor"/><path d="M22 16V42M3 26H41M22 42L6 64M22 42L38 64" fill="none" stroke="currentColor"/></svg> : !useCase && <div className="sysml-stereotype">«{kind === 'Requirement' ? 'requirement' : kind}»</div>}
    <strong>{data.label}</strong>
    {!useCase&&!actor&&<div className="sysml-compartment">
      {businessFields(props).map(([key,value],index)=><div key={`${key}:${index}`}>{key} = {Array.isArray(value)?value.join('; '):String(value)}</div>)}
    </div>}
    <Handle type="source" position={Position.Right}/>
  </div>;
});
export function businessFields(props) {
  const fields = [];
  const seen = new Set();
  const append = (label, value) => {
    if (value == null || value === '') return;
    const key = `${label}:${JSON.stringify(value)}`;
    if (!seen.has(key)) {seen.add(key); fields.push([label, value]);}
  };
  const profiles = (props.profile_applications || []).filter(profile=>/requirement/i.test(profile.stereotype || ''));
  for (const profile of profiles) {append('Requirement number',profile.Id); append('Text',profile.Text);}
  if (!profiles.length) {
    append('Requirement number',props.sysml_Id || props.profile_Id || props.requirementId || props.Id);
    append('Text',props.sysml_Text || props.profile_Text || props.requirementText || props.Text || props.text);
  }
  for (const key of ['documentation','body','value','units','unit','lower','upper','ownedFeatures']) append(key,props[key]);
  return fields;
}
const nodeTypes={sysml:SysMLNode};

export default function SysMLDiagram({graph,diagram,onSelect,selectedId,viewportCommand,filtered=false}) {
  const instanceRef=useRef(null);
  useEffect(()=>{
    const instance=instanceRef.current;
    if (!instance || !viewportCommand) return;
    if (viewportCommand.startsWith('zoom-in:')) instance.zoomIn();
    if (viewportCommand.startsWith('zoom-out:')) instance.zoomOut();
    if (viewportCommand.startsWith('fit:')) instance.fitView({padding:0.15});
  },[viewportCommand]);
  const markerPrefix='sysml-'+useId().replaceAll(':','');
  const initial=useMemo(()=>graph.nodes.map((node,i)=>({id:node.id,type:'sysml',position:{x:(i%3)*340,y:Math.floor(i/3)*230},data:node})),[graph.nodes]);
  const [nodes,setNodes]=useState(initial);
  useEffect(()=>setNodes(initial),[initial]);
  const edges=useMemo(()=>graph.links.map(link=>{
    const type=String(link.type).toUpperCase();
    const dependency=/SATIS|VERIF|TRACE|DERIVE|DEPEND|REFINE|INCLUDE|EXTEND/.test(type);
    const generalization=/GENERALIZATION|SPECIALIZATION/.test(type);
    const composition=/COMPOSITION|AGGREGATION/.test(type);
    const relationLabel={DERIVE_REQT:'deriveReqt',SATISFY:'satisfy',VERIFY:'verify',TRACE:'trace',REFINE:'refine',INCLUDE:'include',EXTEND:'extend'}[type] || type.replaceAll('_',' ').toLowerCase();
    return {id:link.id,source:link.source,target:link.target,label:dependency?`«${relationLabel}»`:composition||generalization?'':relationLabel,type:'smoothstep',
      markerStart:composition?`url(#${markerPrefix}-${type.includes('COMPOSITION')?'filled-diamond':'diamond'})`:undefined,
      markerEnd:generalization?`url(#${markerPrefix}-triangle)`:dependency?`url(#${markerPrefix}-arrow)`:undefined,
      style:{stroke:'#334155',strokeDasharray:dependency?'6 4':undefined}};
  }),[graph.links,markerPrefix]);
  if(/Table|Matrix/.test(diagram?.type || '')) return <div className="sysml-table-view"><h3>{diagram.name}</h3><p>Semantic fallback for {diagram.type}. Original vendor row/column configuration is unavailable.</p>{!graph.nodes.length && <p role="status">{filtered ? 'No elements match the current filter in this view.' : 'No row or column members were exported for this view.'}</p>}<table><thead><tr><th>Element</th><th>Type</th><th>Recorded relationship</th></tr></thead><tbody>{graph.nodes.map(node=><tr key={node.id}><td><button onClick={()=>onSelect(node)}>{node.label}</button></td><td>{node.type}</td><td>{graph.links.filter(link=>link.source===node.id).map(link=>`${link.type} → ${graph.nodes.find(other=>other.id===link.target)?.label || link.target}`).join('; ') || 'No outgoing connection in this view'}</td></tr>)}</tbody></table></div>;
  return <div className="sysml-diagram" aria-label={diagram?.name || 'SysML diagram'}>
    <div className="sysml-frame-title">{diagram?.type} [ {diagram?.name} ]</div>
    <svg width="0" height="0" aria-hidden="true"><defs>
      <marker id={`${markerPrefix}-triangle`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto"><path d="M1 1L11 6L1 11Z" fill="white" stroke="#334155"/></marker>
      <marker id={`${markerPrefix}-arrow`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto"><path d="M1 1L11 6L1 11" fill="none" stroke="#334155"/></marker>
      {['diamond','filled-diamond'].map(kind=><marker key={kind} id={`${markerPrefix}-${kind}`} viewBox="0 0 14 12" refX="1" refY="6" markerWidth="14" markerHeight="12" orient="auto-start-reverse"><path d="M1 6L7 1L13 6L7 11Z" fill={kind==='diamond'?'white':'#334155'} stroke="#334155"/></marker>)}
    </defs></svg>
    {!graph.nodes.length&&<p className="empty-state">{filtered ? 'No elements match the current filter in this view. Clear the search or choose a different SysML view.' : 'No drawable members were exported for this view. Its original binary drawing or vendor configuration may be required.'}</p>}
    <ReactFlow onInit={instance=>{instanceRef.current=instance;}} key={diagram?.id} nodes={nodes.map(node=>({...node,selected:node.id===selectedId}))} edges={edges} nodeTypes={nodeTypes} onNodesChange={changes=>setNodes(current=>applyNodeChanges(changes,current))} onNodeClick={(_,node)=>onSelect(node.data)} fitView minZoom={0.05} maxZoom={2} nodesConnectable={false} deleteKeyCode={null}><Background/><Controls showInteractive={false}/></ReactFlow>
  </div>;
}

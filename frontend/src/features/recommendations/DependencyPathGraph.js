import React, {useId,useMemo,useState} from 'react';
import {UI_COLORS as C} from '../../styles/uiTokens';

export default function DependencyPathGraph({data}) {
  const [selected,setSelected]=useState(null);
  const markerId=useId().replace(/:/g,'');
  const graph=useMemo(()=>{
    const root=data.change_entity;
    if(!root?.node_id)return {nodes:[],edges:[],limited:false,height:100};
    const nodes=new Map([[root.node_id,{id:root.node_id,name:root.name,depth:0}]]),edges=new Map();
    for(const item of data.realization_chain || []){
      let current=root.node_id;
      for(const [index,edge] of (item.path || []).entries()){
        const target=edge.start_id===current?edge.end_id:edge.start_id;
        if(!nodes.has(target)&&nodes.size>=60)break;
        if(!nodes.has(target))nodes.set(target,{id:target,name:item.path_names?.[index+1] || 'Related record',depth:index+1});
        edges.set(edge.relationship_id,{id:edge.relationship_id,source:current,target});
        current=target;
      }
    }
    const columns=new Map();
    for(const node of nodes.values()){
      const row=columns.get(node.depth)||0;
      node.x=100+node.depth*180;node.y=40+row*55;columns.set(node.depth,row+1);
    }
    return {nodes:[...nodes.values()],edges:[...edges.values()].filter(edge=>nodes.has(edge.source)&&nodes.has(edge.target)).map(edge=>({...edge,a:nodes.get(edge.source),b:nodes.get(edge.target)})),limited:nodes.size>=60,height:Math.max(180,...[...columns.values()].map(count=>count*55+40))};
  },[data]);
  if(!graph.nodes.length)return null;
  const record=(data.realization_chain || []).find(item=>item.node_id===selected);
  return <section aria-label="Dependency graph">
    <p>Follow the recorded dependency paths from the selected object. Select a record to inspect its path. Arrows show the investigation route; retained evidence records the original relationship direction.</p>
    {graph.limited&&<p role="status">The diagram shows up to 60 records. The evidence table retains the remaining results.</p>}
    <div style={{overflow:'auto',maxHeight:540,border:`1px solid ${C.border}`}}>
      <svg viewBox={`0 0 1000 ${graph.height}`} style={{width:'100%',minWidth:800,height:graph.height}} role="img" aria-label="Recorded engineering dependency paths">
        <defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill={C.textSec}/></marker></defs>
        {graph.edges.map(edge=><path key={edge.id} d={`M${edge.a.x+65},${edge.a.y} L${edge.b.x-65},${edge.b.y}`} fill="none" stroke={C.textSec} markerEnd={`url(#${markerId})`} opacity={.6}/>)}
        {graph.nodes.map(node=><g key={node.id} role="button" tabIndex={0} aria-label={`Inspect ${node.name}`} onClick={()=>setSelected(node.id)} onKeyDown={event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();setSelected(node.id);}}} style={{cursor:'pointer'}}>
          <title>{node.name}</title><rect x={node.x-70} y={node.y-17} width="140" height="34" rx="5" fill={selected===node.id?C.primary:C.surface} stroke={C.primary}/>
          <text x={node.x} y={node.y+4} textAnchor="middle" fontSize="11" fill={selected===node.id?'#fff':C.textPrimary}>{node.name.length>22?node.name.slice(0,20)+'…':node.name}</text>
        </g>)}
      </svg>
    </div>
    {record&&<p role="status"><strong>{record.name}</strong>: {record.path_names?.join(' → ')}. {record.review_status==='configuration_conflict'?'Configuration evidence conflicts.':'Effectivity review is required.'}</p>}
  </section>;
}
